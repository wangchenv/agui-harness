# 跨业务 Agent 应用的模块边界

本文用于设计或重构业务 Agent；先确定要完成的任务，再选择所需模块。
本工具包提供 Coding Agent 的设计指导，不是运行框架，也不表示生成物已经适合生产。
**MUST** 表示适用场景下的必要不变量；**SHOULD** 表示允许记录理由后替代；**可选** 表示按需要采用。
这里的 AGUI 是本工具包的应用设计简称；自定义实体、状态和事件不是 AG-UI 官方协议字段。
如需对接 AG-UI，另建适配层并核对项目实际采用的官方协议版本，不据此文档猜测字段。

## 先确定系统边界

- MUST 写明角色、真实用户目标、可读取的数据、可执行的动作及禁止触碰的系统。
- MUST 指定业务权威系统：哪个服务决定工单状态、资源占用、价格或审批结果。
- MUST 区分只读建议、可逆写入、不可逆写入、外部发送及资金动作；采用各自的执行策略。
- SHOULD 从一个完整业务闭环开始，不因复用目标预先实现所有行业或所有模型 runtime。
- 可选：多角色、分析子 Agent、向量检索、长流程引擎；它们不是采用组件式 UI 的前提。

## 两种状态不能混为一谈

| 状态 | 典型内容 | 权威持有者 | 失效后的处理 |
|---|---|---|---|
| Runtime 知识状态 | 会话消息、已读对象、推理假设、工具结果、当前计划 | 会话服务、EvidenceStore | 可压缩或重建；重新读取必要事实 |
| 业务权威状态 | 工单负责人、库存、预算、预约、外部操作结果 | 业务后端、操作账本 | 依据版本、事务、幂等与对账恢复 |
| 用户交互状态 | 当前卡片、加载状态、筛选、未提交草稿 | 前端及宿主 | 从事件游标、业务快照和 receipt 恢复 |

- MUST 不把“模型说执行了”“卡片呈现成功”“会话记得批准”当成业务提交事实。〔H04/H06〕
- MUST 不把“读取过实体”当成写权限或持续有效的授权。〔H01/H07/H10〕
- MUST 让业务状态在会话被清理、断流、模型更换后仍可查询。
- SHOULD 把短期事实快照与长期偏好分别管理；历史文本不是操作账本。

## 推荐责任划分

| 模块 | 拥有的责任 | 不拥有的责任 | 主要接口 |
|---|---|---|---|
| Host | 身份、租户、请求接入、应用事件、审批入口 | 从模型参数接受身份权限 | SessionContext、TrustedPrincipal |
| Runtime | 模型循环、工具调度、取消、预算、记录恢复 | 判断业务提交是否生效 | ToolCall、ToolOutcome、RunState |
| Domain Pack | 领域实体、工具契约、提示词、skills、领域错误 | 另建绕过后端的业务真相 | DomainTool、EntityRef |
| Policy | 权限、意图范围、风险、版本和执行前条件 | 单凭 LLM 文本授予批准 | PolicyDecision、Approval |
| Business Adapter | 后端读写、幂等键、条件写、对账 | 无条件重复非幂等写 | read、prepare、execute、query_operation |
| Operation Store | 持久操作状态、receipt、重放和恢复 | 以会话消息代替提交记录 | reserve、transition、get_receipt |
| Presentation | 结构校验、服务端事实补全、组件事件 | 自由执行模型生成的代码 | PresentationSpec、UIEvent |
| Memory | 已许可事实的保存、读取、删除和保留 | 保存授权令牌、代替实时政策 | get、upsert、purge、generation |
| Observability | 关联请求、工具、操作、事件与成本 | 默认记录全部敏感输入 | TraceContext、Metric、AuditEvent |

小应用可将模块放在同一进程；MUST 保留责任边界，不要求微服务化。

## 依赖与一次请求的数据流

```text
UI / API → Host → Runtime → 受控工具执行器 → Policy → Business Adapter
                    │             │                       │
                    │             ├→ Operation Store ←───┘
                    └→ Presentation → UI 事件适配器 → 前端组件
                   Evidence / Memory 只提供上下文，不授予业务权限
```

- MUST 让写操作通过同一服务端执行边界；页面按钮和聊天工具不能各有一套较弱规则。
- MUST 在调用真实后端前解析可信身份、租户与资源权限。〔H01〕
- MUST 在可能产生副作用前登记稳定 operation ID；执行结果独立于模型流保存。〔H02/H04〕
- MUST 将工具结果区分为成功、确定未执行、被策略阻止、提交状态未知；禁止混成 unavailable。
- SHOULD 工具结果同时包含给模型的说明和给宿主的结构化状态，避免从自然语言猜执行结果。
- SHOULD 业务工具保留明确名字，如 `stage_ticket_assignment`，而非只有 `execute(action, payload)`。
- 可选：通过 MCP 或 HTTP 暴露工具；传输协议不能替代授权和幂等实现。

