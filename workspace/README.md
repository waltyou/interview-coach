# Personal Workspace

该目录保存个人准备和练习数据。

```text
jobs/           具体职位、私有 Job Brief 与精选 Question Plan
onboarding.json 首次引导生命周期与 CandidateProfile 引用
profile/        已确认的 CandidateProfile 与不可变 CoachObservation
cycles/         PreparationCycle 定义
events/         只追加的 AttemptEvent，包含 PracticeSession ID
sessions/       当前题目、提示、待答阶段、目标与预算
questions/      个人经历、具体公司和项目上下文相关的 private Question
resume/         私人完整简历、岗位定制版本、共享页眉与生成的 PDF
state/coach-model.json 从 CoachObservation 重建的 CoachModel 投影
state/cycles/   当前 CycleProgress 投影
state/mastery/  跨 PreparationCycle 的 MasteryState 投影
reports/cycles/ 已结束 PreparationCycle 的 JSON 和 Markdown CycleReport
reports/answer-review.md 由全部 AttemptEvent 自动生成的逐题回答复习册
```

`profile/candidate.json` 只保存用户确认的事实；`profile/observations/` 保存有证据的教练判断；`state/coach-model.json` 是可重建视图。`events/` 是原回答和评价的事实来源。`reports/answer-review.md` 与 Dashboard 回答复习区也都是可重建视图，不应手工修改来替代事实来源。

`resume/Markdown/master/` 是职业事实来源，`resume/Markdown/tailored/` 是面向 Job 的派生版本，`resume/PDF/` 是可重建输出。通用规则与导出器位于相邻的 `../resume/` 工具目录。职位上下文统一保存在 `jobs/`，新的岗位简历应在对应 Job Brief 中记录路径。
