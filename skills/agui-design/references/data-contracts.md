# 应用数据契约与不变量

以下为 AGUI 工具包建议的**自定义应用模型**，不是 AG-UI 官方事件名或字段。
采用它们是设计选择；若项目已有等价模型，保留原命名并证明同等语义即可。
MUST=适用时必要；SHOULD=优先采用、偏离需说明；可选=按业务需要。
本文件不定义认证系统、运行框架或已验证的生产 schema。

## 所有持久记录的公共语义

| 字段/语义 | 要求 |
|---|---|
| `schema_version` | MUST 显式版本；持久记录升级不能默默改变历史语义 |
| `id` | MUST 服务端生成或验证、稳定、不可跨租户复用作授权凭据 |
| `tenant_id` | MUST 对多租户数据存在且来自可信 host；单租户可固定常量 |
| `created_at` | MUST 权威服务器时间，使用带时区时间戳 |
| 关联标识 | MUST 能连接 request、intent、proposal、operation、receipt；不要求全塞进每张表 |
| 保留与权限 | MUST 定义谁可读/写/删及保留周期；不能仅依靠不可猜 ID |

- MUST 将实体 ID 与访问权限分开；每次按 tenant + entity 解析与鉴权。〔H01〕
- MUST 金额用整数最小货币单位并显式 currency；资源量用整数或明确 scale/unit 的十进制。
- MUST 声明数量范围、舍入规则与溢出处理；禁止用二进制 float 承担资金不变量。
- SHOULD 使用服务器分配的实体版本/ETag；时间戳不能自动代替并发版本。
- MUST 区分 expiry（失效期限）、retention（保留期限）和 version（并发条件）。

## 1. Entity：业务对象引用及快照

必填语义：`entity_type`、`entity_id`、`tenant_id`、`version`、`authority`、领域字段及单位。

- MUST 指定 authority：真正拥有工单、账号或预约状态的服务，而非会话缓存。
- MUST 条件写使用当前实体版本；缺乏版本的外部系统要记录替代策略及剩余风险。
- SHOULD 只向模型暴露任务必要字段；密钥、后台凭证和权限令牌不得成为实体描述。
- 可选：软删除状态、外部来源 ID、display label；显示名称不可作为唯一写目标。

## 2. Evidence：读取了什么、在何时可据此判断

必填语义：`evidence_id`、`tenant_id`、`entity_ref/source_ref`、`source_version`、`observed_at`、`snapshot`、`provenance`、`validity_policy`。

- `provenance` MUST 记录工具/后端/查询及其关联调用；来源 URL 或“模型知道”不能替代后端证据。
- `validity_policy` MUST 表达失效条件；可为 expires_at、必须提交前重读、或来源明确不可变。
- MUST 区分后端事实、用户陈述、模型推断；推断不能被标成权威字段。〔H07〕
- MUST 缓存证据不授予权限；过期快照不得直接用于计算可提交变更。
- SHOULD 保存任务必要快照/摘要及可重读引用，而非无限复制敏感原始响应。
- 可选：引用片段、内容哈希、数据质量标记；哈希证明内容一致，不证明事实正确。

## 3. Intent：用户希望做什么，以及允许做到哪一步

必填语义：`intent_id`、`request_id`、`principal_id`、`tenant_id`、`source_message/action`、`requested_action`、`targets`、`constraints`、`authorization_scope`、`status`。

- MUST 保留用户原始动作来源与解析结果；模型解释不能覆盖原始要求。
- `authorization_scope` MUST 区分了解/建议/起草/提交，及目标、数量、金额、发送对象等边界。〔H10〕
- MUST 不从“这看起来不错”自动推出高风险提交权限；不从可访问资源推出可修改权限。
- SHOULD 用确定性选择和明确结构化字段解决关键歧义；仅在歧义会改变动作时提问。
- MUST 已有清楚授权可覆盖的低风险可逆动作不反复索要确认；新目标或扩大范围需重新判定。
- 可选：意图置信度只影响澄清策略，不能成为授权凭据或替代 policy。

## 4. Proposal：可审阅、不可悄悄变化的候选操作

必填语义：`proposal_id`、`tenant_id`、`intent_id`、`action_type`、`targets`、`expected_versions`、`before/after` 或确定性 patch、`preconditions`、`proposal_hash`、`policy_version`、`expires_at`、`status`。

- MUST 先标准化实际执行 payload，再计算内容 hash；hash 覆盖版本、数量、费用、收件人等重要条件。
- MUST 审批界面展示的是该 hash 对应内容；修改内容形成新版本/新提案，不静默更改批准对象。〔H03〕
- MUST 声明执行前需重读的事实、业务规则及可接受漂移；过期后不可自动延长原批准。
- SHOULD 把预计影响与确定变更分开：模型估计不能伪装为后端模拟结果。
- 可选：模拟输出、影响范围、补偿方案、审批成本；无须为纯读取创建 Proposal。

## 5. Approval：由谁以什么权限批准了哪个内容

