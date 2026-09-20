// Synthetic data only. Exercise the real CLI in an isolated pack with Unicode/spaces.
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { loadPdfDependencies } = require('./browser.cjs');

async function main() {
  const tool = path.resolve(__dirname, '..');
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'coach PDF 测试 '));
  try {
    const markdown = path.join(temp, 'workspace/resume/Markdown');
    await fs.mkdir(path.join(markdown, 'shared'), { recursive: true });
    await fs.mkdir(path.join(markdown, 'tailored'), { recursive: true });
    await fs.cp(path.join(tool, 'scripts'), path.join(temp, 'resume/scripts'), { recursive: true });
    await fs.cp(path.join(tool, 'styles'), path.join(temp, 'resume/styles'), { recursive: true });
    for (const language of ['en', 'zh']) {
      await fs.writeFile(path.join(markdown, `shared/header-${language}.md`), '# Example Candidate / 示例候选人\n');
      await fs.writeFile(path.join(markdown, `tailored/example-${language}.md`),
        `<!-- resume-header: ${language} -->\n## Experience / 工作经历\n\nSynthetic cross-platform test. 数据平台开发。\n`);
    }
    const result = spawnSync(process.execPath, [path.join(temp, 'resume/scripts/export-pdf.cjs')], {
      cwd: os.tmpdir(), encoding: 'utf8', timeout: 120000,
      env: { ...process.env, NODE_PATH: path.join(tool, 'node_modules') },
    });
    if (result.error || result.status !== 0) throw result.error || new Error(result.stdout + result.stderr);
    const { PDFDocument } = loadPdfDependencies();
    for (const language of ['en', 'zh']) {
      const pdf = await PDFDocument.load(await fs.readFile(path.join(temp, `workspace/resume/PDF/example-${language}.pdf`)));
      if (pdf.getPageCount() !== 1) throw new Error('Expected one page per synthetic resume.');
    }
    console.log(result.stdout);
    console.log('Synthetic PDF smoke passed. This does not replace visual font review.');
  } finally {
    await fs.rm(temp, { recursive: true, force: true });
  }
}
main().catch((error) => { console.error(error.message); process.exitCode = 1; });
