# 运行时契约：执行边界、资源预算和可恢复状态

本文件规定业务 Agent 的运行时责任；不要求采用特定框架或固定多 Agent 拓扑。
先复用宿主已有认证、任务队列、业务服务和监控；只有缺少边界时才增加实现。
界面契约见 [interaction.md](interaction.md)，对抗验收见 [failure-matrix.md](../../agui-verify/references/failure-matrix.md)。

## 1. 模型请求不是业务事务〔H01、H10〕

宿主验证 caller 后创建 principal、tenant 和 session epoch；模型参数不得覆盖这些字段。
查询和命令分别适配后端；每次读取和写入都在数据源或策略层再次验证资源归属。
模型可提出工具调用，执行器负责 schema、能力、资源版本、预算和业务前置条件。
服务端凭证不进入 prompt、工具结果、事件或 UI；权限不得依赖 prompt 中的警告。
不把跨租户 ID 查不到与服务不可用混为一谈；对用户返回不泄露对象存在性的拒绝。
授权范围应尽量绑定动作与资源；一个成功查询不自动授予该资源的写权限。

## 2. 可追踪但不混用的标识

| 标识 | 范围与用途 |
|---|---|
| `session_id + epoch` | 会话身份与撤销代际；不是长期业务主键 |
| `turn_id` | 一次用户意图处理；重放事件不新建 turn |
| `operation_id` | 一次稳定业务命令；重试继续使用同一个 ID |
| `proposal_id + revision` | 建议与批准内容绑定 |
| `stream_id + seq / event_id` | 单流排序、去重和恢复游标 |
| `resource_revision` | 业务并发控制；不以模型生成时间替代 |
| `trace_id` | 关联诊断；不得充当鉴权凭证 |

以上是应用合约字段，接入 AG-UI 时按 adapter 明确映射或扩展，不冒充协议原生保证。
日志记录关联 ID 和状态变化，敏感载荷按字段脱敏；保留必要审计且限定访问期限。

## 3. 三类状态必须独立〔H04、H06〕

turn 记录 `running/completed/failed/cancelled`；它结束不等于业务提交。
operation 记录 `proposed/approved/executing/committed/rejected/failed/unknown/cancelled`。
presentation 记录 `partial/validated/final/interrupted/stale`；由服务端事实投影而来。
明确每条状态转换的授权者和证据，禁止任何模型文本直接把 operation 改为 committed。
命令已发送但没有可靠结果时进入 unknown；启动对账而不是释放幂等约束或自动重试。
confirmed failed 表示已确认未生效；业务部分完成必须有逐项状态，不能整体当作未执行。
取消是请求，不是结果；外部系统确认取消后才推进相应终态。

## 4. 命令执行路径〔H02、H03、H04〕

1. 接收稳定 operation ID，验证 principal、tenant、payload hash 和允许的动作。
2. 查幂等记录：相同载荷返回已知结果/进行状态；不同载荷拒绝，不能重新执行。
3. 校验 proposal revision、批准绑定、有效期和业务对象的预期版本。
4. 原子保留幂等键并写 executing 记录；重复执行者不能同时取得执行权。
5. 在业务事务中检查约束并提交；成功证据与执行记录尽可能同事务保存。
6. 外部系统无法同事务时使用 provider 幂等键、outbox/inbox 和结果查询实现收敛。
7. 根据权威结果生成 receipt；发布可恢复事件，不以 HTTP 200 或模型结尾代替提交证据。

幂等保留期限覆盖重试、离线恢复和对账窗口；过期后要明确告知不能安全重放。
业务后端必须原子执行限额、库存、唯一性和版本检查；单进程 asyncio.Lock 只是局部优化。
大批量命令先约定 all-or-nothing 或逐项提交；不能先改一半再仅返回异常。
无法原子提交时，明确补偿动作、补偿权限和失败处理；补偿本身也有 operation ID。
批准后业务版本变化应产生 conflict/new proposal，不得悄悄重算后沿用旧批准。
已有授权可以由策略批准，保留策略版本；人工批准只用于确需人工判断的风险层。

## 5. 会话并发、撤销和事件持久化〔H05〕

聊天入口取得 session turn lease 后再加载状态、追加用户消息、启动模型。
同 session 第二个 turn 排队或在执行前返回 busy；不能先调用工具再报告 session 冲突。
lease 带拥有者、期限和 fencing token；旧 worker 失去 lease 后不能继续提交状态。
消息按 turn/message ID 追加并去重，不能按旧列表长度截断更新 transcript。
页面 app events 独立追加，turn 仅推进已消费游标；不要以旧 snapshot 覆盖新页面动作。
provenance 可以按明确合并规则追加，批准 capability 等字段不得无条件集合并集。
reset/revoke 写入 tombstone 或推进 epoch；只有创建接口能建立新 session。
旧 record 的保存必须检查 epoch 和存在性；CAS 失败不能读取最新版本后强行覆盖。
撤销同时标废在途 turn 和关联提取任务；最终存储仍检查 epoch，防止取消未及时到达。
会话 TTL 与业务 operation 保留期分离：会话过期不能删除尚在对账的业务结果。
持久化快照和恢复游标需一致；多进程部署要测试真实共享存储，不能只测内存替身。

