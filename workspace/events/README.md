# Attempt Events

每次回答在 `YYYY/MM/` 下创建一个新的 `attempt.recorded` JSON 文件。

示例格式见：

```text
protocol/examples/attempt-event.example.json
```

Event 是训练历史的事实来源。每条 Event 通过 `cycle_id` 关联 PreparationCycle，通过 `practice_session_id` 关联一次连续练习会话。创建后保持只读，状态投影由 `scripts/rebuild_state.py` 生成。
