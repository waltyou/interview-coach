# Terms

本文件是 Context Pack 的领域语言入口。Agent 执行协议时必须使用下面的核心术语。

## Onboarding

新用户从空白 Workspace 到获得第一个实际结果的可恢复引导生命周期。状态保存在私有的 `workspace/onboarding.json`，持久化状态为 `in_progress`、`completed` 或 `skipped`；状态文件缺失时，Agent 结合 Workspace 是否已有个人数据区分 `new` 与 `existing`。

Onboarding 记录初始入口和 CandidateProfile 引用，用于跨 Agent 续接。CandidateProfile、PreparationCycle、Job、Source 和 AttemptEvent 保存业务事实，不能用 OnboardingState 代替它们。

## CandidateDiscovery

Coach 持续理解候选人的过程。可以通过聊天、简历、其他信息文件、练习历史、真实面试历史或这些方式的组合完成。初次 Onboarding 只要求建立可行动的最小画像，之后在目标变化或出现新证据时继续发现。

## CandidateProfile

用户已经确认的背景、目标、偏好和材料清单，保存在 `workspace/profile/candidate.json`。它是候选人事实来源，不保存 Agent 未经确认的推断。

## CoachObservation

Coach 对强项、缺口、风险或中性信号的一条不可变判断。每条观察必须有信心等级和至少一个可追溯证据；需要修正时以新观察显式 supersede 旧观察。

## CoachModel

从有效 CoachObservation 重建的候选人能力投影，保存在 `workspace/state/coach-model.json`。它汇总 strengths、gaps、risks 和 mixed signals，不是事实来源，不能手工编辑来替代观察。

## Source

由 `source-list.txt` 选中的知识文档或整理后的真实面试经验。Source 可以位于仓库中的任意目录，格式支持 Markdown、PDF、PPTX 和 XMind。Context Pack 保存引用、主题、格式、内容哈希和抽取进度，不复制整篇原文。

Source 的内容单元分别是 document、page、slide 和 sheet。Question 引用非 Markdown Source 时，SourceRef 使用 `unit_label` 与 `unit` 精确定位；`heading` 保存该单元内的标题或主题。

## Question

可以在训练中独立提出的问题。Question 保存 Prompt、Rubric、Hints、Follow-ups 和 SourceRefs。

`visibility=public` 的题目保存在 `library/questions/`，构成共享的基本盘。`visibility=private` 的题目保存在 `workspace/questions/`，用于个人经历、具体公司、职位和项目上下文。项目不存在第三种候选可见性。PreparationCycle 可以同时包含两类题目。

## Job

正在评估或面试的具体职位。Job 保存在 `workspace/jobs/`，记录职位事实、私有 Job Brief，以及有顺序的 Question Plan。Question Plan 的每一项包含优先级、建议作答时长和入选理由。

`job_targeted` PreparationCycle 必须通过 `job_id` 关联 Job，并在创建时按 Question Plan 的顺序冻结题目快照。Job 后续变化不会改写既有 PreparationCycle。

## Resume

用于表达用户职业事实或面向具体 Job 投递的简历。Resume 的私人数据保存在 `workspace/resume/`，通用规则和导出工具保存在 `resume/`。

完整简历是职业事实的唯一权威来源。岗位定制简历只能从完整简历中的既有事实派生，并使用 Job 与 Job Brief 决定取舍、排序和措辞重点。PDF 是从 Markdown Resume 生成的可重建输出。与 Resume 相关的 Source 和 Question 默认属于私人数据。

## PreparationCycle

一次有明确目标、题目快照和复习策略的准备周期。中文称“准备周期”或“复习周期”，不得简称 Round。

`kind` 有四种：`baseline`、`maintenance`、`job_targeted`、`stage_targeted`。当前版本支持前三种；`stage_targeted` 仍待 InterviewStage 结构化关联。

## PracticeSession

用户与 Agent 一次连续的练习对话。一个 PreparationCycle 可以包含多个 PracticeSession。v0.3 通过 AttemptEvent 的 `practice_session_id` 分组，暂不建立独立文件。

## AttemptEvent

用户对一道题的一次真实回答及其评价。AttemptEvent 是训练历史的事实来源。

## CycleProgress

某个 PreparationCycle 中每道题的覆盖、到期和评分状态。它是可重建投影。

## CycleReport

PreparationCycle 结束时生成的固定总结。JSON 供 Agent 读取，Markdown 供用户回顾；原始回答仍以 AttemptEvent 为准。

## MasteryState

跨 PreparationCycle 聚合的长期掌握状态。它是可重建投影。

## InterviewStage

实际招聘流程中的面试阶段，例如 recruiter screen、technical interview 或 onsite。中文可称“第 N 轮面试”。

## InterviewExperience

InterviewStage 结束后的结构化复盘。整理为受支持的 Source 并加入 `source-list.txt` 后，可以更新 Source Catalog 并生成新的 Question。

每份 InterviewExperience 必须记录 `Job ID` 和 `InterviewStage`。`Job ID` 可以是已有 Job 的 ID、等待用户补充时的 `unresolved`，或用户明确表示没有已跟踪职位时的 `untracked`。一旦关联到 Job，InterviewExperience 与 Job Brief 必须互相链接。

## 禁用的歧义词

不要使用 `Round`、`ReviewRound` 或 `InterviewRound`。准备复习使用 PreparationCycle，真实招聘轮次使用 InterviewStage。

“初始化”需要指明对象：首次产品引导称 Onboarding，扫描和同步资料称 Source initialization。
