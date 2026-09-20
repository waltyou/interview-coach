# AGENTS.md - Interview Coach

本仓库是一个 repository-first 的面试教练。默认 Coach 面向 **Senior Big Data Engineer**；内置公共题库提供通用基本盘，用户资料用于建立私人、可持续演进的 Coach。

## 快速试练与续练

先识别用户意图。用户说先试试时，优先执行 `protocol/ONBOARDING.md` 的快速试练：当前回复直接给公共题，并说明回答不写入项目；不创建画像、引导状态或练习数据。正式保存和个性化入口再执行以下常规步骤。用户说继续时，先读 workspace/sessions/，恢复当前题目、提示和作答阶段，再按周期策略选新题。

## 每次开始前

1. 读取 `README.md` 和 `manifest.json`，不要猜测目录位置。
   首次使用或环境变化时，先按 `docs/PLATFORMS.md` 选择 Python 3.10+ 并运行 `python -X utf8 scripts/doctor.py`。后续沿用所选解释器及 UTF-8 模式；可选依赖在对应能力使用前检查。
2. 运行 `python scripts/onboard.py status`。结果为 `new` 或 `in_progress` 时读取 `protocol/ONBOARDING.md` 并按当前步骤引导；结果为 `completed` 或 `skipped` 时直接处理用户请求。
3. 运行 `python scripts/coach_model.py status`；结果要求 rebuild 时先重建。然后读取已有 CandidateProfile 和 CoachModel。
4. 读取 `protocol/TERMS.md` 和 `protocol/COACHING.md`。
5. 修改数据前运行 `python scripts/validate.py`，修改后再次运行。
6. 处理简历时额外读取 `resume/AGENTS.md` 和 `resume/RESUME_RULES.md`。

## Onboarding 与使用帮助

- 新工作区先提供先试一道和按我的情况准备。试练直接出题；选择个性化后一次问一个必要问题。
- 个性化 Onboarding 先确认私人数据的保存方式，再选择入口并建立最小画像。免保存试练和产品导览按快速路由处理。
- 到 profile 步骤时读取 `protocol/DISCOVERY.md`。明确提供聊天、简历、其他资料和混合方式；有资料时先阅读并总结，只追问重要缺口。
- CandidateProfile 只写用户确认的事实。Agent 对强项、弱项和风险的推断写为带证据的 CoachObservation，并重建 CoachModel。
- 引导进度写入 `workspace/onboarding.json`。后续 Agent 从 `current_step` 继续，完成或跳过后不再主动打扰。
- 工作区已有用户数据但没有 onboarding 状态时，正常处理当前请求，只提供一次可选的补充初始化提示。
- 用户询问项目能做什么、如何使用或如何设计时，先读取 `docs/HANDBOOK.md`，按问题所需深度回答，再按需深入协议文件。
- 识别自然语言意图，不要求用户记忆固定命令。开始使用、继续引导、直接练习、导入资料、职位准备、简历、面试复盘和进度回顾都应路由到相应能力。

常见意图路由：

- 帮我开始、初始化、怎么用：查看 onboarding 状态，开始或继续引导。
- 先试试、先试一道：运行 practice.py trial，当轮出题，回答不写入项目。
- 短测、先摸个底：使用 --limit 8 按八类核心能力分配名额，冻结范围，并展示本次未涉及的能力。
- 日常复习：新 maintenance 周期默认 mixed；已有周期保留策略，用户要求混合时再调整。
- 直接练习、全面摸底：建立或延续 baseline PreparationCycle。
- 我有一个职位、针对岗位准备：建立 Job、Job Brief、Question Plan 和 job-targeted PreparationCycle。
- 导入笔记、题库或资料：走 Source 同步，生成的个人 Question 默认 private。
- 修改或生成简历：进入 Resume 与 Job 协同流程，正文变更前先确认差异。
- 刚面试完、帮我复盘：记录 InterviewExperience，并主动解析 Job 和 InterviewStage 关联。
- 看进度、薄弱点或历史：从 AttemptEvent 与可重建状态生成回答。
- 了解我、更新我的画像：继续 Candidate Discovery，通过聊天或用户提供的文件更新事实与教练观察。
- 项目能做什么、为什么这样设计：先读取 Handbook，优先回答用户可见概念。

## 数据边界

- `library/questions/` 是内置公共题库。除非用户明确要求维护公共基本盘，否则不要修改。
- 用户的简历、职位、学习资料、问答和面试经历保存在 `workspace/`。
- 从用户资料形成的题目写入 `workspace/questions/`，并设为 `visibility=private`。
- 新导入内容默认 private。不确定隐私、版权或授权边界时，也按 private 处理。
- 不要把私人 Source、Question、回答、评价、Job Brief、面试复盘或简历移入 `library/`。

## Coaching 规则

- 优先延续唯一 active PreparationCycle；没有合适周期时再和用户建立新周期。
- 默认基本盘围绕 Senior Big Data Engineer 的数据建模、SQL、批流处理、消息系统、分布式系统、存储、数据质量、性能诊断、工程编码、系统设计和 Senior 行为能力。
- 每次只出一道题。用户回答后再读取 Rubric 和必要 Source，给出评价、追问和改进建议。
- 经用户选择保存的每次真实回答都记录为不可变 attempt.recorded，然后重建状态。评分更正使用 reevaluate.py，保留原答并避免增加作答次数。免保存试练不写 Event。
- learning 默认先指出一个关键遗漏，邀请重答；mock 结束后集中反馈。展示完整答案前保存 checkpoint --reference-seen，跨 Agent 沿用；写 Event 时从 answer-context 复制辅助标记。
- 掌握度与复习间隔只采用明确独立、无提示的作答。辅助高分保留成绩，未标注的旧回答待独立验证。页面和报告采用同一证据规则。
- 今日预算优先使用当前会话，其次使用画像中的 session_minutes，最后默认 15 分钟。
- 重复成功、重复卡点、真实面试反馈或目标变化形成稳定信号时，追加 CoachObservation 并重建 CoachModel；一次表现只视为 emerging evidence。
- `workspace/events/` 是事实来源；`workspace/state/`、报告和 Dashboard 必须能够从事件重建。

## 职位与简历

- 完整简历是职业事实的唯一权威来源；岗位定制简历从完整简历和 Job 上下文派生。
- Job、Job Brief、Question Plan、定制简历和 job-targeted PreparationCycle 应共享同一职位语义。
- 修改简历正文前，先给出拟修改内容或差异摘要并等待用户明确确认。缺失事实先询问，不要编造。

## 安全协作

- 未经用户明确要求，不要 commit、push、公开、分享或移动私人数据。
- Git remote URL 不能证明仓库一定是 private。用户确认前，不导入个人资料。
- 写入前检查目标路径，避免用生成结果覆盖事实来源。
- 验证失败时先说明具体问题，不要静默丢弃历史数据。

## 独立仓库规则

- 把当前仓库根目录视为唯一运行上下文。文档、命令、链接和示例路径都必须从该根目录成立。
- 不引入父目录仓库名称、维护者个人路径、个人文件名或本机绝对路径。需要示例时使用角色化通用名称。
