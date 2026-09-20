# 预约与冲突处理状态机

## 正常预约

1. 员工问“明天 10–11 点 A 园区需要视频会议摄像头”；日期按其时区解析，不确定时先澄清。
2. find_equipment 读取真实设备和区间可用性；卡片显示证据时间，模型仅解释优缺点。
3. 员工选择设备；prepare_booking_proposal 重新读取设备规则并生成准确的 120 秒有效提案。
4. 完整确认卡显示设备地点、起止日期/时区、借用人；员工点击“提交预约”形成可信授权。
5. Host 校验 actor、role、范围、session generation、payload_hash、提案有效期、设备/规则版本。
6. 创建或读取幂等 operation；worker 将 approved CAS 为 executing，并携 client_request_id 调原子占用。
7. 后端返回 reservation receipt → 校验对象/区间/owner → 持久化 committed 和事件 → UI 显示预约号。
8. 后端明确拒绝重叠 → failed + conflict_case；UI 告知未预约并允许浏览其他设备/时间。

## operation 状态

proposed → approved：收到 Host 验证的准确意图授权；模型一句“用户同意”不能迁移状态。
proposed/approved → expired：超过有效期或撤回授权，且尚未进入执行。
approved → executing：权限、提案、资源版本校验与执行租约成功。
executing → committed：权威 receipt 已校验并持久化。
executing → failed：后端证明未产生占用，或请求在发送前确定失败。
executing → unknown：连接丢失、超时、进程退出，不能判断远端是否接受。
unknown → committed：按 client_request_id 查询到匹配的唯一预约并校验 receipt。
unknown → failed：后端提供确定拒绝/结束且未提交的状态；“暂时查不到”不能直接判失败。
终态 committed/failed/expired 不再改变；取消或更改若未来支持，属于新的有权限业务操作。
unknown 不设“超时自动失败”；过长未决升级人工核实，同时保留后台查询和用户可见状态。

## 竞争失败与管理员处理

两个员工同时提交重叠区间：后端原子接口只允许一个成功，另一个返回 SLOT_CONFLICT；不存在应用先读再写替代约束。
系统只为明确失败的预约创建一个 conflict_case，关联原员工、设备/时间需求、operation 和园区。
未决 unknown 不进入“重新预约”路径，避免管理员为可能成功的请求创建第二个占用。
管理员 list_conflict_cases 后选择 case；prepare_conflict_decision 形成 offer_alternative 或 reject 的准确方案。
候选必须来自其有权查询的最新目录/可用性；offer 不占用，文本必须明确“建议，尚未预约”。
管理员点击记录决定，Host 执行 case_revision CAS 并持久化 case receipt；同时处理者第二人收到 VERSION_CONFLICT。
员工在会话/工作台查看建议；只有员工确认并提交新的 booking proposal 才产生新预约。
管理员驳回只关闭待处理请求，不撤销、移动、释放任何已确认占用。
管理员工作流采用相同 proposed/approved/executing/committed/failed/unknown/expired 状态，但 committed 的业务含义是“冲突处理决定已记录”。

## 会话、刷新与取消

一个 session 只允许一个生成中的聊天 turn；后续消息排队或显式拒绝 busy，不能无锁覆盖 history。
页面动作可与聊天读取并行，但经过独立 operation CAS；它不直接写 session 整体快照。
取消 turn 停止新模型/工具派发；已经发出的占用保留原 operation_id 继续对账。
注销/重置先递增 session generation，旧批准与旧 worker 的新写能力被撤销。
如果注销前远端已占用，系统仍应记录结果；撤销会话不能把现实占用抹掉。
页面刷新从 last_seen_seq 续接；无 cursor 或 cursor 过期时获取 snapshot，再从 snapshot.seq+1 消费。
订阅校验 tenant/actor；历史事件不能被别人的 session_id 猜中读取。
旧 turn 的 partial 到达不得覆盖新 turn 的 final；同 operation 的旧 revision 不能覆盖新状态。

## 确定性业务边界场景

跨日/跨时区：以 UTC interval 判断冲突，展示保留原 IANA timezone；重复小时要求员工选择偏移。
邻接区间允许；同一设备任意正长度交叠拒绝；不同 equipment_id 同时段可并行。
设备在提案后停用：版本/规则检查失败，旧批准不能提交；重新选择设备。
有其他人刚提交非重叠时段：不能仅因为全日历更新就使本提案无理由失效。
前端重复点击/浏览器重发/worker 接管：使用同一 request_id，最终只一个 occupancy 与一个 receipt。
模型推荐不存在设备、管理员指令“直接抢掉同事的”或来源文本含恶意指令：结构与权限拒绝，审计命中原因。

## 实施前验证点

用适配器合同测试确认后端原子性覆盖相同实体与 UTC 区间；本设计不以文档描述替代实测。
用远端“已成功但响应丢失”故障验证 client_request_id 的查询语义和未发现状态是否最终/暂时。
缺少这些能力时只启用查询/方案草稿，提交按钮禁用并解释业务暂不可办理。
