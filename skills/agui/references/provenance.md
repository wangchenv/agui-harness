# 来源、修正与边界

本工具包在2026-09-20基于 commerce-agents 提交 [fd4d592](https://github.com/anthropics/commerce-agents/commit/fd4d59224ab96b43c6dc6888207c67b3bd5a24cf) 的源码研究和本工作区故障审计编写。

规范是本工具包提出的跨领域设计，不是 Anthropic 的官方产品保证，也不是对参考项目的生产补丁。示例代码是本工作区新编写的非电商控制示范。

| 参考机制/审计教训 | 保留或修正 | 对应控制 |
|---|---|---|
| 角色工具、按需Skills、业务backend | 保留；按新领域定义实体和工具，不给商品接口换名称 | 架构/数据规范 |
| 服务端补全组件字段 | 保留，增加事实TTL、关键字段与解释隔离 | H06/H07 |
| provenance gate | 不能替代身份权限、当前授权和业务版本 | H01/H03/H10 |
| stage→approve→apply | 增加准确内容hash、实体版本、批准有效期和原子提交 | H02/H03/H04 |
| eager执行和整批gather | 执行前登记、逐项持久结果，取消不抹掉已成功写 | H04/H09 |
| 超时后重复加购 | 稳定业务operation身份、原子去重与receipt、unknown对账 | H02/H04 |
| 流写回绕过CAS、reset复活 | 会话串行/明确冲突、事件追加、撤销epoch | H05 |
| partial被finally提升为final | 分开turn/operation/presentation，最终状态需权威事件 | H06 |
| 删除记忆被旧任务恢复 | 原子generation/key revision/tombstone、来源顺序 | H08 |
| 工具轮数不限制同轮fan-out | deadline、并发、调用量、token与费用独立预算 | H09 |
| 模型说成功但没有写 | receipt驱动成功状态；坏模型脚本验证执行边界 | H10 |
| demo看起来更快 | 真实任务、人工审核和返工基线衡量效率 | H11/H12 |

原审计保留于工作区 `research/reliability-audit/production-readiness.md`；发布工具包时不依赖该路径，以上摘要与随包规范已足够使用。38项现状探针复现的是故障/边界及对照，不是38个漏洞，也不是模型错误发生率。

AG-UI官方资料： [协议简介](https://docs.ag-ui.com/introduction)、[事件概念](https://docs.ag-ui.com/concepts/events)，于2026-09-20核对。协议处理Agent与前端的事件交互；本包的业务Operation/Receipt、权限、幂等和审批是应用层额外责任。不会从RUN_FINISHED推出业务已提交，未实现或声称官方协议兼容认证。

[Anthropic Agent评测说明](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)作为轨迹与结果评测的背景参考。规范中的门槛、case ID、harness和领域示例由本包定义，不冒充来源原文。
