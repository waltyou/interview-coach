const { test } = require('node:test');
const assert = require('node:assert/strict');
const { findBrowserExecutable } = require('./browser.cjs');

for (const [platform, target] of [
  ['win32', 'C:\\Users\\Example\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe'],
  ['darwin', '/Users/example/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'],
  ['linux', '/snap/bin/chromium'],
]) {
  test(`${platform}: platform-specific install`, () => {
    assert.equal(findBrowserExecutable({ platform, home: '/Users/example',
      env: { LOCALAPPDATA: 'C:\\Users\\Example\\AppData\\Local' },
      exists: (file) => file === target }), target);
  });
}
test('explicit path takes precedence', () => {
  assert.equal(findBrowserExecutable({ env: { CHROME_PATH: '/custom/browser' },
    exists: () => true }), '/custom/browser');
});
test('invalid override fails instead of silently falling back', () => {
  assert.throws(() => findBrowserExecutable({ env: { CHROME_PATH: '/missing' },
    exists: () => false }), /CHROME_PATH/);
});
test('Linux PATH supports spaces', () => {
  assert.equal(findBrowserExecutable({ platform: 'linux', env: { PATH: '/custom apps/bin' },
    exists: (file) => file === '/custom apps/bin/chromium' }), '/custom apps/bin/chromium');
});
test('no local browser allows Puppeteer-managed browser', () => {
  assert.equal(findBrowserExecutable({ env: {}, exists: () => false }), undefined);
});
