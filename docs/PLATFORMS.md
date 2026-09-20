# 运行环境

目标平台为 Windows、macOS、Linux。核心功能要求 Python 3.10+，无需 npm 依赖；简历 PDF 导出单独要求 Node.js 22+、npm 和可启动的 Chrome、Edge 或 Puppeteer 管理的浏览器。三平台 CI 配置已提供；支持声明应以实际通过的 CI 结果为准，不把模拟平台分支测试当作实机验证。Linux CI 覆盖 Ubuntu，不代表所有发行版或 CPU 架构。

## Agent 首次检查

先定位包含 `manifest.json` 的 Interview Coach 根目录。以下命令均从该目录运行。

1. 判断当前系统和 shell，尝试 `python --version`、`python3 --version`，Windows 还可尝试 `py -3 --version`。选择能运行且版本至少为 3.10 的解释器，后续保持一致。
2. 执行 `python -X utf8 scripts/doctor.py`。文档中的 `python` 可替换为 `python3`、`py -3` 或已配置的解释器。带空格的路径按当前 shell 引用，PowerShell 调用带引号的可执行文件时使用 `&`。
3. 只汇报影响当前任务的问题。检查不写入画像或引导状态，不上传环境信息。没有 Python 时可先介绍产品和讨论目标；结构化写入等待环境就绪，不伪造执行结果。不擅自安装软件或提升权限。
4. 通过后继续 Onboarding。不每轮重复检查；环境变化或脚本失败时再检查。

Windows 的 Python 命令使用 `-X utf8`，避免中文输出被终端默认编码阻断；其他平台也可使用。文件采用 UTF-8，持久化引用采用相对路径和 `/`，保持文件名大小写一致，避免仅大小写不同的重复文件名。

## 按需依赖

读取 PDF 文本前：`python -X utf8 scripts/doctor.py --capability pdf-source`。
缺少依赖时，说明后在所选 Python 的虚拟环境中安装 `pypdf`。也支持 PATH 中的 `pdftotext`。文本提取不等于 OCR 或视觉审阅。

导出简历 PDF 前：

```text
npm --prefix resume ci
python -X utf8 scripts/doctor.py --capability pdf-export
```

安装需要联网，浏览器下载可能耗时。PowerShell 如果限制 `npm.ps1`，可使用 `npm.cmd`，无需修改全局执行策略。检查实际启动并关闭无头浏览器，不读取简历或生成 PDF。

浏览器依次查找 `PUPPETEER_EXECUTABLE_PATH`、`CHROME_PATH`、PATH、平台常见目录，最后使用 Puppeteer 管理的浏览器。显式配置路径无效时直接报错。环境变量值应是可执行文件路径，不包含额外引号或启动参数。

Linux 可能需要浏览器系统依赖与可用的 sandbox，容器和 ARM 环境需单独验证。参考 [Puppeteer 官方排障文档](https://pptr.dev/troubleshooting)，不要默认添加 `--no-sandbox` 或要求以 root 运行。

## 字体和分页

系统字体回退可能影响换行和页数。需要中英文跨系统排版一致时，在各系统安装同一版本的 Noto Sans CJK SC，并将其设为 `resume/styles/resume.css` 的首选字体；等宽字体也应统一。默认保留现有排版，不自动改变用户简历外观。不承诺不同浏览器、字体版本输出逐字节一致。

导出后检查中文缺字、分页、链接和截断。自动 PDF 冒烟测试只验证生成成功与页数，不替代视觉检查。

## 开发验证

```text
python -X utf8 -m unittest discover -s scripts/tests -v
npm --prefix resume test
npm --prefix resume run test:pdf
```

测试使用临时合成数据，不对用户简历执行批量导出。独立仓库的 `.github/workflows/platforms.yml` 覆盖三个系统的 Python 3.10/3.13 和 Node.js 22/24。CI 不上传私人工作区或简历产物。
