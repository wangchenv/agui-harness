# 企业会议设备预约：完整应用设计示例

这是跨业务 AGUI 的**设计示例**：员工查找会议设备并提交自己的预约；管理员为辖区内冲突请求记录替代建议或驳回。它展示从业务约束到工具、组件、UI、恢复与评测契约的设计成果。

设计门禁已在此目录实际通过；**没有实现后端、可运行原型、模型调用或浏览器测试，implementation 与 release 门禁未通过**。实际命令与结果见 [VALIDATION.md](VALIDATION.md)。

## 阅读顺序

1. [架构与范围](.agui/design/architecture.md)：谁能做什么，哪些事实由已有后端负责。
2. [数据契约](.agui/design/data.md)与[流程](.agui/design/workflows.md)：时间区间、proposal、批准、幂等、receipt、unknown和对账。
3. [UI设计与线框](DESIGN.md)：员工查找/审查/结果、管理员队列/差异处理、移动布局与键盘路径。
4. [交互状态](.agui/design/interaction.md)、[运行设计](.agui/design/operations.md)、[评测计划](.agui/design/evaluation.md)。
5. [机器契约](.agui/contract.json)、[17个边界schema](.agui/schemas/)、[tokens](ui/tokens.json)和[组件清单](ui/component-inventory.json)。

本例保持 `scope=application`，没有为了通过门禁退化成 reference；7个工具、2个写工作流、3个运行时组件和8个UI组件均为设计声明。`status=ready`只表示设计完成。

## 关键业务决定

- 既有事实是预约后端提供原子时间段占用接口；同实物的UTC半开区间 `[start,end)` 不能重叠，邻接区间可并存。
- 预约提交使用 `precondition=atomic_predicate`，不虚构全日历版本；管理员修改本地冲突请求使用 `entity_version` 条件更新。
- 员工只能为自己预约；管理员只能在其园区建议替代/驳回，不撤销或抢占他人已确认预约。替代建议不占用设备，仍需员工确认新方案。
- turn、operation、presentation分开；partial不可写，模型结束不代表提交；成功显示必须绑定匹配的权威receipt。
- 远端超时保留unknown，查询原request_id核实；不生成新key盲目重订。
- UI采用普通筛选/列表/审查区与可折叠助手；模型不可用时仍可经同一受控业务路径办理。
- 本期不做长期memory、周期预约、付款、外发通知或部署。

## 在本目录复跑

使用 Python 3.10+ 与插件根目录 `requirements.txt` 中的依赖。以下命令从本示例目录执行，不依赖原作者电脑路径：

```sh
python ../../scripts/ui_audit.py --tokens ui/tokens.json --inventory ui/component-inventory.json
python ../../scripts/harness.py --project . lint
python ../../scripts/harness.py --project . gate --stage design
python ../../scripts/harness.py --project . gate --stage implementation
python ../../scripts/harness.py --project . gate --stage release
```

前三条应通过，后两条应非零退出并说明缺少真实实现。不要运行 `run` 期待测试成功：contract.checks中的脚本是尚未创建的计划路径。

`ui_audit.py`只验证声明结构、选定颜色对、组件引用和动作状态；它没有打开浏览器，不能当作键盘、响应式或可访问性实测。
`prototype/index.html`只是ui_design登记的未来入口，当前不存在，也没有启动命令或截图。H06的三个UI案例计划使用kind=ui和真实browser执行，但本例没有这类证据。

## 复制与继续开发

可复制整个示例目录到自己的项目，保留隐藏的 `.agui` 目录；契约中业务文件路径均相对项目根目录。之后使用已安装工具包的真实路径运行harness。
已有contract时先运行 `status` 并阅读设计；不要重新 `init` 覆盖设计。用户实际授权开发时再建立自己的STATE/HANDOFF与实现记录。
本例不携带旧evidence、STATE、HANDOFF或自动生成门禁缓存；不能继承别处的PASS当作当前实现证据。

## 实施前依赖与未验证项

1. 核实后端按client_request_id幂等和查询最终/未决结果的能力；仅原子占用接口不足以关闭跨系统响应丢失缺口。
2. 对接真实SSO与园区管理员权限；确认设备停用/预约策略的条件检查语义，目录设备修订若存在必须来自真实接口。
3. 确认企业预约时长/提前期政策。设计的最长4小时、提前30天是可配置假设，不声称为企业实际制度。
4. 选定真实模型、采集真实任务与人工基线；release中的planned/unselected标识和阈值只是计划，不是已有评测资产。
5. 明确品牌与目标设备；实现prototype/页面，在实际浏览器检查布局、键盘、状态恢复和截图，再做代表性用户任务评估。

本例中的未来src/tests/prototype路径是设计到实现的交接，不是假造的应用或测试。没有授权或证据支持部署、外部写入及生产就绪声明。
