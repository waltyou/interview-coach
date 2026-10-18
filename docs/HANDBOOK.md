# Interview Coach Handbook

这份 Handbook 是 Interview Coach 面向使用者和开发者的产品知识入口。README 负责快速开始；这里解释它能做什么、如何选择工作流，以及用户可见的设计原则。维护者专用的发布流程和历史决策保留在私有维护文档中。

## 一句话理解

Interview Coach 使用 Git 仓库保存长期上下文，让不同 Agent 都能继续同一段面试准备。公共题库提供 Senior Big Data Engineer 基本盘，私人 Workspace 保存你的目标、资料、回答、简历和面试复盘。

## 先获得一次反馈

说先试一道，Coach 当轮给出公共题，回答和评价不写入项目；聊天平台可能保留对话。想保存进度或按个人情况准备时再确认保存方式并补最小画像。产品导览也可直接开始。

说先做 8 题短测，Coach 在保存方式明确后，从建模、系统设计、沟通、SQL、数据处理、存储、质量与诊断、工程编码各选一题。题目不足或你缩小范围时，结果会明确列出本次未涉及的能力。短测只提供初步观察，每类一道题不能代表全面掌握。

## 第一次使用

Agent 首先按 [运行环境](PLATFORMS.md) 检查基础 Python 环境，并适配当前系统的命令。基础练习不要求安装简历导出依赖；用到 PDF 时再检查对应工具。环境检查不会读取或上传个人资料。

在仓库根目录打开支持 `AGENTS.md` 的 Agent，然后说：

```text
帮我初始化 Interview Coach。
```

Agent 会确认私人数据的保存方式和当前目标，然后邀请你通过聊天、简历、其他资料或混合方式完成第一次 Candidate Discovery。它会先使用你已经提供的信息，再带你完成第一个实际结果。进度保存在仓库中，因此换一个 Agent 或下一次继续时不需要重新回答。

你可以随时说：

```text
继续 onboarding。
查看 onboarding 状态。
跳过 onboarding，直接开始基线练习。
```

## 选择正确入口

| 当前需要 | 可以这样说 | 第一个结果 |
| --- | --- | --- |
| 全面摸底 | 开始 Senior Big Data Engineer 基线练习 | Baseline PreparationCycle 和第一道题 |
| 准备职位 | 我有一个目标职位，帮我建立定向准备 | Job Brief、Question Plan 和定向周期 |
| 导入知识 | 把 workspace/sources 里的资料加入我的 Coach | Source Catalog 和待整理题目 |
| 维护简历 | 帮我建立完整简历，先不要改写事实 | 完整简历入口和事实缺口清单 |
| 定制简历 | 根据这个职位分析我的简历，先给修改建议 | 差异建议，确认后生成定制版本 |
| 面试复盘 | 记录我刚结束的面试 | 与 Job 和 InterviewStage 关联的复盘 |
| 日常复习 | 继续当前准备周期 | 一道题、评价和新的 AttemptEvent |
| 查看进展 | 总结我的覆盖率、薄弱点和下一步 | 基于历史事件的进度报告 |

## 核心生命周期

```text
聊天、资料或经历
    ↓ 用户确认
CandidateProfile
    ↓ 教练从练习和反馈中持续观察
CoachObservation → CoachModel

资料或经历
    ↓
Source
    ↓ 提炼可训练内容
Question
    ↓ 按目标建立快照
PreparationCycle
    ↓ 每次回答
AttemptEvent
    ↓ 确定性重建
CycleProgress / MasteryState / Dashboard / Report
```

原始资料先形成草稿。Coach 会补足影响作答的输入输出和业务条件，把复杂考点分成主问与追问，并核对评分依据后再加入题库。系统设计题仍保留澄清需求的空间，行为题允许你选择真实经历。故事建议和诊断结论留在教练侧，未提出的追问不会算作漏答。具体维护流程见 [题目质量协议](../protocol/QUESTION-QUALITY.md)。每次回答保存为不可变事件，掌握度和 Dashboard 可以随时重建。

## Onboarding 生命周期

```text
new
  ↓ privacy
in_progress
  ↓ goal → profile（Candidate Discovery）→ materials → first_value
completed

任意阶段经用户明确选择 → skipped
```

