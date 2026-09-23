# Teaching Protocol

## 目标与入口

帮助用户从当前理解推进到能够解释、迁移和独立作答。用户说教我、这里没懂、继续上次教学时进入本协议；learning 练习暴露理解缺口时，先指出卡点，再自然进入局部教学。记忆遗漏优先用提示，表达问题优先练习组织和口述。mock 保持考核节奏，结束后再建立 learning 会话教学；用户明确要求中途教学时先结束 mock。

先读取 CandidateProfile、CoachModel、相关回答和已有 TeachingSession。已有证据用来减少重复探测，单次表现只形成暂时判断。只探测影响当前目标的前置概念，足以决定下一步时开始教学。

沿用用户的保存选择。免保存试练可在对话中使用同一教学方法，不创建任何文件。正式教学使用 active PreparationCycle 下的 learning PracticeSession；已有会话直接复用。主题教学可从 ready 阶段开始，current_question 可以为 null，不为教学小检查制造 Question 或修改周期快照。没有合适周期时按 COACHING.md 建立周期。

## 教学循环

1. 明确一个可检验的目标和当前卡点。evidence 引用已有 Event、Source、教学检查或用户原话，区分自述与观察。
2. 沿目标依赖做少量 probe。每次一个短问题，要求解释或推演；选择题可以辅助探测，答对后仍按需要检查理由。
3. 用短文字或 Mermaid 给出局部学习路径。只包含本次目标必需的步骤，current_step 使用零起始下标。保留已证实的知识，允许根据新回答调整 path。
4. 每次只讲一个推理步骤，随后提出一个小任务。先保存实际 explanation、prompt、assistance，再展示给用户。涉及版本或实现细节时检查权威来源，将文件章节或链接记入 sources；尚未核实的结论明确说明。
5. 用户回答后保留原话、反馈与 outcome。passed 表示当前检查完成，gap 表示需补前置概念或换解释；用户说懂了仍需要实际检查。next_action 写明后续 Agent 应做什么。
6. 局部路径完成后切到 transfer，给一个条件变化、未展示答案的任务。通过后结束本次教学。用户主动停止时保存总结和待验证内容，允许以 stopped 结束。
7. 有原题时回到 awaiting_retry，让用户重新口述。没有原题时回到 ready。参考表达在重答后或用户请求时提供。

按会话时间预算控制范围。预算不足时保留 active 教学和 next_action，下一次继续。需要跨会话保留的能力判断沿用 CoachObservation；教学事实仍在教学记录中。

## 记录与恢复

TeachingSession v1 嵌入 PracticeSession.teaching_sessions，和题目、提示、时间预算在同一次写入中保存。列表保留已完成或停止的教学；最后一条可以 active，此时 PracticeSession.stage 必须为 teaching。存储位置沿用私人 sessions root，无第二份进度事实来源。

每条教学记录保存目标、卡点、证据、原题快照（可空）、局部路径、当前步骤、phase、sources、checks、pending_check 和 next_action。每个检查保存当时步骤的文本快照，后续重排路径不会改变历史检查的含义。回答检查只能追加；plan 只能更新教学计划，不能替换历史答案。每次操作保留未知字段。

运行 practice.py status 或 teach.py status 查看未完成教学。select_next.py 遇到 teaching 阶段返回 resume_teaching 及完整教学上下文，暂停、隔天、更换 Agent 后先恢复待回答检查。存在多个未完成会话时沿用现有选择规则。完成或归档周期的教学仅回顾，继续学习应建立 active 周期和会话。题目已修改或归档时展示变更提示，保留原快照，由用户决定继续还是停止。

## 掌握证据边界

教学小检查只写 TeachingSession，不写 AttemptEvent，不改变覆盖率、作答次数、评分或复习间隔。transfer 的 independent 只说明用户独立完成了本次新任务，用于结束教学；它仍属于即时教学证据。

围绕当前原题提供解释、提示或答案时，脚本将 PracticeSession 的原题辅助状态保守标记为 reference_seen，并保留在 reference_seen_questions。该标记在此流程中包含接受过针对性教学，不限于看过完整参考答案。即时重答沿用该状态。恢复教学、答对检查或重新选择原题都不能清除它。只有 probe 且没有给过帮助时，原有辅助状态保持不变。

后续独立验证在间隔后的新练习会话中进行，先检索再讲解，使用正式 Question 和真实 AttemptEvent。辅助题目即使关闭教学后当天再答，也必须沿用已知帮助程度；不得通过创建新会话制造独立证据。新主题的变式暂留教学记录，有持续训练价值时再走 Question 准入和快照规则。

掌握度继续执行 COACHING.md 的独立证据规则。未知辅助程度的历史事件保持待独立验证，原始事件和已结束周期报告保持原样。

## 命令与载荷

下列命令从 Context Pack 根目录运行。载荷文件使用 UTF-8 JSON，放在私人 Workspace；不把含原话的文件放进公共示例目录。每次命令完成一次验证后的原子会话写入。运行失败时原记录保持原样。

```text
python scripts/teach.py status
python scripts/teach.py start --session-id <id> --input workspace/teaching-input.json
python scripts/teach.py plan --session-id <id> --input workspace/teaching-input.json
python scripts/teach.py ask --session-id <id> --input workspace/teaching-input.json
python scripts/teach.py answer --session-id <id> --input workspace/teaching-input.json
python scripts/teach.py finish --session-id <id> --input workspace/teaching-input.json
python scripts/teach.py stop --session-id <id> --input workspace/teaching-input.json
```

各命令载荷示例，按当前步骤只写其中一个对象：

```json
{"goal":"能解释迭代状态并处理耗尽","gap":"尚待确认状态由谁保存","evidence":["用户自述：不理解第二次遍历为何没有结果"]}
```

```json
{"path":["定位迭代状态","推演耗尽","迁移到单次消费场景"],"current_step":0,"phase":"teach","next_action":"检查连续取值时的状态变化","sources":["官方语言文档的 iterator protocol 章节，教学时补具体链接"]}
```

```json
{"prompt":"执行两次取值后，下一次取值从哪里继续？请解释。","explanation":"先用一个具体序列展示状态如何随取值推进。实际使用时保存完整讲解文本。","assistance":"reference_seen"}
```

```json
{"answer":"用户实际回答","feedback":"指出正确点与剩余缺口","outcome":"passed","next_action":"检查耗尽时的行为"}
```

plan 切换至 phase=transfer 后，ask 使用新的任务、空 explanation 和 assistance=independent。独立迁移检查 passed 后才能 finish：

```json
{"summary":"已完成局部理解与即时迁移检查，后续仍需延迟独立验证。","next_action":"请回到原题重新口述；下次会话先独立检索。"}
```

用户需要更多提示时，先记录当前真实回答（包括不知道），再以新的辅助检查继续，避免改写已展示检查的帮助条件。stop 可取消尚未回答的检查，原提示保留在 cancelled_checks；它保留待验证内容，不表示教学目标已达成。