必填语义：`approval_id`、`tenant_id`、`proposal_id`、`proposal_hash`、`approver_id`、`authority_ref`、`decision`、`approved_at`、`expires_at`、`scope`。

- MUST approver 与 authority 来自可信 host/审批服务，不接受模型/browser 传来的权限布尔值。
- MUST apply 时复核 hash、有效期、当前权限及撤销状态；批准不是永久通行证。
- MUST 审批被拒、过期或撤销后不能因重试恢复；批准内容变化必须重新审批。
- SHOULD 根据动作风险选择无需额外确认、一次确认或正式审批；别把所有读和可逆写都做成审批。
- 可选：双人审批、职责分离、外部工单号；策略要明确执行者能否与审批者不同。

## 6. Operation：跨重试仍是同一项执行

必填语义：`operation_id`、`tenant_id`、`idempotency_key`、`payload_hash`、`intent_id`、可适用的 proposal/approval 引用、`state`、`attempts`、`created_at`、`deadline`、`backend_operation_ref`、`last_error`。

- MUST durable key 在首次可能产生副作用前存在，并传到真正实施写入的后端。〔H02/H04〕
- MUST tenant + key 唯一；同 key 同 payload 返回原状态/receipt，同 key 不同 payload 拒绝。
- MUST 分开 logical operation 与 transport attempt；换网络连接或重试不能换操作身份。
- MUST 区分 `pending/running/succeeded/failed/unknown/cancel_requested`；业务可细化状态。
- `failed` MUST 表示确认未产生预期副作用或已有清楚失败结果；提交不确定必须用 unknown。
- `backend_operation_ref` MUST 在获得后保存；外部不支持查询时明确为空并记录人工恢复策略。
- SHOULD 不按参数哈希简单去重所有调用：用户可能合法要求再次执行相同动作。
- 可选：lease、fencing token、next_retry_at、reconcile owner；恢复竞争必须仍保证单操作语义。

## 7. Receipt：业务执行的可查询结果

必填语义：`receipt_id`、`operation_id`、`tenant_id`、`payload_hash`、`outcome`、`committed_at`、`resulting_versions`、`authority`、`result_ref`。

- MUST receipt 由执行/权威系统产生，模型或 UI 不能自行签发成功收据。〔H06〕
- MUST 本地写与 receipt 同事务提交；跨 API 使用外部幂等/查询结果建立可对账的记录。
- MUST 重试可找回原 receipt；仍处于 unknown 的操作不能生成成功 receipt。
- SHOULD 返回可给用户理解的结果摘要与可查引用；敏感业务内容按调用人权限裁剪。
- 可选：补偿 receipt；补偿是新操作，不删除原成功事实。

## 8. UIEvent：前端投影协议，而非业务真相

必填语义：`event_id`、`schema_version`、`tenant/session/run` 作用域、`sequence`、`component_id`、`event_kind`、`revision`、`payload`、可适用的 `operation_id/receipt_id`。

- 以上 MUST 明确为应用 envelope；映射到 AG-UI 时使用适配器，不声称官方存在这些字段。
- MUST 定义去重、顺序、revision 覆盖规则与可恢复游标；旧 partial 不得覆盖新 final。
- MUST 区分 provisional、final、error、cancelled、unknown；rendered 不等于 committed。
- MUST 断线后从 receipt/快照校正状态；撤销或失败后终结 pending 卡片。〔H05/H06〕
- SHOULD 最终 payload 严格校验，partial 用独立容错 schema；两者不能共用“已验证事实”标签。
- 可选：进度、推荐布局、输入 chips；点击动作仍经 Host 同一执行与权限边界。

## 9. Memory：允许长期保存的事实

必填语义：`memory_id/key`、`tenant_id`、`subject_id`、`value`、`category`、`source_ref`、`updated_at`、`expires_at/retention_policy`、`purge_generation`。

- MUST 保存类别有业务许可；凭证、付款信息与越权主体数据不能因模型建议而写入。
- MUST 读取按主体、租户、权限和有效期过滤；“长期记忆”不替代实时规则和用户当前明确要求。
- MUST 提取开始记录 generation，条件写入时原子检查 generation 未变；purge 同事务推进 generation。〔H08〕
- MUST 不能用“先查 generation、再无条件写”处理并发删除；两者之间仍有竞态窗口。
- SHOULD 支持查看、纠正、删除；删除后在途提取、重试、缓存不得复活旧事实。
- 可选：语义召回或加密分区；向量库也必须遵守同一删除和权限条件。

## 设计验收

- MUST 为每个模型提供一个正常样例和一个拒绝/过期样例，说明哪些字段可信 host 提供。
- MUST 验证数据库约束、服务层条件和序列化共同实现不变量，不只把字段写在 JSON Schema 中。
- SHOULD 对 schema 演进注明读兼容、迁移、旧 receipt 重放策略；不能重新解释旧批准。
- 状态迁移与恢复见 [workflows.md](workflows.md)；模块边界见 [architecture.md](architecture.md)。
