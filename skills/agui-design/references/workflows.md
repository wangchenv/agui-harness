# 持久流程、授权与异常恢复

这些状态与接口是本工具包建议的应用设计，不是 AG-UI 官方工作流协议。
MUST=适用时必须保证；SHOULD=优先选择；可选=根据业务复杂度采用。
本指导不自动提供耐久执行、exactly-once 或生产可用性；交付时必须列明实际实现与未覆盖项。

## 1. 按任务选择流程强度

| 动作 | 默认处理 | 何时增加人类介入 |
|---|---|---|
| 读取授权范围内的信息 | 权限检查后直接执行 | 关键对象歧义、权限申请或范围明显变化 |
| 起草、排序、预览 | 可直接产出可审阅方案 | 缺失条件会改变方案实际含义 |
| 已明确授权的低风险可逆写 | 在限定 intent 内执行并回报 | 超过授权数量、目标或后果边界 |
| 昂贵、不可逆、外部发送等动作 | 按现有业务策略确认/审批 | 依据具体风险，不能由 Skill 一律增加门禁 |
| 跨系统长流程 | 保存状态并分步推进 | 冲突、unknown、补偿失败或策略明确要求 |

- MUST 尊重既有用户授权；同一已批准内容的安全重试不反复请求批准。〔H03/H10〕
- MUST 内容、目标、预算或实体版本改变时重新判断授权，不自动挪用旧批准。
- SHOULD 先把方案、差异与影响做成可审阅结果，再请求必要的批准；不让用户批准空白计划。
- SHOULD 衡量批准的等待与打断成本；低风险流程的审批过重会降低任务完成率。

## 2. 角色流程与业务状态机

Skill 可以描述“读取→分析→形成方案”；MUST 不把模型遵守该顺序当成程序保障。
业务需要严格顺序时，在后端/工作流引擎持久化状态并验证每次迁移的前置条件。

```text
Intent: received → clarified / accepted → fulfilled / partially_fulfilled / cancelled
Proposal: draft → ready → approved / rejected → consumed / superseded / expired
Operation: pending → running → succeeded / failed / unknown
                         └→ cancel_requested → cancelled / succeeded / unknown
unknown → reconciling → succeeded / failed / manual_review
```

- MUST 按实际业务调整名称，保留 confirmed success、confirmed failure、unknown 的区别。
- MUST cancelled 只在确认没有发生该动作或已经完成明确取消协议后使用。
- MUST proposal/approval 有持久引用；approval 可以是独立记录，不要求把批准做成 proposal 的唯一状态。
- SHOULD 每次迁移记录 actor、时间、预期版本、原因、操作 ID 和下一步负责人。〔H12〕
- 可选：纯读取任务无需建所有表；实现必要语义而不是照抄整套状态名。

## 3. 从请求到受控执行

1. Host MUST 解析可信 principal、tenant、request ID；客户端不能指定权限身份。〔H01〕
2. Runtime SHOULD 记录 Intent，确认可执行动作与范围；有关键歧义时只询问会改变操作的缺口。
3. 读取工具 MUST 返回来源及版本，Policy 判断证据是否够新。〔H07〕
4. 需要预审的写 MUST 形成不可悄改的 Proposal，绑定实际 payload hash、expected versions 和 expiry。
5. 需要批准时 MUST 从可信审批入口取得 Approval，绑定具体内容与操作者权限。〔H03〕
6. 执行前 MUST 检查当前权限、批准/提案有效性、撤销、预算及业务条件。
7. 首次副作用前 MUST 持久登记 Operation，并由业务后端执行幂等与条件写。〔H02/H04〕
8. 成功 receipt MUST 独立于模型回复保存；UI 从 receipt 更新，模型只解释结果。〔H06〕
9. 未完成部分 MUST 明确记录 blocked/failed/unknown，不能用 end_turn 把任务标为成功。

## 4. 单数据库事务的最低结构

```text
BEGIN
  读取 tenant + idempotency_key 的已有 operation/receipt
  同 key 不同 payload → 拒绝；已成功同 payload → 返回原 receipt
  校验批准 hash、expiry、当前权限、expected entity version
  条件更新业务对象；版本不符 → 冲突，不改批准内容
  原子写入操作结果、receipt，必要时写 outbox event
COMMIT
```

- MUST 依靠唯一约束和事务处理并发，不能只用内存字典或先查后写。
- MUST 金额/资源单位明确；事务失败后不能留下“账本成功、实体未改”或反向状态。
- SHOULD 同事务写 outbox，后台至少一次发布 UI/集成事件，消费者按 event ID 去重。
- MUST 重放前按当前身份鉴权；知道旧 operation key 不代表有权读取其结果。
- 可选：SQLite 可验证单库机制；生产数据库、部署拓扑和故障模型需另行验收。

## 5. 外部 API：先区分提交状态，再决定重试

