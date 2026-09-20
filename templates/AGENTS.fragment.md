## Agent 业务应用规范

对本仓库的 Agent + 组件式 UI 功能，读取 `<AGUI_PLUGIN_ROOT>/skills/agui/SKILL.md`，其中 `<AGUI_PLUGIN_ROOT>` 替换为实际工具包路径；普通页面任务不必套用。

- `.agui/contract.json` 记录设计契约；已有项目规范和用户授权保持有效。
- 模型文字、回合结束、部分卡片都不代表业务成功；真实写必须有服务端权限、意图范围、版本与幂等控制，以及可查询结果凭证。
- 验证使用目标代码和可信测试adapter，证据缺失/失败/陈旧不能声明已通过。
- 交接前更新 `.agui/STATE.json` 并运行 harness handoff；恢复时重算 status。
- 门禁通过不授予部署或外部业务操作权限。
