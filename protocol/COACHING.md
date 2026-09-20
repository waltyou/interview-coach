# Coaching Protocol

## 目标

帮助用户从已有知识逐步恢复独立回答能力。经用户选择保存的训练结果写入私人 Workspace，使任何后续 Agent 都能继续。免保存试练只在当前对话中进行。

用户说先试试、先试一道时，优先执行 ONBOARDING.md 的快速试练，不以画像或 Onboarding 状态作为前置条件。

新 Workspace 的首次交互先读取 Manifest 的 `onboarding` 配置，并遵循 `ONBOARDING.md`。Onboarding 完成、跳过或已有个人数据后，再按本协议进入正常 Coaching 生命周期。

CandidateProfile 存在时，开始规划前先读取其中已确认的背景、目标和偏好。CoachModel 存在时同时读取，但把它视为基于证据的可重建判断，而不是候选人事实。需要继续了解用户或更新画像时遵循 `DISCOVERY.md`。

## 默认 Coach 与用户扩展

公共版本默认是一名面向 **Senior Big Data Engineer** 的 Coach。内置题库优先覆盖数据架构与建模、SQL、批流处理、消息系统、分布式系统、存储与表格式、数据质量、性能与故障诊断、工程编码、系统设计和 Senior 行为能力。它是可直接练习的基线，不承诺穷尽某个岗位的全部技术栈。

使用者可以通过自己的简历、职位描述、学习资料、问答和面试经验建立私人 Coach。Agent 必须遵守以下边界：

- 新资料先登记为 Source，再判断是否值得生成 Question；不得把所有标题机械转成题目。
- 与具体个人、公司、职位、简历或项目经历相关的 Question 默认进入 `workspace/questions/`，并设为 `private`。
- 无法确认公开权利或是否包含私人上下文时，必须选择 `private`。
- Question 只有 `public` 和 `private` 两种可见性。`library/questions/` 中的题目全部公开，`workspace/questions/` 中的题目全部私人。
- 用户扩展题库不改变公共 Coach 的默认定位，也不要求把私人资料贡献回公共仓库。

每次复盘或新增/修订题目时，主动识别背后的通用技术、工程决策或行为能力，并对照公共题库去重。已有覆盖时考虑补充场景或追问，有独立训练价值时可以编写通用衍生题。个人原题、回答与衍生关系保持私有。通用题需要独立题干、评分标准、提示和追问，全面移除私人事实；内容权利、隐私或角色范围不明时仍保持 private。用户已授权共享整理的维护工作区，符合准入条件的题优先进入公共基线；其他使用者的私人材料不自动成为公开贡献。允许没有合适的通用衍生题。

## 简历与 Job 的协同

Resume、Job 和 PreparationCycle 共享同一个职位上下文。完整简历负责保存已经确认的职业事实；Job 与 Job Brief 负责表达目标职位及其要求；岗位定制简历是两者的派生物；Question Plan 和 job-targeted PreparationCycle 使用同一个 Job 进行面试准备。

处理简历任务时：

1. 读取 Manifest 中的 `resume` 与 `resume_tool` root，再读取 `resume/AGENTS.md` 和 `resume/RESUME_RULES.md`。
2. 修改任何简历正文前，先读取完整简历和目标 Job 上下文，向用户给出拟修改内容或差异摘要，并等待明确确认。
3. 缺少事实或事实含义不清时，向用户确认。确认后先更新完整简历，再派生到岗位定制版本。
4. 新的岗位定制简历在对应 Job Brief 中记录 Markdown 与 PDF 路径。尚未结构化的职位描述先作为 Job Source 保存，实际进入求职流程时再建立 Job、Question Plan 和 PreparationCycle。
5. 完整简历可以作为私人 Source 帮助生成个人经历题。岗位定制简历只在确需按该版本训练时显式加入 `source-list.txt`，避免多个版本重复形成 Source。
6. 导出 PDF 后检查页数和视觉布局。定制简历超过两页时先向用户说明内容取舍，得到确认后再修改正文。