`privacy` 和 `goal` 决定后续行动边界。个性化入口的 `profile` 是必要步骤，explore 可跳过；免保存试练先出题。画像可以只包含最小、已确认的事实，不要求填完整问卷；`materials` 可以跳过。`first_value` 要求在当前对话中完成一个实际结果。

## 今天练习与下次继续

你可以说今天练 30 分钟。Coach 先恢复上次未完成题目，再按准备周期策略继续。Dashboard 优先沿用该会话的预算；没有当前会话时使用已确认的练习时长偏好，最后才采用默认 15 分钟。临时调整预算只更新当前会话，不改写你的长期偏好。新日常周期使用 mixed：两道到期题后引入一道新题，一类为空时使用另一类。spaced 只练到期题；全面摸底先按能力覆盖新题。已有周期保留已选策略，可要求改为日常混合复习。

练习出题前保存题目快照，给提示前保存提示文本，追问或重答前保存待答内容。暂停或换 Agent 后说继续，即可读 workspace/sessions/ 接回进度。免保存试练以及升级前没有保存的中间步骤，仅能依靠原聊天上下文恢复。

学习练习先指出一个关键问题，邀请你再答一次；想看完整答案时直接提出。模拟面试逐题作答，结束时集中展示评价。每次真实重答都算新的作答；查看答案后的复述只作为辅助练习，不能证明独立掌握。Coach 会在展示完整答案前保存标记，换 Agent 后继续沿用，并写入后续回答。辅助高分保留为练习成绩，掌握度与到期日仍沿用上次独立作答。没有独立证据时标为待独立验证，从首次练习的次日安排验证；重复看答案不会把复习日期继续推后。旧回答缺少辅助标记时保留原始成绩，等待新的独立作答确认。

Dashboard 首页提供续练、按会话预算安排的任务、两个优先改善点及其回答依据、最近可比较的进步。建议是生成时的快照，真正开始时会重新核对日期与进度；多周期或多会话时先选择。未测主题单独展示，避免被误当成薄弱项。

公共基础仓库随附 [公共题库预览](../dashboard/public.html)，展示本次发布的公共题库和空白学习状态。个人练习后运行 `python scripts/build_dashboard.py` 生成自己的 `dashboard/index.html`；公共预览与个人页面分开保存。

## 核对与更正评价

你可以指出评分与原回答不一致。Coach 对照原答和评价依据重新核对，追加评分更正并说明原因。原始回答和历次评价都保留；作答次数不变，到期日按原作答日期和更正后的评分重算。已完成周期报告保留结束时的结果。复习册显示当前评价及此前分数，历史文件可用于进一步核查。

## Coach 如何理解你

Candidate Discovery 不等于让你填写一张长表。你可以选择直接聊天，提供简历、题库、笔记、职位描述、面试反馈或项目资料，也可以组合使用。Agent 会先读材料，概括已经知道的内容，再只询问影响下一步的重要缺口。

系统刻意区分三类信息：

- `CandidateProfile`：你确认的背景、目标、偏好和材料清单，是个人事实来源。
- `CoachObservation`：Agent 基于某次回答、对话或反馈形成的带证据判断，按事件追加。
- `CoachModel`：从观察重建的强项、缺口、风险和矛盾信号，用于调整后续 Coaching。

单次表现不会立刻变成稳定标签。一个信号默认只是 emerging，至少两个独立证据才进入明确的强项、缺口或风险列表。你可以随时纠正 CandidateProfile，新的观察也可以显式替代旧观察。

## 公共能力与私人 Coach

`library/questions/` 是公共 Senior Big Data Engineer 基线。`workspace/` 是你的私人 Coach，包含：

- `sources/`：学习资料、问答和其他输入。
- `profile/`：已确认的 CandidateProfile 和不可变 CoachObservation。
- `questions/`：个人经历、具体公司、职位和项目相关题目。
- `jobs/`：职位定义、Job Brief 和 Question Plan。
- `cycles/`：有目标和范围的准备周期。
- `events/`：原始回答与评价历史。
- `resume/`：完整简历、岗位定制版本和 PDF。
- `state/` 与 `reports/`：从事件重建的视图。

公共题库负责通用能力，私人 Workspace 负责相关性。导入自己的资料不会要求你修改协议，也不会自动成为公开贡献。

