// Trusted offline acceptance for the repository's plain HTML/CSS/JS starter.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, realpath, stat, writeFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import { execFileSync } from 'node:child_process';
import { chromium } from '/Users/admin/mortimer/browser/node_modules/playwright/index.mjs';

assert.equal(execFileSync('/usr/sbin/sysctl', ['-n', 'kern.hv_vmm_present'], { encoding: 'utf8' }).trim(), '1');
const root = '/Users/admin/mortimer/source';
const manifest = JSON.parse(await readFile(`${root}/manifest.json`, 'utf8'));
assert.equal(typeof manifest.entry_point, 'string', 'The app needs an HTML entry point');
assert.ok(!manifest.entry_point.startsWith('/') && !manifest.entry_point.split('/').includes('..'));
assert.ok(manifest.entry_point.endsWith('.html'));
assert.ok(Array.isArray(manifest.dependencies) && manifest.dependencies.length === 0,
  'This starter profile supports dependency-free web apps; prepare a matching profile for additional runtimes.');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml', '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2' };
const server = createServer(async (req, res) => {
  try {
    const path = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    assert.ok(!path.split('/').some(part => part.startsWith('.')));
    const file = await realpath(resolve(root, '.' + path));
    assert.ok(file.startsWith(root + '/'));
    const type = types[extname(file)];
    assert.ok(type && (await stat(file)).size <= 32 * 1024 * 1024);
    res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' });
    res.end(await readFile(file));
  } catch { res.writeHead(404); res.end('Not found'); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
const errors = [], failed = [];
let failure;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', error => errors.push(error.message));
  page.on('requestfailed', request => failed.push(request.url()));
  page.on('response', response => { if (response.status() >= 400) failed.push(`${response.url()}: HTTP ${response.status()}`); });
  await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const response = await page.goto(origin + '/' + manifest.entry_point, { waitUntil: 'networkidle', timeout: 15000 });
  assert.equal(response.status(), 200);
  assert.ok((await page.locator('body').innerText()).trim().length > 0, 'The app rendered no visible text');
  assert.deepEqual(errors, [], 'Uncaught browser error');
  assert.deepEqual(failed, [], 'Failed or external request in the offline app');
  await page.screenshot({ path: '/Users/admin/mortimer/reports/app-preview.png', fullPage: false });
} catch (error) { failure = error; }
finally {
  await writeFile('/Users/admin/mortimer/reports/app-browser.json', JSON.stringify({
    passed: !failure, errors, failed, failure: failure?.message,
    coverage: 'Offline startup and initial render; application-specific interaction checks are additional.'
  }, null, 2) + '\n');
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
if (failure) throw failure;
console.log('Offline web app rendered without browser errors.');
