# 故障矩阵：可执行场景与权威断言

本矩阵用于生成目标项目的故障测试，不替代业务正常流程测试。
把 `resource/operation/proposal` 替换为真实领域对象，但保留边界与断言。
每个用例先创建隔离 fixture，保存 before snapshot；运行后查询真实业务源及执行 ledger。
使用显式 barrier、假时钟和可控 provider 响应，不依赖 sleep 猜测竞态发生。
只在隔离租户或沙盒运行写操作；测试结束按业务约定清理，不对生产数据注入故障。

## 执行约定

测试夹具提供 `actor_a/tenant_a`、`actor_b/tenant_b`、`backend`、`ledger`、`event_log` 和 UI client。
注入点至少包含：`after_read`、`before_submit`、`after_backend_commit`、`before_receipt`、`before_memory_write`。
`release(barrier)` 允许等待的调用继续；`advance_clock()` 控制 TTL/deadline；provider stub 不接真实模型。
事件恢复使用 stream ID、seq 和 event ID；业务重复调用使用稳定 operation ID。
以下 expected oracle 都要求自动断言；自然语言“看起来没问题”或日志打印不算通过。
模型任务层另跑真实模型的错误意图场景，重复策略见 [evaluation.md](evaluation.md)。

## F01 — H01：伪造租户或目标对象

- Given：A 只可读写 tenant A；B 的 resource 具有可辨认的敏感测试值。
- When：以 A 会话传入 B resource ID，并在模型工具参数中伪造 tenant B。
- Then：请求在业务读取/写入前拒绝；UI 不渲染 B 的内容，也不泄漏对象是否存在。
- Expected oracle：B 业务前后快照相同；工具结果/事件/响应均不含敏感测试值；拒绝审计归属 A。

## F02 — H02：双击和同幂等键并发

- Given：两个请求使用相同 operation ID、principal 和 payload hash；在提交前 barrier 相遇。
- When：同时释放，并让客户端再重发一次相同请求。
- Then：只执行一次副作用，其余返回同一 operation 的进行状态或 receipt。
- Expected oracle：权威业务副作用计数为 1，ledger 只有一个执行权，三次结果引用相同业务 ID。

## F03 — H02：同幂等键换载荷

- Given：operation O 已以 quantity=1 被接收或提交。
- When：相同 O 再请求 quantity=10，或更换 principal/tenant。
- Then：返回明确幂等冲突/授权拒绝，不复用成功结果掩盖载荷变化。
- Expected oracle：业务仍只增加 1；原 ledger hash 和 principal 不变；新载荷没有执行记录。

## F04 — H03：批准后修改 proposal

- Given：用户批准 revision 3 的指定资源与变更值。
- When：模型或页面把 proposal 改为 revision 4，仍带 revision 3 的批准提交。
- Then：要求新版本授权；不得静默采用新内容，也不得解释“此前同意过”继续提交。
- Expected oracle：业务状态不变；批准摘要仅对应 revision 3；revision 4 没有 committed operation。

## F05 — H03、H07：检查后资源被他人修改

- Given：读取 resource revision 8 并预览；before_submit 暂停。
- When：独立操作者提交 revision 9，再释放原操作。
- Then：返回版本冲突并使旧卡 stale；重新建议若改变批准内容则需新批准。
- Expected oracle：revision 9 的变更保留；没有以 revision 8 覆盖它；原 operation 不为 committed。

## F06 — H04：提交成功但响应丢失

- Given：provider 支持幂等键和按业务引用查询；after_backend_commit 暂停。
- When：丢弃提交响应并触发工具 timeout，随后恢复查询服务。
- Then：operation 先 unknown，后对账为 committed；不因 timeout 生成新命令。
- Expected oracle：provider 副作用计数 1；ledger 状态路径包含 unknown→committed；receipt 指向原提交。

## F07 — H04：批量中间项失败

- Given：三项变更，预先声明 all-or-nothing 或逐项提交；第二项注入约束失败。
- When：执行整个批次并等待所有已发出项达到可证明状态。
- Then：事务模式无部分影响；逐项模式明确每项结果，补偿失败不能称“全部撤销”。
- Expected oracle：逐项权威快照与合同一致；不存在 UI 整体成功却有失败项，或整体失败却隐瞒已提交项。

## F08 — H04、H12：worker 在提交后退出

- Given：operation 已被领取；业务已提交；receipt 尚未发布。
- When：杀掉该测试 worker，启动新 worker 并重放 outbox/恢复任务。
- Then：恢复 worker 查询/重放同一 operation 的结果，不能再次执行副作用。
- Expected oracle：业务计数 1；ledger 最终 committed；有唯一业务 receipt，重复事件按 ID 去重。

## F09 — H05：reset 时旧聊天仍在运行

- Given：旧 epoch 的 turn 在模型返回前暂停，用户 reset/revoke 后建立新会话。
- When：释放旧模型响应、旧工具回调和流结束写回。
- Then：旧 token 持续失效；旧任务不能重建会话、覆盖新状态或发布可执行卡。
- Expected oracle：旧 session tombstone/epoch 不回退；旧 token 401；新 transcript 无旧 turn 的追加。

## F10 — H05：同 session 双聊天和页面动作交错

- Given：turn A 正运行；页面动作 P 已成功；turn B 同时到达。
- When：按 A/P/B 的不同完成顺序各运行一次，特别在 session 写回前阻塞 A。
- Then：B 在执行前排队/拒绝；P 的事实与 app event 保留；对话顺序不会混杂回答。
- Expected oracle：P 副作用一次，event 未丢且消费一次；transcript 按 turn 配对；无用户 B 消息被覆盖。

