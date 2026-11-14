// Phone-width regression for the generated platform SDK reference: every page in the
// sidebar group must fit a 390 px viewport with no horizontal page scroll, and every
// reference table must sit in a bounded scroller (.sdk-ref-table) so wide identifiers
// scroll inside the table instead of widening the document. Runs against the preview
// on 127.0.0.1:4321 (npm run build && npm run preview), like integrations.browser.cjs.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

const BASE = 'http://127.0.0.1:4321';
const WIDTH = 390;

async function routes() {
  const { sdkReferenceNavigation } = await import(path.join(__dirname, '..', 'src', 'lib', 'sdk-reference.mjs'));
  const out = [];
  const walk = (items) => {
    for (const item of items) {
      if (item.href) out.push(item.href);
      if (item.items) walk(item.items);
    }
  };
  walk(sdkReferenceNavigation.items);
  return out;
}

(async () => {
  let ready = false;
  for (let i = 0; i < 30 && !ready; i++) {
    try { if ((await fetch(BASE + '/docs/sdk/reference')).ok) ready = true; else await new Promise((r) => setTimeout(r, 1000)); } catch { await new Promise((r) => setTimeout(r, 1000)); }
  }
  assert.ok(ready, 'Start the docs preview on 127.0.0.1:4321 before running browser checks');
  const hrefs = await routes();
  assert.ok(hrefs.length >= 30, `expected the full reference in the sidebar, found ${hrefs.length} routes`);
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: WIDTH, height: 844 }, colorScheme: 'dark' });
  const page = await ctx.newPage();
  const failures = [];
  for (const href of hrefs) {
    await page.goto(BASE + href + '/', { waitUntil: 'networkidle' });
    const m = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      tables: document.querySelectorAll('.docs-content table').length,
      unwrapped: [...document.querySelectorAll('.docs-content table')].filter((t) => !t.closest('.sdk-ref-table')).length,
      offscreen: [...document.querySelectorAll('.docs-content h2, .docs-content h3, .docs-content td, .docs-content pre')]
        .filter((el) => el.getBoundingClientRect().left < 0).length,
    }));
    if (m.scrollWidth > m.clientWidth) failures.push(`${href}: document scrolls to ${m.scrollWidth}px at a ${m.clientWidth}px viewport`);
    if (m.unwrapped) failures.push(`${href}: ${m.unwrapped} table(s) not inside .sdk-ref-table`);
    if (m.offscreen) failures.push(`${href}: ${m.offscreen} element(s) start left of the viewport (clipped content)`);
    console.log(`${href}: ${m.scrollWidth}px wide, ${m.tables} table(s)`);
  }
  await browser.close();
  assert.deepEqual(failures, [], failures.join('\n'));
  console.log(`sdk reference mobile: ${hrefs.length} pages fit ${WIDTH}px with bounded tables`);
})().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