## 开始一次练习

1. 读取 `manifest.json` 和 `protocol/TERMS.md`。
2. 找到用户指定的 PreparationCycle，或者选择唯一的 active PreparationCycle。
3. 从 `library/questions/` 和 `workspace/questions/` 读取题目快照，再读取 `workspace/state/cycles/<cycle-id>.json`。
4. 运行 `python scripts/practice.py status`，优先恢复该周期的未完成 PracticeSession。多条时请用户选择。
5. 无未完成会话时，用 `python scripts/practice.py start --cycle-id <id> --minutes 15 --mode learning` 保存本次目标、预算和模式，再按周期的 review_policy 选题。`select_next.py` 会在展示题目前保存题目快照；已有未完成题目时返回 resume。
6. 每次只向用户展示一道题，不提前展示参考答案、Rubric 或完整 Source。

存在 Python 时，可以调用 `scripts/select_next.py --cycle-id <cycle-id>`。无法执行脚本时，按照本文件直接选择。

## PracticeSession 边界

PracticeSession 保存在 Manifest 的 sessions root（默认 `workspace/sessions/`）。新会话未指定预算时读取 CandidateProfile.preferences.session_minutes，仍无有效偏好时采用 15 分钟。继续会话沿用其预算；用户临时调整时用 checkpoint --minutes 更新。它保存当前题目及 revision、Prompt 快照、已用提示的序号与文本、待回答的追问或重答提示、练习模式、目标和时间预算。

暂停、隔天或更换 Agent 时保留同一未完成会话。用户明确结束或另开一次时将旧会话标记 completed，再创建新会话。已结束周期中的旧会话仅用于回顾；多个 active 周期或未完成会话存在歧义时先选择，不按修改时间猜测。

阶段为 `ready`、`awaiting_answer`、`awaiting_followup`、`awaiting_retry`、`completed`。出题、提供提示和提出追问前都保存 checkpoint。恢复时展示当前题和必要上下文；已用提示沿用原序号，已公开的提示可重新展示。题目已修订或归档时保留快照并说明变化，由用户决定继续还是换题。

```text
python scripts/practice.py checkpoint --session-id <id> --hint-level 1 --hint-text "已给出的提示"
python scripts/practice.py checkpoint --session-id <id> --stage awaiting_retry --pending-prompt "请补充一个关键取舍，再答一次"
python scripts/practice.py checkpoint --session-id <id> --reference-seen
python scripts/practice.py answer-context --session-id <id>
python scripts/practice.py checkpoint --session-id <id> --minutes 30
python scripts/practice.py checkpoint --session-id <id> --stage ready
python scripts/practice.py finish --session-id <id>
```

展示完整参考答案前，先保存 checkpoint --reference-seen。它会把当前题目标记为 reference_seen，并记入本会话的 reference_seen_questions；跨 Agent、重答或同一会话再次选择该题时沿用。分级提示将辅助程度设为 hints，不能覆盖已有 reference_seen。旧会话无法证明是否展示过完整答案时返回 unknown，不自动宣称独立。

写回答事件前运行 answer-context，把输出的 cycle_id、practice_session_id、question_id、question_revision、hints_used 和 assistance 合入 Event，随后再追加用户原回答与评价。unknown 时保持 assistance 缺失；先用已知对话或用户确认澄清，避免制造事实。不能因为换 Agent、没有分级提示或高分而重置辅助状态。

准备换题时先写 AttemptEvent、重建状态，再将会话标记 ready。若写入后中断而未更新 checkpoint，后续 Agent 先核对该会话、题目和时间对应的 Event，使用已保存的回答继续反馈，避免重复记录或要求用户重答。用户明确要求重答是新的真实作答，允许绕过当天自动选题的去重。

旧 Event 只有 practice_session_id 时仍可回顾历史；旧对话没有保存的提示或待答阶段无法还原，应明确说明并从新会话开始。

## 提示阶梯

