// Regressions adapted from verify-scripts/{acceptance,matrix,race-proof}.cjs.
// Run against the actual built docs shell, never a standalone logo atlas.
const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const zlib = require('node:zlib');
const assert = require('node:assert/strict');
const BASE = process.env.DOCS_BASE_URL || 'http://127.0.0.1:4321';
const OUT = process.env.INTEGRATIONS_EVIDENCE_DIR || path.join(os.tmpdir(), 'docs-integrations-browser');
const results = [];
async function record(name, fn) {
  try { results.push({ name, status: 'PASS', detail: await fn() }); }
  catch (error) { results.push({ name, status: 'FAIL', error: String(error.stack) }); }
  await fs.writeFile(path.join(OUT, 'regression-results.json'), JSON.stringify(results, null, 2));
  console.log(name, results.at(-1).status);
}
// Chromium screenshots are RGB/RGBA PNGs. Decode only those lossless formats so
// contrast assertions sample the real embedded SVG rendering, including its MQ.
function pixels(png) {
  let width, height, channels;
  const chunks = [];
  for (let i = 8; i < png.length;) {
    const length = png.readUInt32BE(i), type = png.toString('ascii', i + 4, i + 8), data = png.subarray(i + 8, i + 8 + length);
    if (type === 'IHDR') { width = data.readUInt32BE(0); height = data.readUInt32BE(4); assert.equal(data[8], 8); channels = { 2: 3, 6: 4 }[data[9]]; assert.ok(channels); }
    if (type === 'IDAT') chunks.push(data);
    i += length + 12;
  }
  const raw = zlib.inflateSync(Buffer.concat(chunks)), stride = width * channels, decoded = Buffer.alloc(height * stride);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    for (let x = 0; x < stride; x++) {
      const a = x >= channels ? decoded[y * stride + x - channels] : 0;
      const b = y ? decoded[(y - 1) * stride + x] : 0;
      const c = y && x >= channels ? decoded[(y - 1) * stride + x - channels] : 0;
      const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
      const predictor = [0, a, b, Math.floor((a + b) / 2), pa <= pb && pa <= pc ? a : pb <= pc ? b : c][filter];
      assert.notEqual(predictor, undefined);
      decoded[y * stride + x] = (raw[y * (stride + 1) + 1 + x] + predictor) & 255;
    }
  }
  return Array.from({ length: width * height }, (_, i) => [...decoded.subarray(i * channels, i * channels + 3)]);
}
function luminance(rgb) { return rgb.map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0); }

