import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const base = 'http://127.0.0.1:4321';
const route = '/docs/integrations/traceai/auto';
const out = process.env.AUTO_EVIDENCE_DIR || process.env.INTEGRATIONS_EVIDENCE_DIR || '/tmp/docs-integrations-browser/auto';
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  assert.equal((await page.goto(base + route, { waitUntil: 'networkidle' })).status(), 200);
  await page.getByRole('heading', { name: 'Zero-code Node.js tracing', exact: true }).waitFor();
  assert.equal(await page.locator('.docs-content pre code').count(), 10);
  const code = page.locator('.docs-content pre').filter({ hasText: 'npm install @traceai/auto' });
  await code.locator('.copy-button').click();
  assert.equal((await page.evaluate(() => navigator.clipboard.readText())).trim(), 'npm install @traceai/auto');
  const active = page.locator('.integration-sidebar a[aria-current="page"]');
  assert.equal(await active.getAttribute('href'), route);
  const image = page.locator('img[src="/images/docs/integrations/traceai/auto/trace-span.png"]');
  await image.scrollIntoViewIfNeeded();
  await image.evaluate(img => img.decode());
  assert.equal(await image.evaluate(img => img.naturalWidth), 1440);
  await page.screenshot({ path: `${out}/auto-result.png` });
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  await page.screenshot({ path: `${out}/auto-setup.png` });
  await page.screenshot({ path: `${out}/auto-full.png`, fullPage: true });
  for (const href of await page.locator('.docs-content a[href^="#"]').evaluateAll(links => links.map(a => a.getAttribute('href')))) {
    assert.equal(await page.locator(href).count(), 1, `Missing local anchor ${href}`);
  }
  results.push('page, 10 code blocks, copy button, current sidebar item, trace image and anchors');
  for (const source of ['/docs/quickstart/setup-observability', '/docs/integrations/traceai']) {
    await page.goto(base + source, { waitUntil: 'networkidle' });
    await page.locator(`.docs-content a[href="${route}"]`).first().click();
    await page.waitForURL(base + route);
    await page.getByRole('heading', { name: 'Zero-code Node.js tracing', exact: true }).waitFor();
  }
  results.push('quickstart and overview links navigate to the guide');
  await page.goto(base + '/docs/integrations', { waitUntil: 'networkidle' });
  await page.locator('#integration-search').fill('@traceai/auto');
  const card = page.locator('[data-integration-card]:visible');
  await page.waitForFunction(() => document.querySelectorAll('[data-integration-card]:not([hidden])').length === 1);
  assert.equal(await card.count(), 1);
  assert.equal(await card.getAttribute('href'), route);
  await card.click();
  await page.waitForURL(base + route);
  results.push('package-name search discovers and opens the guide');
  const search = await page.evaluate(async route => {
    const pagefind = await import('/pagefind/pagefind.js');
    const response = await pagefind.search('Zero-code Node.js');
    const entries = await Promise.all(response.results.map(result => result.data()));
    return entries.some(entry => entry.url.replace(/\/$/, '') === route);
  }, route);
  assert.equal(search, true, 'Pagefind indexes the new page');
  results.push('Pagefind search returns the guide');
  assert.deepEqual(errors, []);
  await writeFile(`${out}/browser.json`, JSON.stringify({ results, errors }, null, 2));
  console.log(JSON.stringify({ results, errors }));
} finally {
  await browser.close();
}
