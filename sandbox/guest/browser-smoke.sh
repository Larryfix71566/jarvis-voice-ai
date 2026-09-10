#!/usr/bin/env bash
# Read-only console navigation against the guest's own preview services.
set -euo pipefail
if [ "$(sysctl -n kern.hv_vmm_present 2>/dev/null)" != "1" ]; then
  echo 'Browser checks must run inside the development VM.' >&2
  exit 1
fi
source /Users/admin/mortimer/development.env
node --input-type=module <<'JS'
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { chromium } from '/Users/admin/mortimer/browser/node_modules/playwright/index.mjs';

const reports = '/Users/admin/mortimer/reports';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
const failedRequests = [];
const visited = [];
page.on('pageerror', error => errors.push(error.message));
page.on('requestfailed', request => failedRequests.push({ url: request.url(), error: request.failure()?.errorText }));
let failure;
try {
  const response = await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' });
  assert.equal(response.status(), 200);
  await page.getByRole('button', { name: 'Connect', exact: true }).waitFor();
  assert.equal(await page.locator('.brand').innerText(), 'MORTIMER');
  await page.getByRole('button', { name: /Panels/ }).click();
  for (const name of ['Repo', 'Edit', 'Memory', 'Runs', 'Agents', 'Output', 'Log']) {
    const tab = page.getByRole('tab', { name, exact: true });
    await tab.click();
    assert.equal(await tab.getAttribute('aria-selected'), 'true');
    await page.getByRole('tabpanel').waitFor();
    visited.push(name);
  }
  assert.deepEqual(errors, [], 'The console raised an uncaught browser error');
} catch (error) {
  failure = error;
} finally {
  await page.screenshot({ path: `${reports}/web-preview.png`, fullPage: true });
  await writeFile(`${reports}/browser-smoke.json`, JSON.stringify({
    passed: !failure, visited, errors, failedRequests,
    failure: failure?.message,
    coverage: 'Initial render and read-only panel navigation; no voice or publishing action invoked.',
  }, null, 2) + '\n');
  await browser.close();
}
if (failure) throw failure;
console.log(`Browser smoke passed: console and ${visited.length} panels`);
JS