| 观察 | 操作状态 | 下一步 |
|---|---|---|
| 调用前本地校验失败 | failed/blocked | 修正前置条件，不发请求 |
| 后端明确拒绝且未执行 | failed | 按错误类型修正或安全重试 |
| 后端返回成功及操作引用 | succeeded | 保存 receipt，发布可恢复事件 |
| 超时、断连、进程崩溃，无法证明是否提交 | unknown | 用稳定 key/后端操作 ID 查询并 reconcile |
| 后端不可查询且不支持幂等 | manual_review | 停止自动重复副作用，交人工或设计补偿流程 |

- MUST 不把 coroutine cancel、HTTP timeout 或通用 unavailable 解释成“业务没有执行”。
- MUST 重试沿用同一 logical operation key；attempt ID 可以变化。〔H02/H04〕
- MUST 后端真正写入端落实幂等；仅在 Agent 层缓存结果不能消除跨进程和响应丢失窗口。
- SHOULD reconcile 持有 lease/版本条件，防止多个恢复 worker 同时采取互斥动作。
- SHOULD unknown 显示“结果确认中”及查询入口；不要提示用户直接再执行一次。
- 可选：外部提供幂等保留期时，保存其 expiry；超期后不可盲目沿用“可安全重放”的假设。

## 6. 并发、中断、撤销与资源管理

- MUST 为每个独立工具记录完成结果；一个慢读不得抹掉同批已成功写。〔H04/H09〕
- MUST 写结果在流结束前也可持久化；eager 工具执行不能依赖最终 assistant message 才有记录。
- SHOULD 默认只对独立读工具采用提前并发；写需要依据依赖、顺序和资源锁决定。
- MUST 给 turn、预取、排队、单工具、重试与总成本分别定义预算，不只设置模型 HTTP timeout。
- MUST 限制普通工具并发和每 turn 调用数；max iterations 不限制单轮扇出。〔H09〕
- MUST 取消后有界等待子任务退出；未确认的外部操作交由独立恢复流程跟踪。
- MUST 会话写用串行化或版本比较+合并；冲突时不能让“最后写者”覆盖应用按钮事件。〔H05〕
- MUST 撤销提升 session/action epoch 或等价版本；晚到任务提交前检查是否仍获许可。
- SHOULD 已经提交的动作按撤销/补偿业务协议处理，不伪造 cancelled。

## 7. UI 投影与应用外事件

- MUST 以 operation/receipt 关联卡片，区分“预览已呈现”和“业务已提交”。〔H06〕
- MUST 处理重复事件、乱序、断线和重连：sequence/revision 检查、snapshot 或 receipt 查询恢复。
- MUST final/error/cancelled/unknown 收敛对应 partial/pending；旧 partial 不能复活终态。
- SHOULD 用户通过普通页面完成的操作写入业务系统，并作为带 ID 的应用事件回注会话。
- SHOULD 回注只描述已确认事件；上下文摘要不能成为新的授权或掩盖权限检查。
- 可选：断流后保留暂定卡片，但必须可辨认且不能带已获批准的执行按钮。

## 8. 长流程与 Saga 的适用边界

- MUST 长流程把步骤状态、输入版本、重试策略和 receipt 保存在聊天历史之外。
- SHOULD 优先使用现有耐久工作流服务处理定时唤醒、回调、lease 和恢复。
- MUST 多系统步骤分别建立 operation；不能宣称一个本地事务包含所有外部副作用。
- MUST 在采用 Saga 时定义可补偿动作、补偿条件、顺序及不可逆步骤；补偿不等于数据库回滚。
- MUST 补偿也幂等并产生独立 receipt；补偿失败进入明确人工接管，保留原事实。
- SHOULD 不可逆动作放在前置条件最充分的位置；需要人类决策时保存可恢复等待状态。
- 可选：多个安全只读步骤并行；有读后写依赖的步骤不能仅因工具支持并发就一起执行。

## 9. 后台记忆的删除顺序

1. 提取任务 MUST 捕获 subject + tenant 的 purge generation 和读取来源。
2. 删除 MUST 清事实并原子推进 generation；异步索引/缓存有明确清理状态。
3. 提取写入 MUST 用条件事务检查 generation 未变；不同则丢弃候选事实。
4. 重试、排队和备份恢复 MUST 保留删除屏障，不重新创建已删主体数据。〔H08〕

## 10. 用故障证明流程，而不是重复测试提示词

- MUST 对提交前/后、receipt 前/后、事件发布前/后、用户撤销前/后注入失败。〔H11〕
- MUST 验证业务最终状态、操作账本、用户界面三者一致；不能只断言返回码或模型文字。
- SHOULD 先用 fake model + 真执行器测试机械不变量，再用少量真实任务评估意图与工具选择。
- SHOULD 保留最小失败样例；修复后只扩展受影响路径，避免每次运行无关大评测。
- MUST 可观测记录 request/operation/attempt/event 关联与状态，不默认记录凭证和敏感全文。〔H12〕
- SHOULD 报告任务成功率、unknown 数量/年龄、重复副作用、恢复时长、人工介入及每成功任务成本。
- 数据形状见 [data-contracts.md](data-contracts.md)；模块职责见 [architecture.md](architecture.md)。