## 6. 预算、并发和 deadline〔H09〕

在宿主配置每 turn 的总 token/金额、模型调用、工具调用、wall-clock 和外部写入上限。
同时配置 tenant/用户并发、全局 worker 上限、队列长度和排队超时；预算数字来自目标 SLO。
开始下游调用前保留预算，返回后按实际用量结算；并行子任务共享同一预算账本。
重试、修复提示、子 Agent、memory extraction 都计入预算，不能为每个子调用重置额度。
未知实际用量先保留保守额度并标待核实；不能把 provider 失败当作零成本。
工具实现自己的 timeout，同时继承父 deadline；剩余时间不足时不要开启不可完成的新写入。
并发查询可限流并行；存在依赖、共用状态或不可交换写操作必须串行或走业务事务。
工具循环按调用数和业务进展停止；同参数反复失败不应靠无限轮次寻找成功。
预算不足时返回已确认结果、未完成项和下一步；不要截断后伪称任务完成。
对高风险写入保留提交/对账资源，避免模型耗光预算后无法查询已发出的命令结果。

## 7. timeout、断线与取消〔H04、H09、H12〕

明确区分模型 deadline、工具 deadline、请求断线与用户取消，并记录具体原因。
连接断开不自动撤销已发出的业务命令；恢复应查询 operation，而非重新执行用户文本。
外部写请求 timeout 后先 unknown，再按 operation/provider reference 查询结果。
只有确认没有执行且仍获授权时才重新尝试；使用原幂等键，不生成新业务命令。
取消向可取消任务传播；不可取消的外部命令仍需追踪至可证明的终态。
不能在 finally 中把 unknown 改 failed、把 partial 改 final 或把 session 重新创建。
shutdown 停止接新任务，有限等待，持久化待对账任务；重启后从 durable queue 恢复。
结果不确定时给操作者清晰核实入口和 operation ID，避免让其通过重复点击“试试看”。

## 8. 记忆也是受控写入〔H08〕

按 tenant/principal 隔离持久记忆；明确哪些事实可保存、保留多久、如何更正/删除。
从 turn 接收时捕获 subject memory epoch、session epoch、源 turn 序号，传给后台提取。
提取开始时读取的新 epoch 不能替代原基线，否则 purge 前旧对话会在 purge 后重新保存。
每个 memory key 有 revision；delete 留 tombstone，edit 推进版本，并阻止旧任务覆盖。
extraction 按读取版本做 conditional upsert；同主题以业务定义的较新 turn 为准，不按完成顺序。
epoch/revision 校验与写入在同一事务内；“先查 generation 再 await upsert”仍可能竞态。
手工纠正优先于已有后台任务；用户之后明确的新陈述才可产生更新版本。
提取输入使用不可变的本轮副本，不能持有被其他请求追加的 transcript 引用。
任务以 subject/turn 去重、限并发、可追踪；purge 取消旧任务，存储条件写提供最终保护。
JSON 文件只用于单进程演示；生产采用支持事务和条件写的持久存储，不以文件权限代替一致性。

## 9. 可观测与降级〔H12〕

关联 turn、operation、proposal、stream 和 backend reference，能重建“意图→批准→提交→回执”。
分开记录模型错误、schema 拒绝、权限拒绝、版本冲突、预算终止、unknown 和对账结果。
监控 unknown 数量/年龄、事件游标缺口、重复写拒绝、人工接管和后台任务积压。
查询失败可降级只读或明确显示旧快照及时间；授权、批准、版本和幂等存储不可用时关闭写入。
UI 渲染不可用时仍可查业务结果；模型不可用时仍保留人工操作和人工查询路径。
上线前演练一次 worker 重启、一次外部已提交但丢响应、一次 session revoke。
每次演练同时检查 ledger、业务源、事件日志和 UI；只看到日志“成功”不能验收。

## 10. 性能优化的顺序〔H09、H11〕

先测完整任务的等待分布，再优化占比最大的阶段；首token快不代表最终确认快。
稳定prompt/工具定义可形成缓存前缀，动态身份、事实与本轮状态另行组装；缓存不得跨租户泄露。
读取可批量化、去重并有限并发，缓存键包含租户、权限范围、查询参数和版本/TTL；提交前仍校验最新事实。
只保留决策所需字段和有界检索结果，低频流程按需加载Skill；压缩历史时保留操作ID、结果、引用和未决状态。
模型选型按任务难度与实测质量路由；更便宜/更快的模型也必须通过同一业务约束与任务质量门槛。
组件分段渲染并合并高频更新，给事件队列加背压；过载优先丢弃可重建预览，不能丢业务结果与撤销事件。
取消不必要的后续生成，能从receipt直接呈现的结果无需再让模型复述；自由解释留给用户需要的部分。
先检查缓存、批读、上下文和多余调用，只有可独立并行且收益经测量时才增加子Agent。
所有优化都比较每个成功任务的总成本、最终p95、人工复核与返工；不以单次token下降替代业务收益。
