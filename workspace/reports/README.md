# Cycle Reports

`cycles/` 保存已结束 PreparationCycle 的固定 CycleReport。每次结束会生成两个文件：

```text
<cycle-id>.json    Agent 可读取的结构化报告
<cycle-id>.md      用户可直接阅读的总结
```

原始回答和逐次评价仍以 `workspace/events/` 中的 AttemptEvent 为事实来源。报告用于保存 PreparationCycle 结束时的统计快照，不随之后的复习日期变化而重算。
