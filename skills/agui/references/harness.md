# 本地契约与证据 Harness

CLI 位于 `scripts/harness.py`；依赖 Python 3.10+ 和 `requirements.txt` 中的 jsonschema。目标仓库和插件位置可以不同，`--project` 始终指向目标仓库。只在明确选择 `run` 时执行项目测试程序；init/lint/gate/status/handoff 不调用模型或外部业务。

## 文件与阶段

```text
<target>/.agui/
  contract.json       机器可检验的领域设计与检查声明
  design/*.md         可引用已有文档替代
  schemas/*.json      工具与组件输入输出
  STATE.json          目标、决策、待办；仅用于接续导航
  HANDOFF.md          当时的门禁摘要；恢复工作时必须重新计算
  evidence/*.json    harness生成的运行凭证
  evidence/*.log     adapter输出；避免写入凭证/客户数据
```

- `init` 不覆盖已有 `.agui`；产生 draft，没有预填通过证据。
- `lint` 检查契约/schema/引用/工作流/控制映射一致性，不执行代码。原样设计模板会被拒绝，但修改几个字也不能代替人工设计判断。
- `gate --stage design` 与上述范围相同；允许声明尚待实现的源码路径，不表示实现已验证。
- `run` 默认运行 deterministic/recovery。先审阅声明的命令和adapter，需在隔离测试数据上执行。
- 有UI设计时也运行ui类浏览器检查；颜色/token声明检查不能替代它。
- `run --check <id>` 选一组；model_eval/load 还需 `--include-live`。此开关是防误触，不是付费、压测或外部业务授权。
- `gate --stage implementation` 要求适用的确定性控制有当前源码证据；H11留给真实评测。
- `gate --stage release` 还要求 application 范围、真实模型/负载/恢复、版本绑定及指标门槛。只是证据准入，不执行部署，也不是生产认证。
- `status` 列出三层门禁；`handoff` 将同一摘要写入交接文件。缺失上下文应查 STATE 与当前代码，不凭交接摘要沿用旧 PASS。

调用格式：

```sh
python /path/to/agui-harness/scripts/harness.py --project /path/to/target init --id service-desk --domain "IT工单协作"
python /path/to/agui-harness/scripts/harness.py --project /path/to/target lint
python /path/to/agui-harness/scripts/harness.py --project /path/to/target run
python /path/to/agui-harness/scripts/harness.py --project /path/to/target gate --stage implementation
python /path/to/agui-harness/scripts/harness.py --project /path/to/target handoff
```

`blocked` 返回非零；status/handoff 只是报告，返回0不代表内部门禁通过。CI 必须调用 gate。

## contract.json

精确字段见 [contract schema](../../../schemas/contract.schema.json) 和 [草案模板](../../../templates/contract.json)，不要凭文档补造字段。

| 字段 | 含义 |
|---|---|
| project.scope | reference 仅组件示范；真实应用用 application，reference 永远不能 release |
| features | 实际具备 writes/sessions/memory/ui/external_writes；禁用标记不能用来掩盖已存在能力 |
| source_paths | 快照范围，覆盖相关源码、adapter、fixtures、prompt、schema、配置及依赖锁文件 |
| design | 六份设计文件，可直接映射现有文档 |
| entities/tools/workflows/components | 权威源、闭合参数schema、权限、工具风险、状态迁移、关键字段来源 |
| ui_design | UI应用必需：spec/tokens/inventory/prototype；design时可计划prototype，implementation时必须存在 |
| budgets | 声明整轮和工具预算；检查器只验证声明，运行时强制需实现和测试 |
| controls | H01-H12 适用性、理由、实现位置、测试cases |
| checks | id/kind/command/inputs/timeout_s/cases；同一case只能有一个owner |
| release | 业务校准门槛和精确 model_version/dataset_id/baseline版本ID |

`checks.command` 是 argv 数组，不经过shell。`{python}` 会替换为运行harness的Python。适配器和显式脚本参数必须在 inputs 中；inputs文件必须进入source_paths。imports、动态插件、包依赖不能仅靠argv自动发现，评审者必须把相关依赖/锁文件列进快照。调用外部测试工具时记录其依赖版本，不声称本地快照覆盖远端系统。

所有路径相对 target，禁止越界。生成目录/文件不允许符号链接。快照忽略 `.git`、`node_modules`、常用venv/cache、`.agui/evidence`、STATE、HANDOFF；不要把业务实现放进忽略目录。最多20,000文件/100MiB，monorepo按受审查组件缩小范围。

## 必需案例与检查类型

| 控制 | 适用条件 | 必需 case IDs |
|---|---|---|
| H01 | 总是 | tenant_isolation；有写时 unauthorized_write，否则 unauthorized_read |
| H02 | writes | duplicate_commit, changed_payload, concurrent_duplicate |
| H03 | writes | stale_proposal, unapproved_proposal |
| H04 | writes | rollback_gap, lost_response；外部写另加 unknown_outcome, reconciliation |
| H05 | sessions | session_conflict, session_revocation |
| H06 | ui | partial_disconnect；有写另加 receipt_required |
| H07 | 总是 | stale_evidence |
| H08 | memory | memory_delete, memory_order |
| H09 | application | tool_deadline, concurrency_budget |
| H10 | application | denied_intent, false_success |
| H11 | application | task_quality, operator_efficiency，只能归属 model_eval |
| H12 | application | audit_trace, degraded_mode |

