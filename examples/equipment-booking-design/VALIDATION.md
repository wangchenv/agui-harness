# 可移植设计示例：实际验证记录

在本示例目录实际执行以下命令，使用 Python 3.12.13 与本插件当前harness。调用未访问模型、浏览器或业务后端。
这是设计一致性与静态声明检查记录，不是harness.run签发的实现/发布证据。没有复用原临时项目的门禁缓存。

## 结果

| 检查 | 实际退出码 | 实际结果 |
|---|---:|---|
| UI声明检查 | 0 | design_tokens: passed, component_inventory: passed |
| lint | 0 | passed |
| design | 0 | passed |
| implementation | 1 | blocked |
| release | 1 | blocked |

UI声明、lint、design均通过；implementation/release均为blocked且非零退出。后两者是本例尚未实现的真实状态，不是已获验证后人为禁用。

## 实际 design gate JSON

```json
{
  "status": "passed",
  "stage": "design",
  "scope": "contract consistency only; implementation unverified",
  "errors": []
}
```

## 实际 UI 声明检查 JSON

```json
{
  "schema_version": 1,
  "cases": [
    {
      "id": "design_tokens",
      "status": "passed",
      "detail": "Declared design checks passed; rendered/browser behavior unverified."
    },
    {
      "id": "component_inventory",
      "status": "passed",
      "detail": "Declared design checks passed; rendered/browser behavior unverified."
    }
  ]
}
```

lint 原始结果：

```json
{
  "status": "passed",
  "errors": [],
  "scope": "declaration consistency only"
}
```

## 实现与发布为何未通过

`gate --stage implementation`：退出 1，status=blocked，28 条缺失项。
`gate --stage release`：退出 1，status=blocked，28 条缺失项。

两阶段此次报告的缺失集合相同：
- `source_paths missing: src`
- `source_paths missing: tests`
- `source_paths missing: prototype`
- `ui_design.prototype: missing/empty file prototype/index.html`
- `booking_controls.inputs: missing/empty file tests/test_booking_controls.py`
- `booking_recovery.inputs: missing/empty file tests/test_booking_recovery.py`
- `booking_quality.inputs: missing/empty file tests/eval_booking.py`
- `booking_load.inputs: missing/empty file tests/load_booking.py`
- `booking_ui.inputs: missing/empty file tests/test_booking_ui.py`
- `booking_ui.inputs: missing/empty file prototype/index.html`
- `H01.implementation: missing/empty file src/host/auth.py`
- `H01.implementation: missing/empty file src/adapters/booking.py`
- `H02.implementation: missing/empty file src/runtime/operations.py`
- `H02.implementation: missing/empty file src/adapters/booking.py`
- `H03.implementation: missing/empty file src/domain/proposals.py`
- `H04.implementation: missing/empty file src/runtime/operations.py`
- `H04.implementation: missing/empty file src/workers/reconcile.py`
- `H05.implementation: missing/empty file src/host/sessions.py`
- `H06.implementation: missing/empty file src/ui/registry.py`
- `H06.implementation: missing/empty file src/web/events.ts`
- `H06.implementation: missing/empty file src/web/layout.ts`
- `H06.implementation: missing/empty file src/web/accessibility.ts`
- `H07.implementation: missing/empty file src/domain/evidence.py`
- `H09.implementation: missing/empty file src/runtime/budget.py`
- `H10.implementation: missing/empty file src/host/intent.py`
- `H11.implementation: missing/empty file tests/eval_booking.py`
- `H12.implementation: missing/empty file src/runtime/audit.py`
- `H12.implementation: missing/empty file src/web/fallback.ts`

这些src/tests/prototype路径明确登记为计划，当前不存在。本例没有创建替代实现、空脚本或假browser结果来填补缺口。

## 复跑命令

从本目录执行，选择安装了插件requirements的Python解释器：

```sh
python ../../scripts/ui_audit.py --tokens ui/tokens.json --inventory ui/component-inventory.json
python ../../scripts/harness.py --project . lint
python ../../scripts/harness.py --project . gate --stage design
python ../../scripts/harness.py --project . gate --stage implementation
python ../../scripts/harness.py --project . gate --stage release
```

## 边界与移植检查

- contract、6个设计文档、17个边界schema、DESIGN.md和UI资产均使用项目相对路径；未引用原作者的临时目录。
- UI计划入口`prototype/index.html`尚未创建；没有真实截图、浏览器执行、键盘/读屏测试或用户效率结果。
- 本目录不包含STATE、HANDOFF、evidence、运行日志缓存；复制到新工程后应重新计算门禁结果。
- 预约使用atomic_predicate表达后端原子区间占用；外部幂等/结果查询能力仍需实现前核实。
- release模型/数据集/人工基线为明确计划标识；没有真实模型样本，不能由设计通过推断生产可用。