用户回答困难或主动要求提示时，按 `hints` 的顺序一次提供一级。每次提供前将提示序号和实际提示文本保存到会话 checkpoint。

题目没有预设提示时，Agent 可以根据 Source 生成简短提示。提示应帮助检索记忆，避免直接给出完整答案。

## 评价回答

用户回答后，再读取 Question 的 `rubric` 和 `source_refs`。评价需要包含：

- 简短概括用户实际回答。
- 正确内容。
- 核心错误或遗漏。
- 四维评分：`recall`、`correctness`、`depth`、`communication`，范围为 0 到 4。
- 根据练习模式决定何时展示反馈和参考表达。完整参考表达在用户请求或完成重答后提供，尚未提供时可省略 improved_answer。
- 必要时提出一个深入追问。

学习练习（learning）默认先肯定具体正确点，再指出一个最关键遗漏，邀请用户重答一次。先将阶段保存为 awaiting_retry，并保存重答提示；用户选择看答案、跳过或继续时直接照办。重答与初答各保留真实 Event，并记录已用提示；看过完整答案后的重述只视为辅助表达练习，在反馈中标注，不能作为独立掌握的证据。

模拟面试（mock）逐题集中作答，题间只确认收到回答，四维评分和讲解延至用户结束时统一展示。回答仍及时保存到 Event；用户主动查看报告会看到评价，应在开始时说明。用户要求反馈或提示时提供，并记录模式内的辅助情况。

练习结束时给出三项简短总结：今天完成的练习、有证据的改善、下次优先练什么。没有可比较证据时说明尚需观察，不把未测到的能力判为薄弱。

Question 的 `rubric` 为空时，以 `source_refs` 对应章节作为评价依据，并在反馈中注明依据来源。

评分含义：

```text
0  无法回答或存在核心错误
1  依赖大量提示，只能回答零散内容
2  部分正确，存在明显遗漏
3  能独立完成，只有少量遗漏
4  回答完整，能够处理深入追问和权衡
```

## 写入 AttemptEvent

每次回答后，在 `workspace/events/YYYY/MM/` 创建一个新的 JSON 文件。文件必须符合 `attempt-event.schema.json`。

必须保留：

- 用户原始回答。
- 使用过的提示。
- 本次辅助程度 assistance：independent、hints 或 reference_seen。看过完整答案后即使没有分级提示也必须记录 reference_seen；旧事件缺少该字段时不推断为独立作答。
- Question ID 与 revision。
- PreparationCycle ID 与 PracticeSession ID。
- 四维评分、遗漏和反馈。
- 执行评价的 Agent 标识。

Event 创建后保持只读。用户质疑评分时，先对照原回答和 Rubric 重新核对，解释维持或修正的依据。需要更正评价时，将完整评价对象写入私有 JSON，运行 `python scripts/reevaluate.py --attempt-id <原始回答ID> --evaluation <评价JSON路径> --reason "更正依据"`。脚本追加 attempt.reevaluated，通过 supersedes 关联最近的评价，并保留 corrected_at 和 correction_reason。原回答、提示、题目、所属周期和作答时间保持原值。

重建、历史、复习册和 Dashboard 统一使用最新有效评价，真实作答次数及最近作答日期不增加；复习间隔从原作答日期按新分数计算。原始与更正文件都保留。已完成周期的固定报告仍表示结束时的情况，查当前评价时读取事件。已有 CoachObservation 不自动改写；若更正影响相关判断，Agent 追加 supersede 观察并重建 CoachModel。

一次回答可以成为 CoachObservation 的证据，但不要把单次高分或低分直接当作稳定强项或弱项。出现重复成功、重复卡点、沟通模式、目标变化或真实面试反馈等值得跨会话保留的信号时，追加有明确 evidence reference 的 CoachObservation，并运行 `scripts/coach_model.py rebuild`。用户纠正的是事实时更新 CandidateProfile；Coach 修正自己的判断时，用新观察 supersede 旧观察。

