# PracticeSession

经用户选择保存的练习状态保存在这里。每个 JSON 文件对应一次可恢复会话，保存当前题目快照、提示文本、待答阶段、目标、时间预算和模式。

展示完整答案前保存 assistance=reference_seen 和 reference_seen_questions；同一会话再次练该题仍沿用。写回答 Event 时从 practice.py answer-context 复制辅助状态。旧会话无法确认完整答案是否公开时保持 unknown。

暂停后保留未完成会话，结束时标记 completed。实际回答与评分仍以相邻 events/ 中的不可变记录为准。免保存试练不创建会话文件。

这些文件是私人上下文，无法仅从已完成回答重建。Public Export 只发布本说明，排除用户会话。
