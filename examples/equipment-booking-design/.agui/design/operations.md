# 运行、恢复与实施前依赖

## 预算与并发（设计目标，待压测校准）

单 turn deadline 20 秒；最多 8 次工具调用、2 个并行工具、输入 32 KiB、输出 2500 tokens。
单 turn 费用预算 200000 microunits，货币单位按账单归一为 USD，即最多 0.20 USD；真实模型未选择，不能称已达标。
查设备/准备提案/列冲突 3 秒；提交与对账单次调用 5 秒；写每个 operation 最多 1 个持租约执行者。
租户级模型并发初始 10、外部预约写并发 4，超额排队最多 3 秒后显式 BUSY；管理员不绕过总预算。
预算检查在派发前原子预留，完成后按实耗结算；子工具/恢复工作同样受独立 worker 配额约束。
只读可对可重试错误作 1 次带抖动重试，不能使总 deadline 失效。
占用请求是否发送决定取消处理；发送后超时不盲目重试，改为 client_request_id 查询。

## 恢复 worker

后台周期扫描 executing 租约过期和 unknown；使用租约 fencing token 防止旧 worker 写回覆盖。
对同一 operation 查询退避为 1、2、5、10、30 秒，此后最多每 60 秒一次；5 分钟未决升级人工核实。
5 分钟是人工介入目标，不是把 unknown 变成失败的阈值。
进程重启从持久 operation/outbox 恢复；页面关闭、turn 完成、session 删除均不丢失未决业务。
业务结果写入与发布 outbox 同事务；重放 event_id 相同，消费者可去重。
人工处理只能附上可验证后端结果/对账引用，不能把“猜测未成功”作为 failed。

## 会话与权限

SSO principal 在 Host 注入；每次工具、页面动作、SSE 订阅、snapshot、operation 查询独立检验权限。
缓存角色有短 TTL，但写前必须检查撤销/角色版本；不能仅依赖建立聊天时的一次认证。
session CAS 失败后重新读取并合并事件，不把旧完整对象强制写回新 revision。
reset/logout 增加 generation；旧批准不能开启新的写；已有远端 effects 进入对账而非删除。
审计资料与用户会话保留策略分离；删除聊天不等于删除合法业务预约或抹去审计。
本期不开 memory，因此无背景偏好抽取任务；不得把失败的 memory worker 当作允许漏测本期 session 的理由。

## 可观测性与降级

贯穿 request_id、turn_id、operation_id、proposal_id、event_id、backend_request_id；每个拒绝有机器 reason_code。
度量提交成功率、明确冲突率、unknown 比例/年龄、对账耗时、重复抑制量、CAS冲突、撤销拒绝、seq恢复次数。
日志不记 token、完整提示词、自由用途原文；tenant/员工标识仅在授权审计中可见。
模型不可用时员工仍可用确定性设备筛选与确认表单；管理员仍可查看/处理持久 conflict_case。
目录不可用时禁止新方案；后端占用不可用时保留只读证据过期提示，停止新写并继续低速对账。
未知结果超过 5 分钟、跨租户拒绝异常、恢复积压或 receipt 缺失触发运营告警；本次设计未授权发送真实告警。
回滚模型或 UI 版本不能回滚现实预约；部署变更必须保留 operation/schema 向后兼容，本次不部署。

## 业务 SLO（候选目标，未实测）

已认证查询与提案端到端 p95 ≤ 8 秒；确定性提交后端正常时 p95 ≤ 3 秒。
成功结果 UI 到达/刷新可见 ≤ 2 秒；unknown 95% 在 60 秒内被核实，超过 5 分钟交人工。
重叠双占用、越权写、重复 request_id 多个预约、无 receipt 的成功展示：验收样本内允许值均为 0。
真实任务总体成功率 ≥ 95%；人工主动操作时间中位数降低至少 20%，返工率不增加。
系统故障/unknown 不排除出分母；业务正常无可用设备且准确告知可按定义算正确任务结果。
这些是设计目标；门禁只声明设计结构一致，不能把候选 SLO 写成已实现可靠性。

## H01–H12 的实施映射

| 控制 | 计划实现位置 | 关键验收 oracle |
|---|---|---|
| H01 | src/host/auth.py、src/adapters/booking.py | 跨租户数据与后端调用数均为 0 |
| H02 | src/runtime/operations.py、src/adapters/booking.py | 同 request_id 唯一预约；异 payload 拒绝 |
| H03 | src/domain/proposals.py | 改时间/过期/未授权方案占用数为 0 |
| H04 | src/runtime/operations.py、src/workers/reconcile.py | 远端已成功丢响应后最终匹配唯一 receipt |
| H05 | src/host/sessions.py | reset 后 generation 不复活；并发事件不丢 |
| H06 | src/ui/registry.py、src/web/events.ts | 断流不生成可写 final；成功必须匹配 receipt |
| H07 | src/domain/evidence.py | 超 TTL/设备停用强制重读并拒绝旧方案 |
| H08 | 不适用：无长期 memory | future 启用需重新评审，不能沿用此豁免 |
| H09 | src/runtime/budget.py | 挂死工具有界终止/unknown，预算超额无派发 |
| H10 | src/host/intent.py | 模型伪造授权/ID/结果不能导致越权或假成功 |
| H11 | tests/eval_booking.py | 真实状态 oracle + 相同任务人工计时 |
| H12 | src/runtime/audit.py、src/web/fallback.ts | 操作可追踪、无模型仍能走受控表单 |

上表路径只是实现计划；当前没有对应代码和测试，未取得任何 implementation/release 证据。

## 写入启用的明确前置条件

需得到并用合同测试验证：后端按 client_request_id 幂等、查询最终/未决结果、相同设备区间原子冲突规则。
若只有原子占用而没有幂等查询，项目仍可完成只读原型；写入启用被阻塞，不以本地表伪装解决。
需对接设备修订/规则条件检查，确认“停用”的线性化边界；与占用不在一事务时按后端条件接口补足。
需确认 SSO claims、园区管理员管辖关系和组织真实预约政策；设计暂不批准强制调度。
需实施持久数据库/备份、真实数据集/人工基线和模型版本选择；本次不进行这些外部操作。
