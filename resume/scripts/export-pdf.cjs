const fs = require('node:fs');
const fsPromises = require('node:fs/promises');
const path = require('node:path');

const { findBrowserExecutable, loadPdfDependencies, checkBrowser } = require('./browser.cjs');

const toolRoot = path.resolve(__dirname, '..');
const packRoot = path.resolve(toolRoot, '..');
const resumeWorkspaceRoot = path.join(packRoot, 'workspace', 'resume');
const markdownRoot = path.join(resumeWorkspaceRoot, 'Markdown');
const tailoredRoot = path.join(markdownRoot, 'tailored');
const sharedRoot = path.join(markdownRoot, 'shared');
const outputRoot = path.join(resumeWorkspaceRoot, 'PDF');
const stylesheetPath = path.join(toolRoot, 'styles', 'resume.css');
const sharedHeaders = {
  en: path.join(sharedRoot, 'header-en.md'),
  zh: path.join(sharedRoot, 'header-zh.md'),
};

function printHelp() {
  console.log(`Usage:
  npm run pdf
  npm run pdf -- --check
  npm run pdf -- Markdown/tailored/resume.md
  npm run pdf -- Markdown/tailored/first.md Markdown/tailored/second.md

Paths are relative to the Interview Coach workspace/resume directory.
With no file arguments, every Markdown file under Markdown/master and
Markdown/tailored is exported. Files under workspace/jobs are intentionally ignored.`);
}

function isWithin(parent, child) {
  const relativePath = path.relative(parent, child);
  return (
    relativePath === '' ||
    (!relativePath.startsWith(`..${path.sep}`) &&
      relativePath !== '..' &&
      !path.isAbsolute(relativePath))
  );
}

async function collectMarkdownFiles(directory) {
  const entries = await fsPromises.readdir(directory, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await collectMarkdownFiles(entryPath)));
    } else if (entry.isFile() && path.extname(entry.name).toLowerCase() === '.md') {
      files.push(entryPath);
    }
  }

  return files;
}

async function resolveInputs(argumentsFromCli) {
  if (argumentsFromCli.length === 0) {
    const roots = [path.join(markdownRoot, 'master'), tailoredRoot];
    const files = [];
    for (const root of roots) {
      if (fs.existsSync(root)) {
        files.push(...(await collectMarkdownFiles(root)));
      }
    }
    return files.sort((left, right) => left.localeCompare(right));
  }

  const files = argumentsFromCli.map((argument) => path.resolve(resumeWorkspaceRoot, argument));
  for (const file of files) {
    if (!isWithin(markdownRoot, file)) {
      throw new Error(`Only Markdown files under ${markdownRoot} can be exported: ${file}`);
    }
    if (path.extname(file).toLowerCase() !== '.md') {
      throw new Error(`Input is not a Markdown file: ${file}`);
    }
    const stats = await fsPromises.stat(file).catch(() => null);
    if (!stats?.isFile()) {
      throw new Error(`Markdown file does not exist: ${file}`);
    }
  }

  return [...new Set(files)].sort((left, right) => left.localeCompare(right));
}