复盘和新增题目时，Coach 也会识别经历背后的通用技术与协作能力。你希望贡献题库时，可以授权它保留私人原题、独立编写适合分享的通用题；已有题覆盖的能力优先补充场景或追问。符合质量、角色范围与内容权利要求的题优先沉淀为公共内容，涉及隐私或尚不明确的内容继续保留私有。

## Git 与隐私

推荐把公开仓库作为 `upstream`，把自己的 private repository 作为 `origin`：

```powershell
git remote rename origin upstream
git remote add origin <your-private-repository-url>
git push -u origin main
```

公开更新通过以下方式进入个人版本：

```powershell
git fetch upstream
git merge upstream/main
git push origin main
```

Git remote 的存在不能证明仓库一定是 private。导入个人资料前需要由用户确认。只在本地使用也是有效选择。

## Agent 如何使用仓库

支持 `AGENTS.md` 的 Agent 会从仓库入口获得行为规则，再按任务读取相关协议和数据。自然语言请求是主要界面，脚本用于保证状态转换和数据重建稳定。

常用请求：

```text
我该怎么使用这个项目？
Interview Coach 能帮我做什么？
解释这个项目的数据设计。
开始或继续 onboarding。
继续当前准备周期。
根据最近回答找出三个薄弱点。
把这份职位描述加入我的准备计划。
记录刚才的面试并关联对应职位。
```

当用户询问产品能力、使用方式或设计时，Agent 优先读取本文件，再根据具体问题深入协议或数据，避免把所有实现细节一次性展示给用户。

## 设计原则

### Repository-first

长期上下文保存在普通文件中。用户拥有数据，可以审查、版本化、迁移，也可以更换 Agent。

### Agent-agnostic

协议依赖文件和行为约定，不绑定 Codex、Claude 或特定模型。脚本提供确定性操作，Agent 负责理解目标和处理例外。

### Facts before projections

CandidateProfile、Source、Job、完整简历、CoachObservation 和 AttemptEvent 是事实来源。CoachModel、Dashboard、状态和报告是派生结果，可以重建。

### Public baseline, private relevance

公共题库提供通用基本盘。真正贴合个人背景和职位的内容保存在私人 Workspace。

### Progressive disclosure

默认入口只提供当前行动需要的信息。README 用于开始，Handbook 用于理解产品，协议和 Schema 用于执行细节。

### First value before complete setup

用户无需先录入全部资料。Onboarding 围绕当前目标收集最少上下文，并在同一次对话里完成一个实际结果。

## 常见问题

### 必须导入简历才能练习吗？

不需要。可以通过简短聊天建立最小画像后直接使用公共基线。简历和其他资料用于减少重复提问并提高针对性。

### 必须创建 private repository 吗？

不需要。可以选择只在本地保存。如果需要把个人资料推送到远端，private repository 是推荐方式。

### 换 Agent 后会丢失进度吗？

不会。CandidateProfile、CoachObservation、Onboarding、PreparationCycle 和 AttemptEvent 都保存在仓库中。新 Agent 读取 `AGENTS.md` 和对应文件即可继续。

### 可以直接修改 Dashboard 或报告吗？

它们是派生视图。应修改事实来源或记录新的事件，然后重新生成。

### 如何了解更精确的执行规则？

Onboarding 读取 `protocol/ONBOARDING.md`，练习读取 `protocol/COACHING.md`，领域术语读取 `protocol/TERMS.md`，简历任务读取 `resume/AGENTS.md` 和 `resume/RESUME_RULES.md`。

## 按当前理解学习

可以直接说教我这个概念、这里没懂或继续上次教学。Coach 先利用已有回答确定卡点，再给出一条短学习路径，每次讲清一个步骤，用小问题检查理解，最后换条件验证能否应用。能够独立完成新任务后回到原题口述。模拟面试结束后再集中教学。

正式教学随当前练习保存在私人 Workspace，暂停或换 Agent 后会恢复上次待回答的问题。已有练习直接复用；单独学主题也可以在准备周期下开始，无需先为每个小问题建立题库条目。可以随时说先停在这里，保留进度以后继续；明确结束教学时保存总结和待验证内容。

教学小检查用于调整讲解，不计入题库覆盖或掌握度。刚听完讲解的重答保存为辅助练习，后续独立作答再更新掌握与复习间隔。免保存试练中的教学继续只在当前对话中进行。

例如：教我理解 Python iterator，先看看我卡在哪里；或者：继续上次教学，从待回答的检查开始。
