# Service desk：工单优先级变更示范

这是本项目编写的非电商领域示范，沿用 `research/reliability-audit` 的本地事务实验思路。它演示如何把 agent 提案、宿主审批、业务写入与 UI 状态分开，不是完整框架，也不是对 commerce-agents 的生产补丁。

仅需 Python 3.10+ 标准库；不使用模型、网络、第三方包或真实工单服务。

```sh
cd examples/service-desk
python3 adapter.py
```

从插件目录运行并保存机器可读证据：

```sh
AGUI_EVIDENCE_OUTPUT=/tmp/agui-service-desk-evidence.json \
  python3 examples/service-desk/adapter.py
```

适配器执行真正的 unittest 断言，读取独立 SQLite 连接验证业务状态，并输出：

```json
{"schema_version":1,"cases":[{"id":"duplicate_commit","status":"passed","detail":"..."}]}
```

实际输出包含全部 14 个定义的 case。指定 `AGUI_EVIDENCE_OUTPUT` 时也会向该路径写同一份 JSON。任一断言、测试准备或执行出错，case 标记为 failed、进程非零退出。没有预填 pass，也不会将异常吞掉算成功。

## 业务与可信边界

工单优先级为整数 1–4，1 最紧急。业务流程为：

`宿主身份 → 读工单并签发 Evidence → 提案 → 已验证预览 → 宿主批准确切 hash → 提交 → 持久 receipt → UI committed`

- `domain.py`：`TicketStore` 内所有业务方法从宿主提供的 `Actor` 推导 tenant，不接受模型指定的 tenant。读、提案、批准、执行分别检查权限。
- Evidence 由服务端存储，绑定读者、工单版本和 60 秒有效期。提案与提交都会检查新鲜度；旧版本不能静默重建提案后套用旧批准。
- 提案内容 hash 绑定 tenant、操作者、工单、旧版本、变更前后优先级与 Evidence。此例只有同一操作者批准和执行，不实现多级审批或职责分离。
- 每次真实用户意图由宿主生成持久 operation ID；同一次重试沿用，同一 ID 换内容会拒绝。一次本地事务内执行条件 UPDATE 并保存 receipt；同键重试返回原 receipt。
- `ui.py` 是每个交互单独创建的小型 reducer。partial 不可审批；validated 从后端提案生成；只有与持久 operation 存储完全匹配的 receipt 才能进入 committed；未完成的断流进入 interrupted。终态不被同次交互的迟到帧覆盖。

**Actor 是信任边界输入，不是认证实现。** 真实宿主必须先完成认证、tenant 授权和角色解析，再构造它；不要从浏览器或模型 JSON 直接反序列化 Actor。`seed_ticket`、原始 SQLite 连接、`fault` 和 `defect` 都是内部/测试入口，不能暴露为模型工具。

## 验收与负控

case ID：`tenant_isolation`、`unauthorized_write`、`duplicate_commit`、`changed_payload`、`stale_proposal`、`unapproved_proposal`、`rollback_gap`、`lost_response`、`concurrent_duplicate`、`partial_disconnect`、`receipt_required`、`stale_evidence`、`approval_payload_bound`、`ui_terminal_state`。

必须确认有意破坏实现时，原断言会发现问题：

```sh
python3 adapter.py --inject-defect skip_idempotency_replay
python3 adapter.py --inject-defect allow_unreceipted_commit
```

两条命令都应非零退出。第一个开关在真实业务实现中跳过 receipt 重放，重复提交/不同内容/回包丢失/并发用例会失败；第二个在真实 reducer 中允许无 receipt 收尾，`receipt_required` 应失败。开关不修改测试期望，也不伪造 evidence。不要在正式适配器集成中设置这些开关。

## 已证明与未证明

正常执行证明这些明确定义的本地例子满足断言：同库事务回滚、两个真实连接竞争、关闭重开连接后的成功回执恢复，以及部分 UI 输出的收尾。它们不是模型质量、生产认证、跨服务事务、所有线程调度或断电恢复的证明。

事务只覆盖同一个 SQLite 数据库。`lost_response` 在 commit 后注入回包异常，调用者得到 `UnknownOutcome`，通过原 operation ID 查询/重放恢复；不能把超时当作“肯定未写入”。对外部工单 API，必须使用对方的幂等键/版本条件、持久 operation 状态和对账；若对方没有这些能力，需要明确人工恢复或补偿策略，不能宣称 exactly-once。

上线还需宿主认证与权限撤销、正确租户边界、审批界面展示、生产存储与迁移、日志/隐私、异常监控和领域业务规则。此示范不增加无人要求的整套基础设施。

## 接入本包门禁

此目录的 `.agui/contract.json` 是完成的 **reference** 契约，声明已覆盖的 H01/H02/H03/H04/H06/H07；H05/H08/H09/H10/H11/H12 超出组件范围。不是完整 Agent 应用，不应把关掉这些能力作为真实应用绕过门禁的办法。

从插件根目录执行（解释器先安装根目录 requirements.txt）：

```sh
python scripts/harness.py --project examples/service-desk run
python scripts/harness.py --project examples/service-desk gate --stage implementation
python scripts/harness.py --project examples/service-desk gate --stage release
```

前两项应通过，最后一项应被阻止。全部6类设计在本组件参考中集中于本README；完整应用需要六类设计的实际业务决策，不能照抄该范围声明。

`schemas/` 展示可供Host工具包装器使用的输入/输出；Python业务方法额外接收可信Actor与operation ID，由宿主注入。此例未提供HTTP/模型工具server或浏览器组件，`UIReducer`验证服务端状态约束，不能当作前端端到端验收。
