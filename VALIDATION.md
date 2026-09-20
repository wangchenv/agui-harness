# AGUI Harness 0.2.0 验证记录

日期：2026-09-20。验证对象是工具包和受控示例；真实应用服务质量仍需目标环境证据。

| 检查 | 实际结果 |
|---|---|
| Python 自动测试 | 71 个通过。包含 SQLite 原子性、越权拒绝、批准内容绑定、过期/撤销、并发幂等、丢响应重放、失败回滚、模型评测边界及原始证据篡改。 |
| 核心验收脚本 | `python scripts/check_all.py`：12 项验收通过；预期失败通过断言核对，不以退出码非零直接算负控成功。 |
| 两个领域复用 | 库存扣减与会议室预约复用同一个 Runtime；直接查询数据库核对业务效果。 |
| 自动真实浏览器 | `python scripts/check_all.py --browser`：正常场景 3/3 通过；覆盖 1440/768/390/320 宽度、键盘确认与焦点恢复、生成中断和未知结果核对。每例产生截图及 Playwright trace。 |
| 四类故障负控 | 工单禁用幂等、无回执提交、预约允许冲突、UI 中断后错误开放写入口，均触发原有断言失败。 |
| 离线模型评测 | 逐样本输出和证据可生成；task_quality / operator_efficiency 按预期 skipped，不能通过真实质量发布门。 |
| 原始证据绑定 | UI / model_eval 必须引用真实文件和 SHA-256；缺失或篡改后 gate 拒绝。 |

Python 实测 3.12.13、jsonschema 4.26.0；浏览器实测使用 Playwright 1.62.1 和本机 Chrome。CI 使用锁定的 npm 依赖安装 Chromium；远程执行结果以对应 commit 的 Actions 为准。

复验：安装 `requirements-ci.txt`，执行 `python scripts/check_all.py`；浏览器测试先 `npm ci --ignore-scripts`、`npx --no-install playwright install chromium`，再执行 `python scripts/check_all.py --browser`。日志与原始文件保存至 `.agui/evidence/`，不随源码包分发。

## 本版尚未证明的能力

- 没有真实模型调用、真实人员配对基线、生产负载或可用性 SLO 结果。不能声称业务成功率或效率已提升。
- Runtime 保证只覆盖可信 handler 使用同一 SQLite 连接的事务；宿主认证/授权、远程写入、分布式一致性和业务审批分权需单独实现。
- UI 自动化验证交互原型，不代表真实后端集成、视觉设计品质或完整无障碍合规。
- CI 工作流已提供；强制合并保护需管理员配置并核对。SSH 推送权限不等于管理 API 权限。
- 旧版本 UI / model_eval adapter 需补原始 artifacts 后重跑；原会议室应用的 0.1.1 证据不能直接作为 0.2 发布证据。

---

# AGUI Harness 0.1.1 验证记录

日期：2026-09-20。这是工具包的实现与示例验证，不是生产应用的质量认证。以下保留 0.1.1 当时的验证范围；安装和发布状态以最新版本交付记录为准。

## 已执行

| 检查 | 结果与范围 |
|---|---|
| Python 自动测试 | `python -m unittest discover -s tests -q`：40 个测试通过。覆盖证据绑定、失败撤销、过期/篡改结果、进程失败、锁、路径、控制映射、UI 声明及 schema。 |
| 跨项目调用回归 | 会议室应用实用中发现带 `..` 的插件入口无法生成engine hash。0.1.1规范化脚本路径；新增真实子进程CLI回归，从目标项目目录调用工具并运行adapter。 |
| 应用 schema | 上述测试包含 13 类有效/无效结构样本；另有 13 个“结构合法但业务应拒绝”的样本，明确留给领域校验，不冒充运行时已验证。 |
| Plugin / Skills | plugin-creator manifest validator 通过；skill-creator quick validator 检查全部 5 个 Skills，通过。 |
| 工单真实实现适配器 | 14/14 通过；读取 SQLite 结果并独立断言。lint、run、implementation gate 通过。 |
| 负控一：禁用幂等重放 | 非零退出；duplicate_commit、changed_payload、lost_response、concurrent_duplicate 真实失败。 |
| 负控二：允许无 receipt 完成 | 非零退出；receipt_required 真实失败。 |
| 工单发布门 | 按预期 blocked：reference 不能发布，且缺真实模型、负载和应用恢复证据。 |
| UI 静态审计 | tokens 与 component inventory 模板通过；低对比、缺失/降级颜色对、未知组件、partial/unknown 写及无 receipt 写被测试拒绝。 |
| UI 原型状态测试 | Node 标准库执行页面原始脚本，5 组通过；stub DOM 范围，不称为浏览器测试。 |
| UI 真实浏览器 | 桌面、平板、390/320 手机宽度；批准、键盘焦点、生成中断、unknown 核对、用户视图和空结果通过本次人工检查；见 [具体记录](examples/ui-workbench/VALIDATION.md)。 |
| 跨场景前向试用 | 独立执行者仅按工具包指引产出设备预约设计：UI 静态审计、lint、design 通过；implementation/release 如实阻止 28 项未实现路径。见 [示例记录](examples/equipment-booking-design/VALIDATION.md)。 |

Python 实测环境为 3.12.13、jsonschema 4.26.0。要求为 Python 3.10+；未对所有支持版本、操作系统做兼容矩阵验证。Node 只用于可选 UI 状态测试。

## 如何复验

在插件根目录，用安装了 `requirements.txt` 的 Python：

```sh
python -m unittest discover -s tests -q
python examples/service-desk/adapter.py
python examples/service-desk/adapter.py --inject-defect skip_idempotency_replay
python examples/service-desk/adapter.py --inject-defect allow_unreceipted_commit
python scripts/harness.py --project examples/service-desk lint
python scripts/harness.py --project examples/service-desk run
python scripts/harness.py --project examples/service-desk gate --stage implementation
python scripts/harness.py --project examples/service-desk gate --stage release
python scripts/harness.py --project examples/equipment-booking-design gate --stage design
node examples/ui-workbench/test-state.cjs
```

两个负控与 reference release 应返回非零；不要把它们并进要求全零的成功命令链。示例运行证据属于生成物，不随分发包携带，解压后需重新运行。

## 不能从这些结果推出的结论

- 未调用真实模型，未测任务成功率、幻觉频率、真实并发/负载、生产恢复或人员效率。测试中合成的 live_model 元数据只用于检查门禁行为。
- Schema/颜色/状态声明正确不等于应用实际遵守；UI 界面检查没有覆盖完整可访问性标准。
- 哈希阻止陈旧证据，不证明可修改整个仓库的拥有者没有伪造 adapter 或运行数据。发布还需可信 CI、原始运行 trace、真实业务基线及运营验收。
- 设备预约是完整设计样例，工单是有限控制实现，UI 原型是本地交互参考；三者没有组合为一个已上线应用。

当前证据支持“工具可执行、核心门禁有正负验证、可迁移到另一个领域进行设计”。任何“稳定可控且更高效”的服务结论，必须由目标应用在实际风险、用户、模型和后端环境下提供新增证据。
