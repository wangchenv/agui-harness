# 交互契约

## 用户与运营人员视图
定义任务入口、默认信息密度、完整diff、证据来源、人工审核成本和辅助普通页面入口。

## 组件注册表
每个组件记录 schema、事实补全器、critical fields、允许模型生成的解释字段、操作按钮所需授权与后端路由。

## 三套状态
分别定义 turn、operation、presentation；partial 无写按钮，只有 validated event 才可形成最终卡片，业务成功必须查询到receipt。

## 恢复与可访问性
断流、坏事件、重复/乱序、刷新/重新连接、键盘和读屏、过期事实、用户切换分别如何显示和恢复？

## 协议
选内部事件或指定版本的 AG-UI adapter；自定义 operation/receipt 放独立扩展协议，不冒充官方通用事件语义。
