# Onboarding Protocol

Onboarding 的目标是在一次短对话内建立安全边界、理解候选人，并交付第一个实际结果。它是可恢复的生命周期，不是一次性欢迎文案。

## 何时启动

处理新用户的第一个请求前运行：

```powershell
python scripts/onboard.py status
```

- `new`：主动提供 onboarding，并运行 `python scripts/onboard.py start`。
- `in_progress`：从 `current_step` 继续，不重复已经完成的问题。
- `existing`：已有个人数据但没有 onboarding 状态。正常处理请求，仅提供一次可选补充初始化提示。
- `completed` 或 `skipped`：直接处理当前请求。

用户可以随时要求开始、继续、查看或跳过 onboarding。明确跳过时运行 `python scripts/onboard.py skip`。

## 交互原则

- 每次只问一个会改变下一步行动的问题。
- 先读取用户已经提供的资料，再询问其中没有的信息。
- 不要求用户填写固定问卷。聊天、简历、其他信息文件和历史记录都可以用于理解候选人。
- 将资料中看起来成立的事实总结给用户确认，确认后才写入 CandidateProfile。
- 当前有明确任务时，把 onboarding 融入该任务。
- 默认只展示当前一步，不向用户倾倒目录、Schema 或脚本参数。

## 生命周期

### 1. privacy

确认个人数据的保存方式。Git remote URL 不能证明仓库一定是 private。

- `private_remote`：用户确认个人版本连接到 private repository。
- `local_only`：只在本地保存。
- `no_personal_data`：暂时只使用公共题库。

在 privacy 完成前，不导入简历、联系方式、回答、复盘或公司内部资料。

```powershell
python scripts/onboard.py record privacy --privacy-choice private_remote
```

### 2. goal

确定本次最先获得价值的入口：

- `baseline`：从 Senior Big Data Engineer 公共基本盘开始摸底。
- `job_targeted`：围绕真实职位准备。
- `knowledge_import`：导入笔记、问答或学习资料。
- `resume`：维护完整简历或生成岗位定制简历。
- `interview_retro`：记录真实面试复盘。
- `explore`：先了解产品能力。

```powershell
python scripts/onboard.py record goal --entry-path baseline
```

### 3. profile

读取 `protocol/DISCOVERY.md`，完成一次最小 Candidate Discovery。明确告诉用户可以选择：

1. 现在和 Coach 聊几分钟；
2. 提供简历；
3. 提供题库、笔记、职位描述、反馈或其他信息文件；
4. 混合以上方式。

有资料时先读资料，概括已有信息，再只问重要缺口。CandidateProfile 只保存用户确认的事实、目标和偏好；Agent 的强弱项判断写入 CoachObservation，由 CoachModel 汇总。

```powershell
python scripts/discover.py start
python scripts/discover.py update --method conversation --target-role "Senior Data Engineer" --background-summary "..." --confirmed-by-user
python scripts/discover.py add-material --kind resume --path workspace/resume/resume.md
python scripts/discover.py complete --confirmed-by-user
python scripts/onboard.py record profile --candidate-profile workspace/profile/candidate.json
```

profile 是必要步骤，但不要求用户提供完整履历。一个已确认的背景摘要或资料，加上当前目标、动机或待解决问题，就足以完成初次发现。

### 4. materials

根据入口决定是否继续导入更多资料。资料统一保存在 `workspace/`，默认 private。这一步可以跳过，因为 profile 阶段可能已经注册了当前需要的材料。

```powershell
python scripts/onboard.py record materials
python scripts/onboard.py record materials --skip
```

### 5. first_value

完成一个真实结果：

- 建立 PreparationCycle 并准备第一道题；
- 索引第一份 Source；
- 初始化完整简历；
- 记录 InterviewExperience；
- 完成 Candidate Discovery，并给出下一步教练建议；
- 完成能力导览并确定下一步。

```powershell
python scripts/onboard.py record first_value --activation-kind candidate_discovery_completed --reference workspace/profile/candidate.json
python scripts/onboard.py complete
```

`workspace/onboarding.json` 只保存生命周期和 CandidateProfile 引用，不复制候选人事实。后续事实更新 CandidateProfile，教练判断追加 CoachObservation。

## 首次开场方式

```text
我看到这是一个新的 Interview Coach 工作区。我可以用几分钟帮你完成初始化，并在这次对话里给出第一个有用结果。开始前先确认：你准备把个人资料保存在 private repository、只在本地使用，还是暂时只用公共题库？
```

privacy 和 goal 完成后：

```text
接下来我需要先了解你，但不用填固定问卷。你可以直接和我聊，也可以给我简历、题库、笔记、职位描述或其他资料，我会先读取已有信息，再只问缺少的部分。你想从哪种方式开始？
```