## 更新状态

Event 写入后运行：

```powershell
python scripts/rebuild_state.py
```

该命令同时刷新 `dashboard/index.html`。如果 Agent 按照协议直接重建投影，也必须随后运行 `scripts/build_dashboard.py --skip-rebuild`。

Dashboard 刷新时还会从全部 AttemptEvent 重建 `workspace/reports/answer-review.md`。复习册按 Question 归组，保留每次原回答、建议表达、遗漏点和教练反馈。它是可重建投影，不能替代只追加 Event。

掌握证据与练习记录分开。独立证据必须显式记录 assistance=independent，且 hints_used 为空。scores、knowledge_score、review_interval_days 和 next_due_at 取最近独立证据的分数与原作答时间；辅助高分不替代它，也不延长其复习间隔。最近任何一次练习保留在 latest_attempt_scores、last_attempt_at 和 last_event_id 中，evidence_event_id 指向独立证据。

没有独立证据时 scores 和 knowledge_score 为 null，evidence_status 为 awaiting_independent。从第一次记录的练习次日安排一次独立验证（间隔 1 天）；此后的辅助练习不把这个日期向后推。旧事件缺少 assistance 时同样待验证，原始评分和评价照常保留。覆盖只表示练过；当天已练题目仍跳过自动选题，用户明确要求重答时继续。

四维平均分、强弱项和最近进步都以独立证据为依据；无独立证据单列为待验证。已结束周期的固定报告保留当时语义，新报告标明独立作答分数。CoachObservation 是独立保存的判断，必要时根据新证据追加修正，不批量改写历史。

独立作答的间隔规则：

```text
knowledge_score = min(recall, correctness, depth)

0 -> 1 天后复习
1 -> 2 天后复习
2 -> 4 天后复习
3 -> 10 天后复习
4 -> 30 天后复习
```

`communication` 保留为面试表现指标，不影响知识复习间隔。

`workspace/state/cycles/<cycle-id>.json` 是当前 PreparationCycle 的进度入口。它必须包含：

- PreparationCycle 当前状态和题目总数。
- `unseen`、`covered`、`due` 数量与覆盖率。
- 总回答次数、今日回答次数和四维平均分。
- 每道题的最近评分、知识分、复习间隔和 `next_due_at`。

状态变化如下：

```text
unseen -> 回答并记录 AttemptEvent -> covered -> 到达 next_due_at -> due
```

下一题选择前必须从 AttemptEvent 重建或核对状态，不能依赖可能过期的投影。

## PreparationCycle

PreparationCycle 表示一次准备或复习周期，与公司的 InterviewStage 区分。

周期开始时默认快照符合范围的所有 active Question。周期期间新增问题只有在用户明确刷新题目快照时才加入。

`kind` 定义准备目的：

```text
baseline        全面覆盖，发现真实薄弱点
maintenance     非求职期低频维护
job_targeted    针对职位的准备
stage_targeted  针对 InterviewStage 的短时强化
```

`job_targeted` 必须通过 `job_id` 关联 `workspace/jobs/` 中的 Job。创建周期时按 Job Question Plan 的顺序冻结题目快照；首次覆盖也按该顺序进行，确保高优先级题目先出现。`stage_targeted` 仍只能表达意图，不能保存 InterviewStage 的结构化引用。

## 针对具体职位准备

1. 在 `workspace/jobs/` 创建 Job，并把职位分析保存为仓库内的私有 Job Brief。
2. 为岗位特有问题生成 private Question；通用知识题可以复用 public Question。
3. 在 Job 的 `question_plan` 中按面试价值排序，记录 `must`、`should` 或 `stretch`、建议作答时长和入选理由。
4. 使用 `start_cycle.py --kind job_targeted --job-id <job-id>` 创建 PreparationCycle。脚本只冻结该 Job 的 Question Plan，不会把同 topic 的整个题库一并加入。
5. Job Brief 或 Question Plan 后续可以继续修订；已经创建的 PreparationCycle 保持原有题目快照。

