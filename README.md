# Interview Coach

Interview Coach 是一个由 Git 仓库保存长期上下文、由你自己的 Agent 执行的面试教练。内置内容以 **Senior Big Data Engineer** 为默认基本盘，你也可以导入简历、目标职位、学习资料和面试复盘，把它扩展成只属于你的私人 Coach。

它不是一个需要安装的 npm 或 Python 包。克隆仓库后，让 Agent 读取 `AGENTS.md` 即可开始。首次使用的引导进度会保存在仓库中，换 Agent 或下一次继续时不需要重新回答。

## 快速开始

### 1. 克隆公开仓库

```powershell
git clone <public-repository-url> interview-coach
cd interview-coach
```

### 2. 先试一道，或按你的情况准备

在仓库根目录打开 Codex、Claude Code 或其他支持项目指令的 Agent，然后说：

```text
先试一道。
```

Agent 直接给出一道公共题，回答和评价不写入项目。当前聊天平台仍可能保留对话。想保存进度时，说按我的情况准备；Agent 再确认保存方式和最小背景。只用公共题库和不保存回答是两个独立选择。

也可以说先做 8 题短测，或今天练 15 分钟。已保存的练习中，说继续即可接回原题、提示和待答阶段。

### 3. 保存私人版本

准备导入简历、回答和面试经历时，建议创建一个空的 private repository。Onboarding 会引导你确认。手动设置方式是：

```powershell
git remote rename origin upstream
git remote add origin <your-private-repository-url>
git push -u origin main
```

这样，`upstream` 用于接收 Interview Coach 的公开更新，`origin` 用于保存你自己的私人数据。只在本地使用也是有效选择。

更完整的能力说明、常用说法和设计原则见 [Interview Coach Handbook](docs/HANDBOOK.md)。

## 可以用它做什么

- 按 Senior Big Data Engineer 基线逐题练习，并根据回答给出评价、追问和复习建议。
- 通过聊天、简历和其他资料理解你的背景，并用练习与真实反馈持续演进强弱项模型。
- 导入简历、职位描述、学习笔记和历史问答，生成只属于你的私人题目。
- 围绕目标职位建立 PreparationCycle，组合公共基本盘与岗位定向题目。
- 维护完整简历，根据职位生成定制版本，并导出可自定义样式的 PDF。
- 记录真实面试阶段与复盘，让后续训练使用真实反馈。
- 从不可变的回答历史重建掌握度、复习报告和 Dashboard。

## 数据放在哪里

```text
library/questions/       内置公共题库
workspace/sources/       你的学习资料与面试资料
workspace/profile/       已确认的候选人画像与教练观察
workspace/questions/     根据私人上下文形成的题目
workspace/jobs/          目标职位与 Job Brief
workspace/cycles/        准备周期
workspace/events/        原始回答与评价历史
workspace/sessions/      未完成题目、提示和练习阶段
workspace/state/         可重建的进度和掌握度
workspace/reports/       复习报告
workspace/resume/        私人简历与生成的 PDF
resume/                  通用简历规则、样式和导出工具
```

`workspace/events/` 是练习历史的事实来源。`workspace/state/`、报告和 Dashboard 都是可重建的投影。

公开题库只负责提供通用基本盘。你的简历、公司、职位、项目经历、回答和复盘都应留在 `workspace/`，默认作为 private 内容处理。

## 常用操作

查看或继续首次引导：

```powershell
python scripts/onboard.py status
```

查看候选人发现与教练模型状态：

```powershell
python scripts/discover.py status
python scripts/coach_model.py status
```

检查仓库数据：

```powershell
python scripts/validate.py
```

扫描 `source-list.txt` 中配置的资料：

```powershell
python scripts/initialize.py
```

重建学习状态和 Dashboard：

```powershell
python scripts/rebuild_state.py
python scripts/build_dashboard.py
```

查看历史：

```powershell
python scripts/history.py summary
```

通常不需要记住这些命令。只要 Agent 遵循 `AGENTS.md` 和 `protocol/COACHING.md`，它会在合适的阶段调用对应脚本。

## 简历工作流

处理简历前，Agent 会读取 `resume/AGENTS.md` 和 `resume/RESUME_RULES.md`。完整简历是职业事实的唯一权威来源，岗位定制版本从完整简历和 Job 上下文派生。

首次安装 PDF 导出依赖：

```powershell
npm --prefix resume install
```

导出简历：

```powershell
npm --prefix resume run pdf
```

样式可以在 `resume/styles/resume.css` 中自定义。Agent 在修改简历正文前应先给出拟修改内容或差异摘要，并等待你确认。

## 接收公开更新

当 Interview Coach 发布新功能或公共题目后：

```powershell
git fetch upstream
git merge upstream/main
git push origin main
```

你的私人文件保存在自己的分支历史中，不需要提交到公开仓库。遇到合并冲突时，让 Agent 先解释公开版本和私人版本各自的变化，再决定如何合并。

## 隐私建议

- 导入任何个人资料前，先确认当前 `origin` 指向你的 private repository。
- 不要把简历、联系方式、原始回答、面试复盘或未获授权的资料推送到公开仓库。
- 不确定一份内容能否公开时，把它留在 `workspace/`。
- 提交或分享前检查 `git status` 和实际 remote URL。

## 运行环境

面向 Windows、macOS、Linux。核心脚本需要 Python 3.10+；简历 PDF 导出按需使用 Node.js 22+ 与浏览器。Agent 会先检查当前任务需要的环境。命令中的 `python` 可替换为 `python3` 或 Windows 的 `py -3`，Windows 请加 `-X utf8`。平台验证状态、安装与字体说明见 [运行环境](docs/PLATFORMS.md)。

## License

[MIT](LICENSE)
