# 领域映射：从 IT 工单闭环开始

这是设计例子，不是已接入真实系统的 demo，也不证明任何生产能力。
下面的对象和事件属于本工具包自定义应用契约，不是 AG-UI 官方字段。
MUST 表示本示例适用的必要条件，SHOULD 表示推荐，可选项按项目范围取舍。
设计细节见 [模块边界](../skills/agui-design/references/architecture.md)、[数据契约](../skills/agui-design/references/data-contracts.md)、[持久流程](../skills/agui-design/references/workflows.md)。

## 主场景与已授权范围

用户：“分析今天积压的高优工单，给出改派建议，审批后批量改派。”

- 目标：降低等待时间，给出有证据且可执行的改派方案。
- 本次授权：读取授权项目的工单与负载，生成提案；实际改派需使用已有业务审批入口。
- 未授权：修改优先级、关闭工单、给客户发信、扩大到其他租户或项目。
- MUST 沿用用户选择的 ITSM 系统；不能为了展示 Agent 而另造一份工单权威数据库。
- SHOULD 先覆盖一个队列、一种改派动作；可选多 Agent 分析不改变执行边界。

## IT 服务对象与工具

| 概念 | IT 工单映射 | 关键约束 |
|---|---|---|
| Entity | Ticket、Team、AgentCapacity | tenant/project 范围、后端 version/ETag |
| Evidence | 工单状态快照、分组队列、值班表、负载指标 | observed_at、指标窗口、authority、新鲜度 |
| Intent | 分析并起草改派 | 不含关闭/发信/修改优先级的权限 |
| Proposal | ticket → new_assignee 的明确清单 | expected ticket versions、原因、影响范围、expiry |
| Approval | 操作者批准具体清单 hash | 审批权限、当前权限、内容绑定、可撤销 |
| Operation | 批次及单工单改派操作 | 持久 key、attempt、后端操作 ID、unknown |
| Receipt | 每张工单实际新负责人及新版本 | 权威后端结果，不用模型总结代替 |
| UIEvent | 负载表、证据时间线、改派差异、执行结果卡 | provisional/final 与业务提交分开 |
| Memory | 操作者偏好的展示粒度、固定排班约束 | 许可类别、主体隔离、删除屏障；不存临时授权 |

建议工具 surface：

```text
search_tickets(filters)              → 授权范围内的 Ticket/Evidence
get_ticket(ticket_id)                → 最新状态及 version
get_team_capacity(team_id, window)   → 负载证据及统计窗口
stage_ticket_assignment(items)       → Proposal，不执行改派
present_assignment_diff(proposal_id) → 服务端补全差异组件
apply_assignment(proposal_id, key)   → Operation/Receipt，批准从可信 host 取得
get_operation(operation_id)          → 状态与已确认 receipt
```

- MUST 模型不能通过参数提交 `tenant_id=other`、`approved=true`、操作者身份或伪造 receipt。
- MUST 工具参数可包含资源引用；可信 session 决定资源引用在哪个租户内解析。〔H01〕
- SHOULD 将只读批量分析与实际执行分开，避免一个自由文本“优化”工具同时改多类业务字段。

## 一条正常路径

1. Host 绑定操作者和租户；保存 request/intent，恢复会话及尚未处理的应用事件。
2. Agent 读取高优工单和当前负载，列出按事实支持的候选改派及未决项。
3. 后端校验目标负责人资格、工单可改派状态、版本，形成带 expiry 的不可变提案。
4. UI 显示工单、原负责人、新负责人、版本、原因和预计影响；推断明确标注为推断。
5. 操作者在授权审批入口批准该 hash；不是模型看到“好”就给自己授予批准。
6. apply 检查批准、当前权限和实体版本，以持久 operation key 提交业务后端。
7. 每个已确认 receipt 更新结果卡；Agent 总结成功、冲突、unknown 及下一步。

如果用户原话明确授权“把 TK-17 改派给值班员”，且组织允许这种可逆改派直接执行，
SHOULD 在相同权限和版本约束下直接完成并回报，不为套用示例额外增加正式审批。
审批级别由动作风险、组织策略和已有授权决定。〔H03/H10〕

## 故障路径与最低验收

