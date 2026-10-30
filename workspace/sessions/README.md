# PracticeSession

经用户选择保存的练习状态保存在这里。每个 JSON 文件对应一次可恢复会话，保存当前题目快照、提示文本、待答阶段、目标、时间预算和模式。

展示完整答案前保存 assistance=reference_seen 和 reference_seen_questions；同一会话再次练该题仍沿用。写回答 Event 时从 practice.py answer-context 复制辅助状态。旧会话无法确认完整答案是否公开时保持 unknown。

暂停后保留未完成会话，结束时标记 completed。实际回答与评分仍以相邻 events/ 中的不可变记录为准。免保存试练不创建会话文件。

这些文件是私人上下文，无法仅从已完成回答重建，应随自己的私人仓库保存。

## 教学记录

PracticeSession 可包含 teaching_sessions，列表保留完成或停止的教学，最后一条可以 active。此时 stage=teaching；记录包括目标、卡点、证据、路径、原题快照、检查原话、帮助条件与 next_action。通过 scripts/teach.py 更新，由 scripts/validate.py 校验。教学小检查不写入 workspace/events，不影响覆盖率或复习间隔。此目录中的实际会话均为私人数据。
