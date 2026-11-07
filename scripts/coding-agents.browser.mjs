import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const server = spawn(process.execPath, ['node_modules/astro/astro.js', 'preview', '--host', '127.0.0.1', '--port', '4321'], { stdio: 'ignore' });
const base = 'http://127.0.0.1:4321';
let browser;
try {
  let ready = false;
  for (let i = 0; i < 120; i++) {
    try { if ((await fetch(base)).ok) { ready = true; break; } } catch {}
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  assert.ok(ready, 'Preview server did not start');
  await mkdir('browser-results', { recursive: true });
  browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const results = [];
  for (const slug of ['index', 'cursor', 'hermes-agent']) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const route = '/docs/integrations/coding-agents' + (slug === 'index' ? '' : '/' + slug);
    const response = await page.goto(base + route, { waitUntil: 'networkidle' });
    assert.equal(response.status(), 200);
    assert.equal(await page.locator('h1').count(), 1);
    assert.equal(await page.locator('h1').isVisible(), true);
    const text = await page.locator('main').innerText();
    assert.ok(text.includes('npx @traceai/agents setup'));
    assert.ok(text.includes('FI_AGENT_CAPTURE_CONTENT=false'));
    assert.ok(text.includes('--user-only'));
    const code = page.locator('pre').filter({ hasText: 'npx @traceai/agents' }).first();
    assert.ok(await code.count());
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    assert.equal(await page.locator('img[src]').evaluateAll(imgs => imgs.some(i => i.getAttribute('src') && i.complete && i.naturalWidth === 0)), false);
    if (slug !== 'index') {
      const headings = await page.locator('h2').allTextContents();
      for (const heading of ['What it traces', 'Quick start', 'Configuration', 'User and project scope', 'Manage tracing', 'Troubleshooting', 'Privacy']) {
        assert.ok(headings.some(h => h.includes(heading)), heading);
      }
      await page.getByRole('heading', { name: 'Quick start', exact: true }).scrollIntoViewIfNeeded();
    }
    await page.screenshot({ path: `browser-results/${slug}.png` });
    assert.deepEqual(errors, []);
    results.push({ route, status: response.status(), title: await page.title(), codeBlocks: await page.locator('pre').count(), pageErrors: errors });
    await page.close();
  }
  await writeFile('browser-results/result.json', JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results));
} finally {
  await browser?.close();
  server.kill('SIGTERM');
}