(async () => {
  await fs.mkdir(OUT, { recursive: true });
  let ready = false;
  for (let attempt = 0; attempt < 40; attempt++) {
    try { if ((await fetch(BASE + '/docs/integrations')).ok) { ready = true; break; } } catch {}
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  assert.ok(ready, 'Start the built docs preview before running regressions');
  const { integrations, integrationCategories } = await import('../src/lib/integrations.mjs');
  const manifest = JSON.parse(await fs.readFile(path.join(__dirname, '../public/images/integrations/manifest.json')));
  const browser = await chromium.launch({ headless: true });
  for (const width of [1440, 768, 390, 375]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: 'dark', reducedMotion: 'reduce' });
    const page = await context.newPage();
    await record(`F1 logo navigation unobscured and scrollable ${width}`, async () => {
      await page.goto(BASE + '/docs/integrations', { waitUntil: 'networkidle' });
      await page.locator('[data-integration-card][href="/docs/integrations/traceai/anthropic"] img').click();
      await page.waitForURL('**/traceai/anthropic');
      await page.locator('h1').filter({ hasText: 'Anthropic' }).waitFor();
      await page.screenshot({ path: path.join(OUT, `logo-destination-${width}.png`) });
      assert.equal(await page.locator('#img-zoom-overlay.open').count(), 0);
      assert.notEqual(await page.locator('body').evaluate(e => getComputedStyle(e).overflow), 'hidden');
      await page.evaluate(() => window.scrollTo({ top: 250, behavior: 'instant' }));
      assert.ok(await page.evaluate(() => scrollY > 0), 'Destination must actually scroll');
      return { pathname: new URL(page.url()).pathname, scrollY: await page.evaluate(() => scrollY) };
    });
    await record(`F3 themed asset contrast in real directory ${width}`, async () => {
      await page.goto(BASE + '/docs/integrations?q=LiteLLM', { waitUntil: 'networkidle' });
      assert.equal(await page.locator('[data-integration-card]:visible').count(), 2);
      const rows = [];
      for (const card of await page.locator('[data-integration-card]:visible').all()) {
        const tile = card.locator('.integration-logo'), img = tile.locator('img');
        const background = await tile.evaluate(e => getComputedStyle(e).backgroundColor);
        const bg = background.match(/[\d.]+/g).slice(0, 3).map(Number), bgLum = luminance(bg);
        const shot = await img.screenshot();
        const colors = pixels(shot);
        const contrastPixels = colors.filter(rgb => (Math.max(luminance(rgb), bgLum) + 0.05) / (Math.min(luminance(rgb), bgLum) + 0.05) >= 3).length;
        rows.push({ name: await card.locator('h3').innerText(), background, contrastPixels, totalPixels: colors.length, imageScheme: await img.evaluate(e => getComputedStyle(e).colorScheme) });
      }
      await page.screenshot({ path: path.join(OUT, `litellm-real-page-${width}.png`), fullPage: true });
      assert.ok(rows.every(r => r.contrastPixels >= r.totalPixels * 0.1), JSON.stringify(rows));
      return rows;
    });
    await record(`F4 slow uncached navigation cannot inherit pending query ${width}`, async () => {
      // New context ensures no FastNav/prefetch cache. Hold the network response
      // for 1s exactly as the independent real-fill/real-click reproduction did.
      const c = await browser.newContext({ viewport: { width, height: 1000 } });
      try {
        const p = await c.newPage(), href = '/docs/integrations/traceai/anthropic';
        await p.route('**' + href, async r => { await new Promise(resolve => setTimeout(resolve, 1000)); await r.continue(); });
        await p.goto(BASE + '/docs/integrations', { waitUntil: 'domcontentloaded' });
        await p.locator('[data-integration-directory][data-ready]').waitFor();
        await p.evaluate(() => {
          window.__queryPushes = [];
          const push = history.pushState.bind(history);
          history.pushState = function (...args) { window.__queryPushes.push(String(args[2])); return push(...args); };
        });
        await p.locator('#integration-search').fill('Anthropic');
        await p.locator(`[data-integration-card][href="${href}"] h3`).click();
        await p.locator('h1').filter({ hasText: 'Anthropic' }).waitFor();
        await p.waitForTimeout(250);
        const detail = { url: p.url(), pushes: await p.evaluate(() => window.__queryPushes) };
        await p.screenshot({ path: path.join(OUT, `search-navigation-${width}.png`) });
        assert.equal(new URL(p.url()).search, '', JSON.stringify(detail));
        assert.ok(detail.pushes.every(url => new URL(url, BASE).pathname === '/docs/integrations' || !new URL(url, BASE).search), JSON.stringify(detail));
        assert.equal(detail.pushes.filter(url => new URL(url, BASE).pathname === href).length, 1, 'Only one destination history entry');
        return detail;
      } finally { await c.close(); }
    });
    for (const javaScriptEnabled of [true, false]) await record(`F5 legacy fragments ${width} JS=${javaScriptEnabled}`, async () => {
      const c = await browser.newContext({ viewport: { width, height: 1000 }, javaScriptEnabled });
      try {
        const p = await c.newPage(), rows = [];
        for (const [fragment, target] of Object.entries({ traceai: 'directory-setup', 'llm-models': 'providers', 'orchestration-frameworks': 'frameworks', other: 'apps', 'import-traces': 'import', 'export--alerts': 'export' })) {
          // Each published URL is an independent deep-link load. Do not use a
          // same-document DevTools navigation while the prior hash is scrolling.
          await p.goto('about:blank');
          await p.goto(BASE + '/docs/integrations#' + fragment, { waitUntil: 'networkidle' });
          // No JS lifecycle event signals completion of the existing native CSS
          // smooth scroll. Let that animation settle before inspecting its target.
          if (!javaScriptEnabled) await p.waitForTimeout(1800);
          const anchor = p.locator(`[id="${fragment}"]`);
          assert.equal(await anchor.count(), 1, fragment);
          assert.equal(await anchor.evaluate((e, id) => !!e.closest(id === 'directory-setup' ? '.directory-setup' : `[data-group="${id}"]`), target), true, `${fragment} maps to ${target}`);
          // Native no-JS hash navigation follows the existing smooth-scroll
          // CSS. Poll from the driver: injected rAF/timer pollers cannot run
          // normally when page scripts are disabled. Never scroll via JS here.
          let y;
          for (let attempt = 0; attempt < 50; attempt++) {
            y = await anchor.evaluate(e => e.getBoundingClientRect().top);
            if (y >= -5 && y < 1000) break;
            await p.waitForTimeout(100);
          }
          assert.ok(y >= -5 && y < 1000, `${fragment} target must be in view (end-of-page scroll may clamp), y=${y}`);
          rows.push({ fragment, target, y });
        }
        await p.screenshot({ path: path.join(OUT, `fragment-${width}-js-${javaScriptEnabled}.png`) });
        return rows;
      } finally { await c.close(); }
    });
    if (width < 1024) for (const cached of [false, true]) for (const href of ['/docs/integrations/traceai/bedrock', '/docs', '/docs/cookbook', '/docs/sdk', '/docs/api']) {
      await record(`F2 mobile dismissal ${width} ${cached ? 'cached' : 'uncached'} ${href}`, async () => {
        const c = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
        try {
          const p = await c.newPage(); let permit = false, actualRequests = 0;
          await p.route('**' + href, async route => {
            if (!permit) return route.abort(); // prevent implicit prefetch; prime explicitly below
            actualRequests++;
            if (!cached) await new Promise(resolve => setTimeout(resolve, 600));
            return route.continue();
          });
          const source = '/docs/integrations/traceai/anthropic';
          const selector = href.includes('/integrations/') ? `.integration-sidebar a[href="${href}"]` : `.integration-sidebar nav a[href="${href}"]`;
          await p.goto(BASE + source, { waitUntil: 'networkidle' });
          await p.waitForTimeout(1200); // let source caching and prefetch complete
          if (cached) {
            permit = true;
            await p.locator('#mobile-menu-button').click();
            await p.locator(selector).click();
            await p.waitForURL(BASE + href);
            await p.waitForFunction(() => !document.querySelector('.integration-sidebar') || document.querySelector('.integration-sidebar a[aria-current="page"]')?.getAttribute('href') === '/docs/integrations/traceai/bedrock');
            await p.goBack();
            await p.locator('.integration-sidebar a[aria-current="page"][href="' + source + '"]').waitFor({ state: 'attached' });
            await p.keyboard.press('Escape');
          }
          await p.locator('#mobile-menu-button').click();
          assert.equal(await p.locator('#mobile-menu-button').getAttribute('aria-expanded'), 'true');
          permit = true; actualRequests = 0;
          await p.locator(selector).click();
          await p.waitForURL(BASE + href);
          await p.waitForFunction(href => !document.querySelector('.integration-sidebar') || document.querySelector('.integration-sidebar a[aria-current="page"]')?.getAttribute('href') === href, href);
          await p.waitForTimeout(150);
          const detail = await p.evaluate(() => ({ path: location.pathname, expanded: document.querySelector('#mobile-menu-button').getAttribute('aria-expanded'), overlayVisible: !document.querySelector('#sidebar-overlay').classList.contains('hidden'), transform: document.querySelector('#sidebar').style.transform, heading: document.querySelector('h1')?.textContent }));
          detail.requests = actualRequests;
          await p.screenshot({ path: path.join(OUT, `sidebar-${width}-${cached ? 'cached' : 'uncached'}-${href.split('/').at(-1)}.png`) });
          assert.equal(detail.overlayVisible, false, JSON.stringify(detail));
          assert.notEqual(detail.expanded, 'true', JSON.stringify(detail));
          assert.notEqual(detail.transform, 'translateX(0px)', JSON.stringify(detail));
          assert.ok(detail.heading);
          assert.equal(actualRequests, cached ? 0 : 1, 'Prove cached vs uncached execution, not just delay');
          return detail;
        } finally { await c.close(); }
      });
    }
    await context.close();
  }
  await record('F3 scan every upstream asset for prefers-color-scheme and explicit tile pairing', async () => {
    const rows = [];
    for (const [key, asset] of Object.entries(manifest.assets)) {
      if (asset.kind !== 'brand') continue;
      const source = await fs.readFile(path.join(__dirname, '../public', asset.file), 'utf8');
      if (source.includes('prefers-color-scheme')) rows.push({ key, tile: asset.tile });
    }
    const c = await browser.newContext({ colorScheme: 'dark' });
    try {
      const p = await c.newPage(); await p.goto(BASE + '/docs/integrations', { waitUntil: 'networkidle' });
      for (const row of rows) {
        const entries = integrations.filter(i => i.logo === row.key);
        for (const entry of entries) assert.equal(await p.locator(`[data-integration-card][href="${entry.href}"] img`).evaluate(e => getComputedStyle(e).colorScheme), row.tile === 'dark' ? 'dark' : 'light', row.key);
      }
      return { scanned: Object.values(manifest.assets).filter(a => a.kind === 'brand').length, mediaQueryAssets: rows };
    } finally { await c.close(); }
  });
  await record('F6 built llms-full includes overview and all shared catalog entries', async () => {
    const response = await fetch(BASE + '/llms-full.txt'); assert.equal(response.status, 200);
    const text = await response.text();
    const overview = text.split('URL: https://docs.futureagi.com/docs/integrations\n')[1]?.split('\n---')[0];
    assert.ok(overview, 'Missing exact overview URL entry');
    for (const category of integrationCategories) assert.ok(overview.includes(category.name), category.name);
    for (const entry of integrations) {
      assert.ok(overview.includes(`[${entry.name}](${entry.href})`), entry.id);
      assert.ok(overview.includes(entry.summary), entry.id + ' summary');
      assert.ok(overview.includes(entry.method), entry.id + ' method');
    }
    return { overview: true, entries: integrations.length };
  });
  await browser.close();
  console.log(JSON.stringify({ tests: results.length, failed: results.filter(r => r.status === 'FAIL').length }));
  if (results.some(r => r.status === 'FAIL')) process.exitCode = 1;
})().catch(error => { console.error(error); process.exit(1); });
