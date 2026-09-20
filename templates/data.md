# 数据契约

## 实体与权威源
为每个领域实体定义 ID、tenant、version、数据类型、保留策略、权威 backend。金额用整数最小货币单位并标币种。

## 知识与执行模型
定义 Evidence / Intent / Proposal / Approval / Operation / Receipt；给出 schema 文件位置和跨对象不变量。Approval 绑定准确方案与权限，Operation 的重试沿用操作身份。

## 版本、新鲜度与删除
指定时间单位和UTC策略、TTL、提案过期、条件更新、session epoch、memory key revision/tombstone；关闭记忆时记录不适用理由。

## 错误语义
列出 validation / authorization / conflict / expired / unavailable / unknown；区分确定失败与结果未知，标明哪些可重试以及去重协议。
