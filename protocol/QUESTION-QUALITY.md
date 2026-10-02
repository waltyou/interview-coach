# Question 质量与入库协议

所有新建、资料导入、面试复盘派生和既有题修订都执行本协议。目标是让候选人仅凭当前题干就能开始正确作答，允许面试中有价值的澄清。Agent 自行完成检查与修复；日常入库不增加用户逐题审批。用户明确要求先 review 时先交提案。

## 七项语义检查

| 检查 | 合格条件 | 常见修复 |
| --- | --- | --- |
| standalone | 对象、任务和指代可独立理解；所需代码、表结构和样例齐全 | 将必要 Source 上下文写入题干；主题标题留在 Source |
| answer_contract | 决定结果正确性的条件明确，或明确留给候选人澄清且教练有一致的补充口径 | 固定输入输出、顺序、重复、空值、边界与错误策略 |
| interview_voice | 主问是面试官可以直接说出的提问 | 故事推荐、表达策略、评价要求进入 coach_notes |
| scope | 有一个清晰的首问，候选人能先完成一段回答 | 独立任务进入逐项 follow_ups；不按固定字数判断好坏 |
| followup_context | 每个追问说明继承哪些条件、新增哪些条件 | 补足新 schema、代码重置点、并列规则和版本；明确独立运行 |
| evaluation_alignment | Rubric、Hints 和 Follow-ups 与当前 Prompt 一致 | 未提出的追问不作为漏答；接受满足契约的合理替代方案 |
| factual_basis | 真实事实、合成设定与待验证假设分明，来源可追溯 | 不编造个人经历；版本敏感细节核对对应资料或把验证列为任务 |

编码题至少明确输入与返回形式、改变算法的规模约束、重复/顺序语义及关键边界。无需把所有想象得到的异常都堆入主问；可以声明输入已合法，再把错误处理放到追问。接口约定后用至少一个普通样例和一个能区分合理实现的边界样例手算，必要时运行参考实现。

SQL 题检查表粒度、唯一性、过滤口径、业务时区、时间区间、同值并列、输出粒度。涉及增量状态时明确完整历史还是本批增量、完整替换还是 patch、修订与删除语义。最新事件和最新实体状态是不同层次，迟到修订可能要求重建历史。

系统设计题允许候选人主动澄清规模、SLO 和权衡。必要时在 coach_notes 记录面试官可提供的合成约束；允许其他声明清楚且一致的假设。不为追求信息完整而预先给出整个架构或唯一解。

行为题允许候选人选择真实经历。具体项目复盘可以提供真实背景，但将根因、完整排查路线和预选结论留在教练侧。直接提问经验缺口或职责匹配，避免把消除疑虑、默认使用某故事作为题干指令。

## 新建与导入

1. 先确定来源、可见性、目标能力，并搜索已有题避免重复。题目私有/公开规则继续适用。
2. `initialize.py` 只同步 Source 并把明确问题放入 `workspace/imports/questions/` 草稿封装。封装保存 Source 内容哈希与 `draft`；这些文件不属于题库，不会被选题器或周期加载。重复同步保留人工草稿；Source 已变化时先对照哈希重新读取，不盲目沿用旧草稿。
3. Agent 读取完整 Source，包括必要的代码、表格与图像。自动抽取仅供定位，问号或完整句子都不能证明题目合格。非明确问题与未完成抽取的材料继续留在 Source。
4. 把完整 Question JSON 写在题库外。填写 Prompt、独立 Rubric、分级 Hints、可执行 Follow-ups；需要时添加 `coach_notes` 字符串数组。原始面试原话保留在 Source，题库保存可独立训练的版本。
5. 逐项执行七项语义检查，每项写下本题的具体依据、已固定的条件或有意保留的澄清空间。失败时修改内容并重新检查。不得用统一的通过字样代替实际审阅。
6. 在最终内容确定后，用 `author_question.py <draft.json> --fingerprint` 获取内容哈希，在草稿中写入 `quality_review`。该命令只算哈希，不执行或证明语义审查。记录格式如下：

```json
{
  "version": 1,
  "content_sha256": "最终内容的64位SHA-256",
  "reviewer": "执行本次审阅的Agent或维护者",
  "reviewed_at": "2026-10-02T12:00:00+08:00",
  "checks": {
    "standalone": "本题如何脱离Source独立成立",
    "answer_contract": "本题已固定的口径与边界",
    "interview_voice": "面试官主问与教练备注的边界",
    "scope": "主问能力及分阶段安排",
    "followup_context": "逐项核对追问新增条件的结果",
    "evaluation_alignment": "样例与Rubric核对结果，合理替代解和追问评分范围",
    "factual_basis": "来源、合成约定和版本核验情况"
  }
}
```

7. 执行 `python -X utf8 scripts/author_question.py <draft.json> --check`，再执行不带 `--check` 的同一命令入库。工具拒绝缺失审查、过期哈希、空 Rubric 和确定的格式缺陷；新题 revision=1，修订需携带当前 revision，由工具递增。工具保留未知字段和历史，拒绝陈旧草稿及隐式可见性迁移。
8. 运行 `python -X utf8 scripts/validate.py` 并修复新增错误。需要展示更新时运行 `python -X utf8 scripts/build_dashboard.py --skip-rebuild`。整份 Source 都已处理完成后，才用 `initialize.py --mark-extracted <source-path>` 标记；缺少必要上下文的材料保留 pending，或在 Source 记录为何没有合适题目。

从头生成题目同样走步骤 4 至 8。一次批量任务可调用 `save_question` API，但每道题都需要单独的语义依据，全部草稿检查成功后再写入。工具是防止遗漏的入口，不是自动命题质量判定器；能够手工编辑仓库的维护者仍须遵循本协议。

## 修订、兼容与训练

Question schema 3 新增可选 `coach_notes` 与 `quality_review`。旧题继续可读，不能凭已有文件自动补造审查证据；下次实质修订时补齐。已记录审查的题发生 Prompt、Rubric、Hints、Follow-ups、coach_notes 或训练分类变化后，`validate.py` 会拒绝旧哈希，必须重新审阅。SourceRefs 和导出所需的 evaluation_basis 投影不纳入哈希；公开前仍要检查来源与内容边界。

出题只展示 Prompt；追问只展示当前一项，coach_notes 在必要时供教练了解澄清口径，不直接念出。读到实际答案或诊断线索仍按辅助状态规则记录。Rubric 中的追问项目仅在对应问题实际提出后评价。角色扮演中的教练补充设定不是候选人的个人事实。

修改题目保留 ID 和既有 AttemptEvent、周期及会话快照。归档题继续 archived，除非用户另有要求。主问与追问属于完全不同能力且无法保持单题评分语义时，再考虑独立新题；不为凑数量自动拆题。Public Export 继续由明确任务触发。
