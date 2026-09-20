# 组件、事件与用户交互

## Registry 与事实来源

注册三种组件：equipment_results、booking_confirmation、conflict_review；schema 禁止未知字段。
模型只能选择组件类型、请求 evidence/proposal 引用并补充非关键解释文本；不能直接输出预约事实。
服务端根据当前身份加载 evidence/proposal/receipt，补全设备、地点、区间、owner、决定与业务状态。
critical_fields 在 contract 指定 evidence 或 receipt；不存在 model 来源的关键字段。
模型生成的标签和解释进行文本转义；不允许动态脚本、未登记 action、任意 URL 或 HTML。
组件 schema 是最终 Host 事件的完整格式；partial 使用受限草稿投影，不能把缺字段草稿硬套成 final。

## equipment_results

显示真实设备 ID、名称、地点、类别、可用性观察时间；每条可用性是“截至某时可用”，不是保证。
展示区间同时带日期与时区，禁止只写“明天上午”作为提交凭据。
结果为空时提供修改地点/时间的输入，不伪造设备；后端不可用时说明无法查证。
选择候选属于 prepare 行为，不产生设备占用，也不会形成审批。
不展示其他预约的员工姓名、用途或会议参与人；只展示不可用区间所需信息。

## booking_confirmation

完整卡片显示准确设备/地点、起止时间与时区、当前员工、有效期、proposal_id。
在 proposal 已校验且 session 未撤销时显示“提交预约”；按钮绑定服务端允许的 submit_equipment_booking。
提交时使用 Host 动作通道记录准确授权与稳定 request_id，禁用重复点击只是体验优化，不替代幂等。
processing 显示“正在提交”；unknown 显示“正在核实预约结果”并提供状态查询，不显示“再试一次预约”。
只有含匹配 booking receipt 的 committed 事件才能显示“预约成功”与 reservation_id。
failed 显示“未预约”及明确原因；SLOT_CONFLICT 可链接自己的冲突请求；expired 要重新生成方案。
用户关闭卡片不能撤销后端操作；界面提供操作历史入口用于找回结果。

## conflict_review

管理员只看到自身园区待处理请求；设备/需求来自已持久化 case，候选来自新证据。
显示 offer_alternative/reject 的准确决定；记录决定前按 case_revision 条件校验。
final 的 case receipt 文案是“建议已记录”或“请求已驳回”，不使用“已预约”。
员工接收替代建议时卡片明确未占用，并进入自己的新 proposal/确认流程。
本期不发送邮件/企业聊天通知；状态保存在有权限访问的工作台与会话中。

## Partial、终态与失效

partial 仅允许标题骨架、加载状态、已转义说明；无写 action，无可提交 payload，无成功徽标。
网络结束而没有 validated final 事件：partial → invalidated，保留“内容未完成，请刷新核实”。
final 必须通过 registry schema、引用权限和事实完整性校验，不以 JSON 恰好可解析为准。
proposal 超期、设备停用、权限撤销或 case_revision 变化后，旧 final 确认卡转 invalidated。
receipt 卡过期会话后只能通过重新认证查询，不靠模型历史重建成功事实。
写工具报错时助手不能复述前一张成功卡作为本次结果；operation_id 必须可关联。

## 事件 envelope 与恢复

本应用内部 envelope：event_id、seq、tenant/session scope、generation、turn_id、operation_id（可空）、presentation_id、revision、kind、payload。
seq 是服务端持久化单调序列；event_id 去重；同一 presentation/operation 使用 revision 拒绝倒序覆盖。
这些是应用 envelope，不是宣称 AG-UI 官方固定字段；adapter 必须保留关联和恢复语义。
客户端连续应用 seq；重复忽略，缺口暂停应用并恢复；不同 session/generation 的事件丢弃。
服务端 snapshot 在同一一致性边界给出 records 与 last_seq；先订阅再快照/快照后重放必须避免窗口丢事件。
浏览器只保存恢复 cursor 和无敏感内容的引用；真实授权和 receipt 从服务端读取。
恢复日志保留 24 小时；游标超期返回 SNAPSHOT_REQUIRED，不能静默跳到最新尾部。
RUN_FINISHED 结束转录；业务 receipt 可能稍后到达，仍按 operation_id 更新卡片。

## 前端验收设计

模拟断流于 partial 后：无写按钮、无成功态；刷新得到权威 snapshot。
模拟 receipt 事件重复/倒序：单卡片一个最终结果，旧状态不回退。
模拟注销后迟到的 final：旧 generation 不重新激活提交按钮。
模拟页面动作与聊天并发：聊天没有把已提交 operation 从 snapshot 覆盖掉。

## 视觉与任务界面设计

页面/响应式/键盘/焦点/线框详见 ../../DESIGN.md；tokens与组件清单登记在contract.ui_design。
业务registry仍是事实与动作边界；UI inventory只补页面设计，不替代后端schema与授权。
responsive_layout、keyboard_navigation、ui_state_recovery计划由kind=ui且context.execution_mode=browser的真实浏览器检查持有；当前未运行。