function extractImageSources(markdown) {
  const sources = [];
  const markdownImagePattern = /!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+["'][^"']*["'])?\s*\)/g;
  const htmlImagePattern = /<img\b[^>]*\bsrc\s*=\s*(["'])(.*?)\1/gi;

  for (const match of markdown.matchAll(markdownImagePattern)) {
    sources.push(match[1] || match[2]);
  }
  for (const match of markdown.matchAll(htmlImagePattern)) {
    sources.push(match[2]);
  }

  return sources;
}

async function validateLocalImages(markdownPath, markdown) {
  const missingImages = [];

  for (const originalSource of extractImageSources(markdown)) {
    const sourceWithoutFragment = originalSource.split('#', 1)[0].split('?', 1)[0];
    let decodedSource;
    try {
      decodedSource = decodeURIComponent(sourceWithoutFragment);
    } catch {
      decodedSource = sourceWithoutFragment;
    }

    if (
      decodedSource === '' ||
      decodedSource.startsWith('data:') ||
      /^[a-z][a-z\d+.-]*:\/\//i.test(decodedSource)
    ) {
      continue;
    }

    const imagePath = decodedSource.startsWith('/')
      ? path.resolve(packRoot, decodedSource.slice(1))
      : path.resolve(path.dirname(markdownPath), decodedSource);

    if (!isWithin(packRoot, imagePath) || !fs.existsSync(imagePath)) {
      missingImages.push(originalSource);
    }
  }

  if (missingImages.length > 0) {
    throw new Error(
      `Missing or out-of-pack image(s) in ${path.relative(packRoot, markdownPath)}:\n` +
        missingImages.map((image) => `  - ${image}`).join('\n'),
    );
  }
}

async function expandSharedHeader(markdownPath, markdown) {
  const markerPattern = /^\uFEFF?\s*<!--\s*resume-header:\s*([a-z-]+)\s*-->\s*/i;
  const marker = markdown.match(markerPattern);

  if (!marker) {
    throw new Error(
      `Missing shared resume header marker in ${path.relative(packRoot, markdownPath)}. ` +
        'Add <!-- resume-header: en --> or <!-- resume-header: zh --> at the start of the file.',
    );
  }

  const headerKey = marker[1].toLowerCase();
  const headerPath = sharedHeaders[headerKey];
  if (!headerPath) {
    throw new Error(
      `Unsupported shared resume header "${headerKey}" in ` +
        `${path.relative(packRoot, markdownPath)}.`,
    );
  }

  const header = await fsPromises.readFile(headerPath, 'utf8');
  const body = markdown.slice(marker[0].length).trimStart();
  return `${header.trimEnd()}\n\n${body}`;
}

async function countPdfPages(pdfPath) {
  const { PDFDocument } = loadPdfDependencies();
  const pdfBytes = await fsPromises.readFile(pdfPath);
  const pdf = await PDFDocument.load(pdfBytes);
  return pdf.getPageCount();
}

async function exportResume(markdownPath, browserExecutable) {
  const { mdToPdf } = loadPdfDependencies();
  const markdown = await fsPromises.readFile(markdownPath, 'utf8');
  const expandedMarkdown = await expandSharedHeader(markdownPath, markdown);
  await validateLocalImages(markdownPath, expandedMarkdown);

  const resumeName = path.basename(markdownPath, '.md');
  const outputPath = path.join(outputRoot, `${resumeName}.pdf`);
  const launchOptions = browserExecutable ? { executablePath: browserExecutable } : {};

  await mdToPdf(
    { path: markdownPath, content: expandedMarkdown },
    {
      dest: outputPath,
      basedir: packRoot,
      stylesheet: [stylesheetPath],
      body_class: ['resume'],
      document_title: resumeName,
      page_media_type: 'print',
      marked_options: { gfm: true },
      launch_options: launchOptions,
      pdf_options: {
        format: 'A4',
        margin: '0',
        preferCSSPageSize: true,
        printBackground: true,
      },
    },
  );

  const pageCount = await countPdfPages(outputPath);
  return { markdownPath, outputPath, pageCount };
}

async function main() {
  const argumentsFromCli = process.argv.slice(2);
  if (argumentsFromCli.includes('--help') || argumentsFromCli.includes('-h')) {
    printHelp();
    return;
  }
  if (argumentsFromCli.includes('--check')) {
    await checkBrowser();
    return;
  }
  loadPdfDependencies();

  const markdownFiles = await resolveInputs(argumentsFromCli);
  if (markdownFiles.length === 0) {
    throw new Error('No Markdown resume files were found.');
  }

  const outputNames = new Map();
  for (const markdownPath of markdownFiles) {
    const outputName = `${path.basename(markdownPath, '.md')}.pdf`.toLowerCase();
    const previousSource = outputNames.get(outputName);
    if (previousSource) {
      throw new Error(
        `Output filename collision: ${path.relative(packRoot, previousSource)} and ` +
          `${path.relative(packRoot, markdownPath)} would both create ${outputName}`,
      );
    }
    outputNames.set(outputName, markdownPath);
  }

  await fsPromises.mkdir(outputRoot, { recursive: true });
  const browserExecutable = findBrowserExecutable();
  console.log(
    browserExecutable
      ? `Browser: ${browserExecutable}`
      : 'Browser: Puppeteer-managed Chromium',
  );

  const pageLimitWarnings = [];
  for (const [index, markdownPath] of markdownFiles.entries()) {
    console.log(
      `[${index + 1}/${markdownFiles.length}] Exporting ${path.relative(packRoot, markdownPath)}...`,
    );
    const result = await exportResume(markdownPath, browserExecutable);
    console.log(
      `  -> ${path.relative(packRoot, result.outputPath)} (${result.pageCount} page${
        result.pageCount === 1 ? '' : 's'
      })`,
    );

    if (isWithin(tailoredRoot, result.markdownPath) && result.pageCount > 2) {
      pageLimitWarnings.push(result);
    }
  }

  if (pageLimitWarnings.length > 0) {
    const details = pageLimitWarnings
      .map(
        ({ markdownPath, pageCount }) =>
          `  - ${path.relative(packRoot, markdownPath)}: ${pageCount} pages`,
      )
      .join('\n');
    console.warn(
      `\nWarning: the following tailored resumes exceed 2 pages:\n${details}\n` +
        'Please reduce the corresponding Markdown content, then export again. ' +
        'The generated PDFs have been kept for review.',
    );
  }

  console.log(
    `Done. Exported ${markdownFiles.length} PDF file(s) to workspace/resume/PDF/.`,
  );
}

main().catch((error) => {
  console.error(`\nExport failed: ${error.message}`);
  process.exitCode = 1;
});
