# 数据与工具契约

## 领域实体与权威源

| 实体 | 权威源 | 标识与版本 | 租户隔离 | 使用界限 |
|---|---|---|---|---|
| equipment | 企业设备目录，待对接 | equipment_id、equipment_revision（需验证可提供） | tenant_id + site scopes | 名称、序列号、启用状态、类别、地点、借用规则 |
| occupancy | 现有预约后端 | equipment_id + [start,end)；原子冲突约束 | tenant_id | 可用性查询只是证据，提交时重新原子判定 |
| reservation | 现有预约后端 | reservation_id、revision（接口待确认） | tenant_id + owner_id | 只有后端成功凭证代表占用 |
| proposal | 应用数据库 | proposal_id、revision、payload_hash | tenant_id + actor_id | 准确待提交意图、审批对象、有效期 |
| operation | 应用数据库 + 后端结果对账 | operation_id、revision、request_id | tenant_id + actor_id | 本地执行状态及远端权威 receipt 引用 |
| conflict_case | 应用数据库 | case_id、revision | tenant_id + site_id | 用户失败请求及管理员决定；无权创造占用 |

可用性不发明全日历 entity_version：原子区间占用是冲突控制，equipment_revision 用于设备状态/规则变化校验。
预约提交的 contract.precondition=atomic_predicate，指后端原子判断并占用不重叠区间；管理员本地case修改使用entity_version。不能把前端缓存时间戳或无来源全日历版本当成条件。
若目录无版本，适配器需提供可验证的条件/修订语义；否则暂时只开放只读查询。
reservation version_field 的 revision 是所需契约，未声明现有系统已经支持。

## 时间与数据类型

设备采用可区分的实物 ID；不在本期实现“任意一台同类设备”的多数量库存。
start_at/end_at 为带偏移的 RFC3339 日期时间，timezone 为 IANA 地区；持久化 UTC instant，同时保留展示地区。
区间采用 [start_at,end_at)，拒绝 end<=start、过期时间、无偏移时间与未消歧的 DST 重复小时。
服务端验证 timezone 与偏移在该 instant 一致；schema 的 date-time 不能独自完成这项跨字段验证。
预约策略暂定最长 4 小时、最多提前 30 天；由配置 policy_revision 纳入提案 hash。
描述、用途字段限制长度并作为不可信数据；不得从自由文本生成权限或控制字段。
不保存会议内容、参与人列表；只保存必要的简短用途，支持缺省。

## 证据与提案

查询返回 evidence_id、observed_at、expires_at；可用性证据有效 15 秒，设备元数据 60 秒，超期重新读取。
构建提案时重新读取设备/规则/可用性；proposal 有效期为 120 秒，不保证在期限内必然抢到设备。
proposal 的规范化 payload 包含设备、准确区间、timezone、owner、规则版本、设备版本；Host 计算 payload_hash。
模型输入不得包含 tenant_id、actor_id、审批人或 permission；这些由 Host 上下文注入。
approval 绑定 proposal_id + revision + payload_hash + actor + session generation；用户改时间后原批准失效。
写工具只接收 proposal_id 或冲突决定提案 ID，服务端从可信存储解析内容。
客户端 action 带单次授权引用和稳定 request_id；它们由 Host 验证，不由模型任选。

## 对外工具（schema 为本目录旁 JSON 文件）

find_equipment：输入需求/园区/准确区间，输出可访问设备、证据与有效期；不得暴露谁占用了设备。
prepare_booking_proposal：输入证据引用、设备与准确区间；Host 重读并返回绑定当前 actor 的不可变提案。
submit_equipment_booking：输入 proposal_id；在授权、版本、有效期校验后调用原子占用。
get_booking_operation：输入 operation_id；按当前 principal 查询可见操作，返回状态与可选 receipt。
list_conflict_cases：管理员查询自身园区请求；员工仅可见自己的请求，工具层必须区分调用权限。
prepare_conflict_decision：管理员输入 case_id、expected_revision、offer/reject 与候选方案；Host 验证范围并形成提案。
resolve_booking_conflict：输入 decision_proposal_id；条件更新本地 case，不调用占用接口；输出类型明确的 case receipt。

## 持久化与事务

operation 以 (tenant_id, request_id) 唯一，payload_hash 一并存储；同 key 不同 payload 返回 IDEMPOTENCY_CONFLICT。
以原子 compare-and-set 将 approved → executing；并发 worker 只能取得一个带期限的执行租约。
创建 operation、批准引用消费、执行 outbox 在本地事务内完成；不假定与远端预约后端共享事务。
远端以同一 client_request_id 保证占用幂等且能查结果，这是待确认/新增的后端 adapter 前置条件。
仅应用本地幂等表无法关闭“远端已成功、本地未写回”的缺口；缺少远端查询时不允许重发未决写入。
收到后端冲突拒绝，operation=failed；本地同事务创建冲突 case/outbox；内部重放不得产生重复 case。
case 决定、case receipt、operation 完成、事件 outbox 同一数据库事务提交。
会话使用 (tenant_id,session_id,generation,revision)；补丁式更新，CAS 冲突必须重读/重算，禁止整份覆盖。

## Receipt 与错误

booking receipt 包含 operation_id、reservation_id、equipment_id、owner_id、start/end、tenant 引用、committed_at、authority_ref。
conflict receipt 包含 operation_id、case_id、decision、case_revision、decided_at；不得带虚假 reservation_id。
operation 查询 schema 使用 oneOf 区分 committed/failed/unknown/processing；committed 才允许非空 receipt。
AUTH_DENIED、VALIDATION_ERROR、PROPOSAL_EXPIRED、VERSION_CONFLICT 是无提交的拒绝；SLOT_CONFLICT 只在后端明确拒绝时使用。
DEADLINE_EXCEEDED 若已经发出占用请求则转 unknown，不能凭 HTTP timeout 判断未占用。
UPSTREAM_UNAVAILABLE 在发送前已确认失败时可 failed；发送边界不清时按 unknown 处理。
保留设备证据与 receipt 的来源关联供审计；日志隐藏 SSO token 和员工用途原文。

## Memory

本期 memory=false，不做跨会话偏好抽取或回写；会话历史不是授权源。
员工问“和上次一样”只能用其有权读取的真实预约记录重新生成提案，不能凭模型记忆直接预约。
