# AGENTS.md - Resume Capability

该目录提供 Interview Coach 的简历维护与 PDF 导出能力。个人简历数据保存在 `../workspace/resume/`，目标职位及其 Job Brief 保存在 `../workspace/jobs/`。通用工具与私人职业事实必须保持分离。

## 每次开始前

1. 读取 `../manifest.json`、`../protocol/TERMS.md` 和 `../protocol/COACHING.md`，确认 Resume 与 Job 的位置。
2. 读取 `RESUME_RULES.md`。
3. 定制简历时，先读取对应的 Job、Job Brief 或用户刚提供的职位描述。
4. 修改任何简历正文前，先给出拟修改内容或差异摘要，得到用户明确确认后再写入。

## 目录边界

- `../workspace/resume/Markdown/master/`：完整简历，所有职业事实的权威来源。
- `../workspace/resume/Markdown/tailored/`：面向具体职位的定制简历。
- `../workspace/resume/Markdown/shared/`：中英文共享页眉。
- `../workspace/resume/PDF/`：导出的审阅或投递版本。
- `../workspace/jobs/`：Interview Coach 的统一职位上下文。
- `assets/`、`styles/`、`scripts/`：通用导出资产与工具。

## 事实与定制规则

- 姓名、联系方式、任职时间、项目、职责、技术、业绩和教育经历只能来自完整简历及共享页眉中已经确认的事实。
- 完整简历有多份且权威文件不明确时，先请用户选择；不要根据文件名猜测。
- 缺少或含义不清的事实需要用户确认。确认后先更新完整简历，再用于定制版本。
- 可以调整顺序、篇幅、关键词和表达重心，不能虚构、夸大或把团队成果改写为个人成果。
- 新的岗位简历应在对应 Job Brief 中记录链接，让简历定制与 PreparationCycle 共享同一个 Job 上下文。

## PDF 导出

从 Interview Coach 仓库根目录运行：

```powershell
npm --prefix resume install
npm --prefix resume run pdf
```

只导出指定简历：

```powershell
npm --prefix resume run pdf -- Markdown/tailored/example-role.md
```

导出器读取 `../workspace/resume/Markdown/`，写入 `../workspace/resume/PDF/`。每次导出后检查页数、分页、字体、链接、图标和内容截断。定制简历超过两页时保留生成结果，先汇报页数与内容取舍，得到确认后再精简正文。
