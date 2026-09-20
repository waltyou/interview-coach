const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

function findBrowserExecutable({ platform = process.platform, env = process.env,
  home = os.homedir(), exists = (file) => {
    try { fs.accessSync(file, fs.constants.X_OK); return fs.statSync(file).isFile(); }
    catch { return false; }
  } } = {}) {
  const p = platform === 'win32' ? path.win32 : path.posix;
  for (const key of ['PUPPETEER_EXECUTABLE_PATH', 'CHROME_PATH']) {
    if (env[key]) {
      if (!exists(env[key])) throw new Error(`${key} must name an executable browser file.`);
      return env[key];
    }
  }
  const names = platform === 'win32' ? ['chrome.exe', 'msedge.exe'] :
    ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge'];
  const candidates = (env.PATH || '').split(p.delimiter).filter(Boolean)
    .flatMap((directory) => names.map((name) => p.join(directory, name)));
  if (platform === 'win32') {
    for (const root of [env.PROGRAMFILES || 'C:\\Program Files',
      env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', env.LOCALAPPDATA].filter(Boolean)) {
      candidates.push(p.join(root, 'Google/Chrome/Application/chrome.exe'),
        p.join(root, 'Microsoft/Edge/Application/msedge.exe'));
    }
  } else if (platform === 'darwin') {
    for (const root of ['/Applications', p.join(home, 'Applications')]) {
      candidates.push(p.join(root, 'Google Chrome.app/Contents/MacOS/Google Chrome'),
        p.join(root, 'Microsoft Edge.app/Contents/MacOS/Microsoft Edge'));
    }
  } else if (platform === 'linux') {
    for (const root of ['/usr/bin', '/usr/local/bin', '/snap/bin']) {
      candidates.push(...names.map((name) => p.join(root, name)));
    }
  }
  return candidates.find(exists);
}

function loadPdfDependencies() {
  if (Number(process.versions.node.split('.')[0]) < 22) throw new Error('Node.js 22+ required.');
  try {
    return { mdToPdf: require('md-to-pdf').mdToPdf, PDFDocument: require('pdf-lib').PDFDocument,
      puppeteer: require(require.resolve('puppeteer', { paths: [path.dirname(require.resolve('md-to-pdf'))] })) };
  } catch (error) {
    throw new Error(`PDF dependencies unavailable. Run npm ci in the resume directory. ${error.message}`);
  }
}

async function checkBrowser() {
  const { puppeteer } = loadPdfDependencies();
  const executablePath = findBrowserExecutable();
  let browser;
  try {
    browser = await puppeteer.launch(executablePath ? { executablePath } : {});
    console.log('PDF environment ready: ' + await browser.version());
    console.log('Fonts and pagination still require visual review. See docs/PLATFORMS.md.');
  } catch (error) {
    throw new Error(`Browser launch failed: ${error.message}. Check browser installation, OS dependencies and sandbox permissions; see docs/PLATFORMS.md.`);
  } finally {
    if (browser) await browser.close();
  }
}

module.exports = { findBrowserExecutable, loadPdfDependencies, checkBrowser };