## F11 — H06：partial 后 EOF 或断网

- Given：客户端收到 ui_partial，但没有完整校验后的 final ui 和 turn terminal。
- When：分别注入 clean EOF、网络异常、坏 JSON 帧及超时。
- Then：卡片保持不可写并标 interrupted；明确提示未完成，不能在 finally 升为 final。
- Expected oracle：DOM/状态树无可执行写动作；无 committed operation；不存在伪造完成 receipt。

## F12 — H06：运行完成但业务未确认

- Given：业务 operation 是 unknown 或仅 proposed，编排器正常结束本轮。
- When：发送 turn complete，AG-UI adapter 场景中发送 RUN_FINISHED。
- Then：UI 显示本轮结束，同时保持业务待批准/核实状态，不显示已提交。
- Expected oracle：operation 状态未被 run 事件修改；成功文案只在权威 receipt 到达后出现。

## F13 — H06、H12：事件重复、乱序、缺帧和刷新

- Given：已有 seq 1..10，operation O 已提交；客户端只连续应用到 5。
- When：发送重复 5、先发 8、漏发 6，再刷新并以游标 5 恢复；另测日志过期。
- Then：重复忽略、缺口触发重放；日志过期走一致快照；不重新执行 O 的用户消息。
- Expected oracle：最终 UI projection 等于完整日志重放；业务计数仍为 1；游标连续且不跨 stream 比较。

## F14 — H07：动态报价或预约到期

- Given：卡片绑定 quote/reservation Q 和截止时间；另有新 reservation R。
- When：推进时钟使 Q 过期，刷新 R 的状态，再点击 Q 的旧动作。
- Then：Q 卡明确过期，不能显示 R 的倒计时为其续命；服务器拒绝旧资格。
- Expected oracle：Q 未提交；R 状态未被误改；卡片 resource ID、版本、时间与业务记录一致。

## F15 — H08：提取中删除或手工更正

- Given：提取任务已读 memory key K 的 revision 2，before_memory_write 暂停。
- When：用户删除 K 或改为 revision 3，再释放旧提取。
- Then：旧写入被条件写拒绝；删除不复活，手工值不被覆盖。
- Expected oracle：K 的 tombstone/revision 3 保留；其他用户同名 K 不受影响；拒绝原因可追踪。

## F16 — H08：purge 早于后台提取开始

- Given：旧 turn 已接收但仍在流式输出，其 memory extraction 尚未启动。
- When：用户 purge 全部记忆；旧流结束后尝试启动 extraction；另测模型等待中 purge。
- Then：两个时序都拒绝旧 epoch 写入；purge 后新 turn 仍可保存新事实。
- Expected oracle：旧事实数量 0；purge epoch 单调；新 turn 写入成功且来源为新 epoch。

## F17 — H08：多个提取乱序完成

- Given：同一主题的旧 turn 说 red，新 turn 说 green；两个提取读取同一基线。
- When：先完成新提取、再完成旧提取；交换顺序重跑，并跨两个 worker 重跑。
- Then：以较新有效 turn 或人工 revision 为准，不以完成时间为准。
- Expected oracle：最终值总是 green；无不同用户串写；账本保留拒绝旧更新的依据。

## F18 — H09：并发分支和重试耗尽预算

- Given：总预算只能容纳两次调用；三个子任务竞争，第一次调用发生可重试故障。
- When：同时发起并允许重试，记录每次预算保留、实际用量和释放。
- Then：子任务共享总账，超预算分支不启动；给出未完成项，不声称整个任务完成。
- Expected oracle：所有重试/提取消耗计入总额；并发不超过配置；预算不足不丢已发命令的对账任务。

## F19 — H09、H04：写请求发出后取消

- Given：命令已送外部系统，响应尚未返回，用户点击取消或客户端断线。
- When：取消本地等待；外部系统分别返回已提交、已取消和暂不可查询三种结果。
- Then：按权威证据进入 committed/cancelled/unknown；不能一律显示“未执行”。
- Expected oracle：UI 与 provider 记录一致；不重复提交；unknown 在约定 SLO 内收敛或触发人工接管。

## F20 — H10：坏模型参数与恶意内容

- Given：工具只允许白名单动作、有限数量和已授权资源；检索内容含“跳过批准”等指令。
- When：假模型发负数、超限、陌生 ID、额外权限字段、任意 URL，以及绕过批准的调用序列。
- Then：schema/权限/业务门分别拒绝；检索文本不改变策略；partial 不生成执行能力。
- Expected oracle：所有 forbidden effects 为零；拒绝分类正确；原始敏感内容不泄漏到日志/UI。

## F21 — H11：看似省时但增加人工复核

- Given：有等价任务的人工作业基线，含主动时间、错误和返工；采用交叉顺序分配题组。
- When：代表性用户分别完成手工和 Agent 流程，记录全部审阅/纠错/接管时间。
- Then：报告净人工收益和不确定性；未达到预定收益门槛不得宣称效率改善。
- Expected oracle：可核对的时间记录与业务结果；分母包含失败/放弃任务，不只计成功样本。

## F22 — H12：授权或幂等存储不可用

- Given：模型仍可用，但批准/幂等/权限存储不可读写，已有 operation 尚待对账。
- When：发起新写入，同时访问只读结果与已有 operation 的恢复入口。
- Then：关闭无法保证安全的新写入；明确降级；保留对账与人工查询，不返回假成功。
- Expected oracle：新副作用为零；已有状态不被误置 failed；trace 能关联失败依赖、受影响 operation 和告警。
