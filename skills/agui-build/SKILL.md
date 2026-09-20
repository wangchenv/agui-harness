---
name: agui-build
description: 按领域契约实现 Agent 业务应用的受控工具、持久执行、生成式组件、流式恢复及预算；不把自然语言流程当作业务状态机。
---

# 实现受控 Agent 与组件式 UI

先读取 `.agui/contract.json` 和已有业务设计。没有设计时只补足影响本次实现的决定，按 [design](../agui-design/SKILL.md) 生成必要契约；不无限扩展架构。

## 实现路径

1. 定义一条最小完整旅程的最终状态断言；测试直接调用真实实现，并读取独立业务状态。为高影响不变量加入提交/回包/断流等故障点。
2. 先实现领域 adapter、持久操作记录、权限/租户、版本/批准、幂等与未知状态；再接模型工具。页面按钮与模型调用走同一业务服务。
3. 依 [runtime](references/runtime.md) 实现 turn/session 的并发、取消、持久恢复和共享预算；把每个工具结果独立持久化，不能等待模型流或整批工具结束。
4. 依 [交互规范](references/interaction.md) 实现组件 registry、输入 schema、服务端补全、完整校验、三个状态机和重连。关键事实从后端获取，解释文本不能改变成功状态。
   遵循 [agui-ui](../agui-ui/SKILL.md) 产出的DESIGN/tokens/组件清单，实际打开桌面、平板、移动界面验证；设计变化更新契约，不在实现时悄悄回到通用聊天页。
5. 接模型适配器、按需技能和只读委派。固定工具与角色授权；不要直接执行模型生成的任意代码或把长期记忆作为权限来源。
6. 写项目自己的测试 adapter，输出 [result schema](../../schemas/result.schema.json) 到 AGUI_EVIDENCE_OUTPUT；在 contract.checks 登记真实命令与 case。adapter 应复用现有测试框架，不能只打印 pass。
7. 审阅将运行的命令和被调用文件后运行 harness run，再执行 implementation gate；修复失败并更新 STATE/HANDOFF。对关键路径加入一个已知错误实现的负控，确认原测试会失败。

## 变更纪律

- 适配已有存储和架构，不默认引入微服务、图数据库、工作流平台或多 Agent。
- stable operation_id 由宿主维护，同一意图重试沿用；模型 tool_call_id 不等于业务操作身份。
- 本地事务只覆盖同一业务原子边界；远端提交不明进入 unknown。不得交换两行记账顺序就宣称分布式问题解决。
- 无关读取可以并行，依赖写需要按流程顺序；eager 只在持久记录与恢复机制已成立时用于写。
- schema/版本/权限变更需考虑已有 proposal、事件和 receipt；旧批准不能自动用于新方案。
- 快速反馈不能伪装最终完成；失败时保留可靠的恢复入口，不重放原聊天来盲目重做操作。

参考 [SQLite 工单示例](../../examples/service-desk/README.md) 了解控制机制，不把其中测试开关或 trusted Actor 构造直接暴露为工具。

新建单库应用可按 [Runtime 接入约束](../../docs/RUNTIME.md) 复用 `agui_runtime`，为每个领域实现 validate/apply 和当前授权函数，并把复制的模块纳入目标源码快照。外部 API 写入不能放入其 SQLite handler；跨系统流程仍按运行规范单独设计。不同人员审批不属于这个版本的默认 Actor 绑定能力。

验收交给 [verify](../agui-verify/SKILL.md)。只有本地测试时准确报告范围，不宣称真实模型或生产效果已验证。