支持四种选择策略：

```text
coverage_once          每题覆盖一次后结束
spaced                 只选择已到期题目，不引入新题
mixed                  日常练习，每日按两道到期题、一道新题交替；某类为空时使用另一类
coverage_then_spaced   先覆盖全部，再按 next_due_at 复习
```

maintenance 新周期默认使用 mixed；baseline 保持 coverage_then_spaced。已有周期的策略原样保留，用户要求日常混合复习时再调整该周期 review_policy。首次覆盖按一级 topic 的已覆盖题数优先补齐能力，再在该能力内抽题；Job 精选顺序优先。

用户要求短测时创建 `start_cycle.py --name "8题短测" --kind baseline --visibility public --limit 8 --policy coverage_once`。按数据建模、系统设计、沟通与 Senior 行为、SQL、数据处理与分布式系统、存储与表格式、数据质量与故障诊断、工程编码八类能力分配名额。每类至少一题后再填剩余名额；请求少于八题时优先建模、系统设计和沟通。尊重用户指定的 topic 和 visibility，缺少某类时明确列出，不突破范围补题。

创建时在 diagnostic 中冻结能力范围、可用能力、抽样前主题、选中题目的能力与主题映射。报告和 Dashboard 使用该快照，明确列出本次未涉及、尚未作答、尚无独立证据和当前题库或范围缺少的能力。八题练完只说明完成了短测，每类一道题仍只能提供初步判断。旧周期缺少快照时只报告已有范围，不猜测当初被排除的题目。

新的 PreparationCycle 会重置 CycleProgress，但保留 MasteryState 和全部 AttemptEvent。新周期中所有快照题目都重新具备被覆盖的资格。

## 结束 PreparationCycle

PreparationCycle 由用户主动结束。是否要求覆盖全部题目由用户决定；提前结束时报告必须保留未覆盖题目。

结束流程：

1. 将 PreparationCycle 的 `status` 改为 `completed` 并写入 `completed_at`。
2. 从全部 AttemptEvent 重建最终 CycleProgress。
3. 在 `workspace/reports/cycles/` 生成同名 JSON 和 Markdown CycleReport。
4. 刷新 `dashboard/index.html`。
5. 报告生成后视为结束时的固定快照，不随未来日期或其他 PreparationCycle 的复习而改写。

存在 Python 时可以运行：

```powershell
python scripts/complete_cycle.py --cycle-id <cycle-id>
```

需要确保全部题目至少覆盖一次时，增加 `--require-coverage`。

## Question 生命周期

```text
active -> archived
archived -> active
```

归档题目时保留所有 AttemptEvent、CycleProgress 和 MasteryState。active PreparationCycle 选择下一题时跳过已经 archived 的 Question。

Question 生成后直接进入训练，不建立独立审核状态。`visibility=public` 的题目保存在 `library/questions/`；`visibility=private` 的题目保存在 `workspace/questions/`。无法确认能否公开时默认归为 `private`。PreparationCycle 默认可以同时快照两类题目。

## InterviewExperience 进入题库

真实 InterviewStage 结束后，先把事实和复盘整理为仓库中的受支持 Source，并把仓库相对路径加入 `source-list.txt`。然后：

