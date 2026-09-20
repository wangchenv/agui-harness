# 运行与运营

## 预算与资源
按任务类型定义 deadline、工具超时、并发、调用量、输入/输出大小和总费用（币种/计价版本）；子任务共享预算。

## 持久化与恢复
定义 session turn lease、append事件、operation/receipt原子边界、outbox、unknown查询、恢复队列、任务撤销和启动恢复。

## SLO与观测
按成功业务任务记录成功率、延迟、审核时间、返工、成本；trace关联tenant/session/turn/operation，日志最小化敏感内容。

## 故障操作手册
列出限流、后台不可用、未知写结果、证据陈旧、质量下降的处置与降级；明确告警责任和恢复条件。
