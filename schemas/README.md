# 应用层模型 schema

`application.schema.json` 是工具包建议采用的 **自定义应用协议**，不是 AG-UI 官方事件/字段，也不是已验证的生产协议。它把 [应用数据契约](../skills/agui-design/references/data-contracts.md) 的结构部分写成 JSON Schema Draft 2020-12。已有项目可保留等价模型，并证明对应不变量。

它不替代已有 `contract.schema.json`（设计/验收合同）或 `result.schema.json`（检查结果），也不改变它们的格式。Service desk 示例是独立、精简的领域演示，未宣称已经逐字段实现这里的建议协议。

## 定义与用法

十个主 `$defs`：`TrustedContext`、`EntityRef`、`Evidence`、`Intent`、`Proposal`、`Approval`、`Operation`、`Receipt`、`UIEvent`、`MemoryFact`。根 schema 的 `oneOf` 接受其中一种完整记录。推荐调用方按预期模型选择明确的 `$ref`，不要让对方自由选择模型类型。

辅助定义：

- `EpochMilliseconds`：UTC Unix epoch 整数毫秒，显式使用 UTC，最大值为 JavaScript 安全整数。示例各 `created_at`、`expires_at` 等使用这一表示；与“带时区时间戳”有相同的绝对时间语义。项目也可另行选择带偏移的 RFC 3339 字符串，但必须明确转换规则，不能混用秒/毫秒。
- `MoneyMinorUnits`：整数 `amount_minor`、显式三字母 `currency`、`minor_unit_exponent`；例如 12345/USD/2 表示 USD 123.45。币种实际存在、币种位数、业务正负范围、舍入与溢出仍由服务验证。
- `DomainPayload`：唯一有意开放的对象扩展点。`snapshot`、`constraints/limits`、`before/after`、确定性 patch、`execution_payload`、UI payload、结构化 memory value 引用它。必须再应用 `domain_schema_ref` 指向的领域 schema，以及业务语义检查；开放不代表任意字段已可信。

其余协议对象与嵌套 envelope 都使用 `additionalProperties: false`。实体版本接受服务器分配的非负整数或不透明字符串/ETag；它不是时间，也不是授权凭据。引用中的重复 tenant、version 必须在服务端核对一致性。

## 结构上拒绝什么

- 缺必填字段、未知协议字段、错误类型、非整数金额、非法状态枚举。
- `Operation.state=unknown` 携带 receipt 引用；unknown 必须提供结果未知的错误信息和恢复策略。
- `Receipt.outcome=unknown`；应保留为 operation 的未知状态，而不是签发成功收据。已确定失败的 receipt 可用 `outcome=failed`，此时 `committed_at=null`。
- `UIEvent.business_status=committed` 缺少 operation/receipt 引用，或不是已验证的 final。一个合法 final 仍可只是 preview/pending。
- memory 删除 tombstone 仍携带活跃 value，或没有删除时间。`revision`、`expected_revision`、`purge_generation` 为人工纠正、删除与在途提取提供并发前置条件。

**JSON Schema 不知道当前时间和权威数据库状态。** `expired`、`rejected`、`revoked`、`unknown` 记录本身可以结构合法；结构合法不允许执行它们。权限布尔值/permissions 列表、authority 字符串或有效格式的 hash 都不能靠通过 schema 获得可信来源。

## 样例与可复验命令

`application-examples.json` 为全部 13 个 `$defs` 提供正常与结构非法值，还提供 13 个**结构合法但必须由服务判定**的案例：过期上下文/证据/提案/批准、跨租户引用、仅起草意图、拒绝/撤销、未知提交、未验证来源的 receipt、partial/final 展示，以及人工删除 tombstone。`as_of_epoch_ms` 是过期案例的固定判定时间。

在插件目录，用已安装 `jsonschema` 的 Python 运行：

```sh
python3 - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator

schema = json.loads(Path('schemas/application.schema.json').read_text())
examples = json.loads(Path('schemas/application-examples.json').read_text())
Draft202012Validator.check_schema(schema)
assert set(schema['$defs']) == set(examples['definitions'])

def validator(name):
    return Draft202012Validator({
        '$schema': schema['$schema'], '$defs': schema['$defs'],
        '$ref': '#/$defs/' + name,
    })

for name, case in examples['definitions'].items():
    v = validator(name)
    v.validate(case['valid'])
    assert list(v.iter_errors(case['invalid'])), name

for case in examples['semantic_cases']:
    validator(case['definition']).validate(case['instance'])

print('13 valid accepted; 13 invalid rejected; 13 semantic examples structurally valid')
PY
```

正常样例的 `agui-example-json-sorted-v1` hash 算法仅用于这些没有浮点数的 JSON 值：按键排序、紧凑逗号/冒号、UTF-8、保留非 ASCII 字符后计算 SHA-256，并加 `sha256:` 前缀。Proposal hash 输入是整份正常 Proposal 去掉 `proposal_hash` 与可变 `status`；operation `payload_hash` 输入是正常 Proposal 的 `tenant_id/intent_id/proposal_id/proposal_hash/execution_payload`，再加正常 Intent 的 `principal_id`。Receipt 与 Operation 引用同一 payload hash。这不是对所有语言/数值的通用 canonical JSON 标准；项目必须版本化并共同实现自己的 canonicalization 规则，或采用合适的正式标准。

## 必须在服务/数据库实现并测试的部分

1. 可信 host 身份来源、当前授权、租户/主体隔离、批准撤销及审批界面实际展示内容。
2. 当前时间比较、expires/retention 的区别、实体版本/ETag、Evidence 重读与引用一致性。
3. canonical payload 与 hash 实际一致；批准的内容就是将执行的内容。
4. tenant + idempotency key 的唯一性、同键异内容冲突、合法状态转换、未知结果恢复和并发执行。
5. receipt 真实存在、由权威服务产生且对应本次 operation；同库事务原子性或外部 API 幂等/查询/对账。
6. UI 去重、sequence/revision、迟到事件和断线恢复；领域 final payload 校验以及安全渲染。这里没有把 partial 当最终领域 payload。
7. memory 写入许可、revision 与 purge_generation 的原子条件写、人工修改优先级、tombstone 保留时间、缓存/索引清理。写入时的 `expected_revision` 不能通过 schema 与数据库现值比较。

本次验证仅证明 schema 自身符合 Draft 2020-12，以及样例通过/拒绝符合预期；不验证领域 schema 是否存在或正确、授权、业务约束、原子性、负载、模型表现或生产安全。