## 模型、Skill 与确定性代码

- MUST 把权限、数量、版本、批准、状态迁移等硬条件放进代码。〔H01/H03/H10〕
- MUST 假设模型可能漏读 Skill、选错工具、重复调用、构造错误参数、把失败解释成成功。
- SHOULD 用 prompt 承载高频行为规则、工具描述承载局部契约、Skill 承载按需流程知识。
- SHOULD 把模型用于意图解释、候选方案、分析和说明；执行器负责可判定的不变量。
- 可选：分析子 Agent 只获得完成分析必要的读工具与独立预算；其读取不自动扩展主会话的可写范围。
- MUST 在模型供应商适配时核实工具选择、流式参数、取消和错误语义，不能仅更换 model 字符串。

## 呈现与真实执行

- MUST 由服务端使用 Evidence/业务读结果补齐关键字段；模型只选择对象、结构和说明。〔H07〕
- MUST 校验完整 payload；未知组件、未知对象及越权对象不得进入可点击的执行界面。
- SHOULD 部分参数只生成 provisional UI；不得让 partial 卡片触发提交或被当作最终 receipt。
- MUST 最终业务状态来自 receipt/权威读取，不来自 `end_turn` 或模型“已完成”。〔H06〕
- MUST 为取消、超时、失败、unknown、流断连定义可见状态；不能永久停留 loading。
- 可选：渐进卡片、布局建议、快捷输入；自动执行快捷输入仍受原动作授权规则约束。

## 运行与持久化选择

| 条件 | 合适起点 | 必须补充的边界 |
|---|---|---|
| 只读、短任务 | 内存 runtime + 后端读接口 | 读权限、截止时间、证据新鲜度 |
| 单数据库写入 | 本地事务 + durable receipt | 幂等唯一约束、版本条件、批准绑定 |
| 外部 API 写入 | 操作账本 + 业务幂等键 + 查询 | pending/unknown 对账、重复投递恢复 |
| 多步骤跨系统 | 持久状态机/工作流 | 分步 receipt、补偿语义、人工接管 |
| 高并发会话 | 会话串行器或乐观版本 + 可合并事件 | 冲突重试、撤销 epoch、防止覆盖 |

- MUST 不把 SQLite 原型的单库原子性推广成跨 API exactly-once 保证。〔H04〕
- SHOULD 优先复用已有身份、审批、工单或工作流服务，不额外发明业务权威源。
- MUST 将端到端 deadline、工具并发、调用数量和费用限制作为独立预算。〔H09〕
- SHOULD 支持只读降级；不能用降级为由绕过写权限或复核。〔H12〕

## 公共控制 ID

| ID | 控制责任 | 设计时须回答 |
|---|---|---|
| H01权限与租户 | Host + Policy + Backend | 身份来源和每次资源级鉴权在哪里？ |
| H02操作幂等 | Operation Store + Backend | 重试如何找回同一操作，而不再次写？ |
| H03提案版本与审批 | Proposal + Approval + Policy | 批准绑定什么内容、版本、有效期？ |
| H04写入账本原子/对账 | Backend + Operation Store | 提交与记录之间失败时如何判定？ |
| H05会话并发撤销 | Session Store + Runtime | 并发事件怎样合并，撤销如何阻止晚写？ |
| H06UI终态与receipt | Presentation + Host | 断流重连后用什么证明执行结果？ |
| H07事实来源与新鲜度 | Evidence + Backend | 来源、版本和失效后重读策略是什么？ |
| H08记忆删除顺序 | Memory Store | 删除后在途提取为何不能写回？ |
| H09时间并发成本预算 | Runtime + Adapter | 谁限制排队、工具、总时长和费用？ |
| H10意图与坏模型边界 | Intent + Policy | 正确参数但错误意图的写如何被限制？ |
| H11评测效率 | Test Harness | 哪些风险用确定性探针，哪些用真实模型？ |
| H12可观测降级 | Observability + Host | 未完成、未知和降级如何定位与恢复？ |

## 设计交付物

- MUST 交付角色/动作范围、模块责任、权威系统、关键接口和错误状态，不只画调用链。
- MUST 对适用的 H01–H12 标注实现位置、缺口与验收；不适用项写理由，不伪造覆盖。
- SHOULD 描述正常、取消、重试、过期、并发五条关键路径，并附最少必要样例。
- 继续读 [数据契约](data-contracts.md)、[持久流程](workflows.md)；跨域形态见 [领域映射](../../../examples/domain-mapping.md)。
