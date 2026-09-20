# AGUI Harness 0.1.1 验证记录

日期：2026-09-20。这是工具包的实现与示例验证，不是生产应用的质量认证。当前交付为工作区插件源码，未安装、发布或部署。

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