1. 运行 `initialize.py` 更新 Source Catalog，只深入读取输出中的 `pending_source`。
2. Markdown 直接读取正文；XMind 按 sheet 和主题树读取；PDF 按 page 读取；PPTX 按 slide 读取文本和 speaker notes。
3. PDF 和 PPTX 必须检查视觉渲染结果。源码截图、图表、架构图、扫描页和空间关系不能只依赖文本层。XMind 出现关联线、浮动主题、图片或依赖空间位置的表达时也要检查缩略图。先用 metadata 和缩略图定位，再深入查看相关内容单元。
4. 从 Source 中生成完整 Question，并检查重复题和 SourceRef。Prompt 必须脱离 Source 独立成立；不得保留“这种思维”“上述方法”等没有先行词的指代，也不得只复制章节主题名。
5. 非 Markdown SourceRef 使用 `unit_label` 与 `unit` 定位 page、slide 或 sheet，并用 `heading` 记录该单元内的标题或主题。
6. 判断题目是 `public` 还是 `private`；具体公司、个人职业经历和项目上下文题默认私人。同时检查能否提炼可独立训练的通用问题，或为已有公共题补充有价值的场景与追问。已有共享授权且满足准入条件时优先沉淀公共内容；无法确认时使用 `private`，不为增加数量强行转换。
7. 题目直接设为 `active`，需要时补充 Rubric、Hints 和 Follow-ups。
8. 完成整份 Source 的语义与视觉抽取后，运行 `initialize.py --mark-extracted <repository-relative-path>` 记录本次内容哈希。部分处理时保持 pending。
9. 新题默认只进入未来 PreparationCycle；当前题目快照必须由用户明确刷新。

## InterviewExperience Job 关联

用户开始回忆真实面试时，Agent 必须把 Job 关联作为同一次录入流程的一部分，不能等待用户以后主动提醒。

1. 先检查用户当前消息和连续对话中是否已经提供 Job ID、Job Brief 路径、职位链接、公司与职位名称，或明确指向某个已有 Job。
2. 线索能够唯一匹配 `workspace/jobs/*.json` 中的 Job 时，直接写入 Job ID、Job Brief 链接和 InterviewStage。用户已经给出明确职位时，不再询问确认。
3. 用户没有提供职位线索，或线索匹配多个 Job 时，先把已经回忆出的事实写入 InterviewExperience，使用 `Job ID: unresolved`，然后主动询问需要关联哪个职位。存在候选 Job 时，优先列出简短候选，而不是让用户重新描述职位。
4. 用户明确表示这次面试不属于任何已跟踪 Job 时，记录 `Job ID: untracked`。对已经是有效 Job ID 或 `untracked` 的同一份 InterviewExperience，不重复询问。
5. Job 确认后，在 InterviewExperience 中记录公司、职位、Job ID、Job Brief、InterviewStage，以及能够确定的关联 PreparationCycle；同时在 Job Brief 的面试进展中增加返回 InterviewExperience 的链接。
6. PreparationCycle 关联只用于追溯。除非用户明确要求，否则不结束 PreparationCycle、不刷新 Question 快照，也不修改 Job Question Plan。
7. 后续口述属于同一个日期、Job 和 InterviewStage 时，优先追加到已有 InterviewExperience，避免为一次面试建立多个零散文件。

`validate.py` 会检查 `tech/interview/experiences/` 中每份 Markdown 是否包含 Job ID 和 InterviewStage。`unresolved` 会产生持续 warning，直到用户提供职位或明确选择 `untracked`。

## 历史回顾

`workspace/events/` 是完整历史。`workspace/state/` 是快速投影。`workspace/reports/cycles/` 是已结束 PreparationCycle 的固定总结。

`workspace/reports/answer-review.md` 是面向日常复习的可重建汇总。Dashboard 提供入口，独立的 `dashboard/review.html` 展示相同的完整历史，并支持搜索与 PreparationCycle 筛选。两个复习入口都以最近一次回答为先，同时保留同一道题的此前尝试，不能只展示最近一次。

Agent 回顾历史时应能够回答：

- 当前 PreparationCycle 已覆盖多少题。
- 哪些题当前到期。
- 哪些知识长期薄弱。
- 某道题历次回答如何变化。
- 不同 PreparationCycle 的覆盖率和评分如何变化。
- 某个 PracticeSession 中完成了哪些回答。

## 隐私

`library/questions/` 中的 Question 是公共基本盘。`workspace/questions/`、准备周期、回答、状态、报告、Source Catalog、`source-list.txt` 和个人简历都属于使用者的私人上下文。不要把私人上下文复制到 `library/`；提交或分享仓库前必须检查实际 Git remote 与待提交文件。
