---
name: agui
description: 为跨业务的 Agent + 组件式 UI 应用组织设计、实现与验证，读取持久契约并路由后续工作。用于 AGUI 智能业务应用或 commerce-agents 模式迁移；不用于普通静态网站。
---

# AGUI 开发 Harness

将模型放在受控业务接口之上，通过组件式 UI 完成真实任务。这里 AGUI 是应用模式简称，AG-UI 是可选的前后端事件协议；本包未实现或认证官方协议 adapter。

## 入口

1. 明确目标仓库，读已有 AGENTS.md/工程约定；不要替换已有身份、业务真相或研发流程。
2. 找 `<target>/.agui/contract.json`、`STATE.json`、`HANDOFF.md`。有记录先执行 status，不能把旧 PASS 当当前事实。
3. 新项目在目标目录运行 `python <plugin-root>/scripts/harness.py --project <target> init --id <lowercase-id> --domain <业务范围>`。只生成 `.agui`，不覆盖已有内容。
4. 依据用户目标选择下面一个入口；持续开发时依据缺失证据向前推进，不必每阶段重新询问已经给出的授权。

| 任务 | 读取 |
|---|---|
| 新场景、架构、数据模型、业务旅程、已有系统改造 | [agui-design](../agui-design/SKILL.md) |
| 信息架构、任务界面、视觉设计、tokens、响应式与可访问性 | [agui-ui](../agui-ui/SKILL.md) |
| 按已有设计实现工具、执行器、组件、状态与恢复 | [agui-build](../agui-build/SKILL.md) |
| 可靠性审计、评测、准入验证、回归 | [agui-verify](../agui-verify/SKILL.md) |

CLI 语义、证据边界与案例 ID 见 [Harness 合约](references/harness.md)。需要知道过去教训来源时读 [来源与决策记录](references/provenance.md)。不要一次性加载所有参考文档。

## 共同约束

- 用户任务决定范围；选择一个可验证的完整旅程，不自动增加支付、发送、部署或多 Agent。
- Host 注入真实身份；权限、批准、版本、幂等、额度、关键结果由确定性代码控制。
- 分离 turn、operation、presentation；模型结束和卡片完成都不能证明业务已提交。
- 有用户界面的应用在实现前完成 UI 设计，复用既有设计系统；自动颜色检查、真实浏览器测试、截图视觉review与实际用户效率分别提供证据。
- 缺失、跳过、陈旧或脚本化模型证据不能冒充真实模型质量；参考项目不能冒充完整应用。
- 每次交接更新 STATE 的 objective/decisions/open_questions/next_action，并执行 handoff。STATE 仅导航，门禁根据当前文件和证据重新计算。
- 本地工具包不授予任何外部操作权限；部署、发消息、扣费依用户既有授权处理。门禁 PASS 不等于部署批准。

## 与其他研发流程配合

已使用 SDLC、spec/plan 或其他工作流时，保留其主状态与项目结构，本包作为 Agent 应用领域规范与验收插件；引用已有设计/测试路径，不创建第二套互相矛盾的需求。没有这些流程时直接使用本包。永远不要仅因 skill 文档要求产物就擅自扩大用户的功能范围。
