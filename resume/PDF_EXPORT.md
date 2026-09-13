# Markdown to PDF export

导出能力位于 `resume/`，个人简历源与 PDF 位于 `workspace/resume/`。以下命令均从 Interview Coach 仓库根目录运行。

## 首次安装

```powershell
npm --prefix resume install
```

导出脚本优先使用本机 Chrome 或 Edge。

## 导出全部简历

```powershell
npm --prefix resume run pdf
```

命令扫描 `workspace/resume/Markdown/master/` 和 `workspace/resume/Markdown/tailored/`，将同名 PDF 写入 `workspace/resume/PDF/`。`workspace/jobs/` 中的职位资料只用于定制分析，不参与导出。

## 导出指定简历

```powershell
npm --prefix resume run pdf -- Markdown/tailored/example-role.md
```

`--` 后的路径相对于 `workspace/resume/`。可以一次提供多个 Markdown 路径。

## 共享页眉

每份简历以以下标记之一开头：

```markdown
<!-- resume-header: en -->
<!-- resume-header: zh -->
```

导出时，标记会在内存中替换为 `workspace/resume/Markdown/shared/` 中的对应页眉。联系方式只需在共享页眉中维护。

## 渲染策略

- 导出器按原文渲染。除展开共享页眉外，不删除、改写或缩短正文。
- 所有简历使用同一份固定 A4 样式 `resume/styles/resume.css`。
- 导出器不会根据页数动态缩小字号、行距或页边距。
- 定制简历超过两页时保留 PDF 并打印页数。先确定内容取舍，再修改 Markdown 和重新导出。
- 本地图标缺失时终止导出，避免生成缺少资源的 PDF。