有ui_design时H06还必须包含responsive_layout、keyboard_navigation、ui_state_recovery，且这些案例归属kind=ui，context.execution_mode=browser。H11以外的硬控制由deterministic/recovery测试验证，H06也可由ui类真实浏览器验证。可以增加cases，但不能删除必需案例、重复owner、把skipped当passed，或用任意 live_probe 替代真正的任务质量测试。自然语言场景和oracle见 [故障矩阵](../../agui-verify/references/failure-matrix.md)。该表是最低检查，不是完整威胁覆盖；业务特有不变量继续增加。

UI设计使用 [tokens schema](../../../schemas/ui-tokens.schema.json)、[inventory schema](../../../schemas/ui-inventory.schema.json) 与 `scripts/ui_audit.py --tokens ... --inventory ...`。它检查声明的颜色对比度、token结构、组件/屏幕引用和未完成状态的写操作。它不计算实际DOM样式，不验证布局、屏幕阅读器或完整WCAG；这些由浏览器与视觉/可用性review验证。

## Adapter协议

参考 [可执行工单适配器](../../../examples/service-desk/adapter.py)。每次run生成唯一的临时输出文件路径，通过环境变量 `AGUI_EVIDENCE_OUTPUT` 传入；`AGUI_PROJECT_ROOT` 为目标目录。adapter必须真实调用实现并运行断言，向该文件输出 [result schema](../../../schemas/result.schema.json)：

```json
{"schema_version":1,"cases":[{"id":"duplicate_commit","status":"passed","detail":"两次调用后独立数据库读取显示version只增加1"}]}
```

- 必须报告合同中的全部且仅有那些case，ID不可重复；状态只能passed/failed/skipped。
- 任何失败/跳过、非零exit、超时、缺文件、畸形JSON或运行中源码变化，都阻止证据成功。
- adapter返回0但没有断言不能证明业务正确。负控必须证明重要断言能识别错误实现。
- 运行失败先撤销旧证据，避免失败后仍沿用旧PASS。运行日志写磁盘，adapter需约束日志量与敏感内容。
- 同一check由独占锁串行，防止并行运行覆盖证据。硬终止可能遗留`.lock`；只有确认记录的运行已经停止后才能移除，不能为获得PASS盲目删锁。
- 超时会终止进程；POSIX会杀同组子进程，Windows仅直接子进程，Windows adapter须另行管理子进程或在容器执行。

其他kind增加context：model_eval的execution_mode=live_model并提供精确model_version、dataset_id、baseline_version；load为load，recovery为recovery。一个scope的版本变化会使所有旧证据失效，本版不做细粒度依赖图优化。
ui使用browser；必须真实启动目标实现并验证DOM/键盘/断流等路径，不能只读取tokens或生成截图文件名。屏幕和交互目标见 [UI设计Skill](../../agui-ui/SKILL.md)。

## 发布指标

真实model_eval需要metrics：sample_size、task_success_rate、human_time_reduction、rework_delta、cost_per_success。load需要sample_size、p95_latency_ms。模型/数据集/基线版本必须与contract.release精确匹配。

- task_success_rate：成功任务数÷任务总数，范围0..1。
- human_time_reduction：1−新流程每任务主动人工耗时÷基线耗时；50%写0.5，允许负数表示更慢，不得大于1。
- rework_delta：新返工率−基线返工率，范围−1..1。
- cost_per_success：模型、工具、基础设施、人工审核和返工总成本÷成功任务数；计价单位在evaluation设计中指定。
- p95_latency_ms：完整旅程的第95百分位毫秒数；不要替换成首token时间。
- sample_size并不自动证明统计功效；还要按场景分层、重复运行、给出失败类别和置信区间。

模板阈值只是演示起点，未经业务校准不能作为承诺。本地门禁不验证实验设计是否科学，也不会独立证明adapter真的调用了所声称模型；可信CI、代码评审及运行账单/trace共同提供来源证据。
设计阶段允许透明的planned/unselected模型与数据集标识；实现真实评测前必须选定实际版本与基线，不得把计划标识包装成已验证后端能力。

## 防陈旧与信任边界

运行凭证绑定合同哈希、source_files内容哈希、harness/schema实现哈希、命令、退出码与时间。gate重新读取result并检查cases、kind、模型版本和指标，原始result不能直接充当运行凭证。

这能发现意外漏跑、陈旧结果和范围不一致，不能抵御能改写所有源码/证据的仓库管理员。需要更强保障时在可信CI保存不可变工件、限制写权限并审计运行身份。本工具不提供签名证明或远端部署认证。
