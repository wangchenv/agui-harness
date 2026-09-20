---
name: agui-design
description: 设计或重构具有业务操作和生成式组件界面的 Agent 应用，产出架构、实体契约、流程与可验证控制；适用于跨行业 AGUI 场景。
---

# 设计可执行、可验证的 Agent 业务系统

目标：产出领域模型和执行边界，不把电商对象换名字当成通用架构。

## 工作顺序

1. 读取已有业务接口、权限、数据库、组件与流程；有 `.agui` 先读 contract/STATE 并运行 status。新目标经 router 的 init 建立草案。
2. 定义一条完整旅程：用户与运营角色、真实任务、已有基线、允许自动执行的范围、禁止动作和失败出口。缺失会改变业务风险的信息要问清；独立的代码阅读和架构工作继续。
3. 读 [架构](references/architecture.md)、[数据契约](references/data-contracts.md)、[流程](references/workflows.md)，按目标取舍模块；小系统可单体，不能省略责任边界。
4. 输出/更新六个设计文件，路径写入 contract.design。已有文档可直接引用，不为模板重写。定义 tool input/output 与组件 schema、领域权威源、持久状态机、错误分类、预算、降级与验收。
   有UI的应用接 [agui-ui](../agui-ui/SKILL.md)，将DESIGN、tokens、组件清单和prototype路径写入ui_design；应用架构与视觉设计相互校验，不靠生成组件schema替代界面设计。
5. 将 H01–H12 映射到实现位置和测试 case；只按实际功能标记不适用。reference scope 仅用于明确的组件示范，真实应用必须 application。
6. 把初始工具名、模板阈值、权限和数据源替换为实际定义；`status=ready` 只是设计声明完成，不能手改 evidence 为 passed。运行 lint 与 `gate --stage design`，修复结构/引用/流程不一致。
7. 评审设计是否真实覆盖业务任务与操作风险；机器 lint 不能理解业务含义。记录未决点、决定、验证方式，交给 build。用户已要求实现且关键决定已明确时直接继续，不新增形式化批准步骤。

## 设计中必须说清楚

- 什么必须由业务系统保证，什么只由模型提供建议；读过对象不等于获准修改。
- 每项写如何形成可信意图、准确提案、批准、条件更新、幂等 receipt，以及 unknown 查询。
- 新建预约等业务可采用 atomic_predicate（例如原子区间互斥）而非强求全局实体ETag；在precondition_detail明确数据源约束、冲突行为及旧批准失效规则。
- 数据 TTL、version、tenant、金额/时间类型，memory 的删除/乱序规则。
- 哪些卡片字段由模型解释、哪些必须来自 Evidence/Receipt；部分呈现无写按钮。
- 哪些目标能确定性验证，哪些需要真实模型/端到端/负载及人工效率基线。

领域形态参考 [IT 服务工单、CRM 与资源预约](../../examples/domain-mapping.md)；可运行机制见 [service-desk](../../examples/service-desk/README.md)。示例不能覆盖全应用运行可靠性。

CLI 和必需案例使用 [Harness 合约](../agui/references/harness.md)；不要猜测 JSON 字段或门禁含义。