| 注入 | 必须观察到的结果 | 控制 |
|---|---|---|
| A 租户请求 B 的工单 ID | 读取、呈现和改派均拒绝，不泄露对象是否存在 | H01权限与租户 |
| 同 key 重复点击批准执行 | 返回原 operation/receipt，不重复改派 | H02操作幂等 |
| 批准后工单已转交他人 | 版本冲突；显示新状态，重做提案，不沿用旧批准 | H03提案版本与审批 |
| ITSM 已提交但连接断开 | unknown，按 key/操作 ID 查询；不自动发第二次非幂等写 | H04写入账本原子/对账 |
| 改派与另一页面撤销并发 | 版本/epoch 阻止晚执行，或明确返回已提交需补偿 | H05会话并发撤销 |
| receipt 保存后 SSE 断开 | 重连查询 receipt，正确终结 pending 卡片 | H06UI终态与receipt |
| 负载缓存已过期 | 重新读取或标注不能据此提交 | H07事实来源与新鲜度 |
| 删除偏好时后台提取在运行 | 条件写拒绝旧 generation，偏好不复活 | H08记忆删除顺序 |
| 一个负载读一直不返回 | deadline 到期后降级；不隐藏同批已成功写 | H09时间并发成本预算 |
| 模型调用 close_ticket 或扩大范围 | 工具不暴露或 policy 拒绝，仍可完成允许部分 | H10意图与坏模型边界 |
| 模型选择不稳定 | 先机械探针后任务轨迹评测，复用最小失败样例 | H11评测效率 |
| 外部系统持续故障 | 可关联诊断、只读降级、明确恢复或接管入口 | H12可观测降级 |

## 批量执行不能伪造全有或全无

- MUST 先判断 ITSM 是否提供真正原子批量接口；没有则按工单保存独立子 operation 与 receipt。
- MUST 批次完成可以是部分成功；未成功项保持明确状态，不将所有工单一起标“已改派”。
- SHOULD 只对失败前已确认未写的子项安全重试；unknown 子项先对账。
- 可选：回退已改派工单是一组新的补偿操作，需要检查其当前负责人/版本；不能覆盖用户后续修改。
- MUST 不因为数据库里有一个 batch receipt 就宣称远端每张工单都成功。

## 其他领域如何映射

| 设计位置 | CRM / 客户运营 | 资源预约 |
|---|---|---|
| 用户闭环 | 找停滞商机→拟跟进任务→确认后创建 | 搜索资源→方案比较→预留→确认预约 |
| 权威对象 | Account、Opportunity、Activity | Resource、Availability、Hold、Booking |
| 读取证据 | 联系历史、阶段、负责人、更新时间 | 时间区间、容量、时区、占用版本 |
| 明确工具 | get_opportunity、stage_followup_task | search_slots、create_hold、confirm_booking |
| 提案边界 | 创建跟进任务与发送客户消息分开 | 展示空闲与实际占用分开，hold 有服务器 expiry |
| 批准内容 | 目标客户、任务/消息内容、收件人 | 资源、参与者、时间、费用/取消条件 |
| 版本冲突 | 商机已关闭或负责人变化后重做方案 | 资源已占用、hold 过期后不能沿用确认 |
| unknown 对账 | 查询创建任务/外发消息操作 ID | 按幂等键查询 booking，避免重复预约 |
| 补偿边界 | 撤回任务可行，已送达邮件通常不可撤回 | 取消预约有权限、截止时间和费用条件 |
| UI | 漏斗、客户卡、任务差异、发送状态 | 日历、时间线、预留倒计时、预约 receipt |
| 长期记忆 | 展示偏好，不保存无限期“可群发”授权 | 地点/时间偏好，不替代当前参与者同意 |

## 迁移时保留机制，重写领域规则

- SHOULD 复用 runtime、工具结果 envelope、operation/receipt 生命周期、UI 投影和评测方法。
- MUST 重写领域实体、授权范围、版本/有效期、冲突、补偿和真实业务适配器。
- MUST 金额涉及多币种时不能无条件加总；预约时间需时区及边界规则，不能只靠显示字符串。
- SHOULD 第二领域优先选语义差异大的流程来检验抽象，而非只给同类目录换名称。
- 可选：两领域共用 MemoryStore 接口；数据分类、主体隔离和保留策略仍各自定义。
- 交付时 MUST 说明哪些路径仅 fixture、哪些完成故障注入、哪些已连接真实后端并得到业务验收。
