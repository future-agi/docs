const assert = require('node:assert/strict');
const { createServer } = require('node:http');
const { chromium } = require('playwright');
const { createDocsContext } = require('./docs-browser.cjs');

(async () => {
  // Two loopback origins stand in for the docs and a stalled analytics server.
  // No external service is contacted, even for the original-failure proof.
  let analyticsRequests = 0;
  const analytics = createServer(() => { analyticsRequests++; });
  await new Promise(resolve => analytics.listen(0, '127.0.0.1', resolve));
  const analyticsUrl = `http://127.0.0.1:${analytics.address().port}/analytics.js`;
  const docs = createServer((request, response) => {
    if (request.url === '/ready.js') {
      response.writeHead(200, { 'content-type': 'text/javascript' });
      response.end('document.body.dataset.ready = "true";');
    } else {
      response.writeHead(200, { 'content-type': 'text/html' });
      response.end(`<body><h1>Docs fixture</h1><script src="/ready.js"></script><script async src="${analyticsUrl}"></script></body>`);
    }
  });
  await new Promise(resolve => docs.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${docs.address().port}`;
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const original = await browser.newContext();
    const page = await original.newPage();
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await page.locator('body[data-ready="true"]').waitFor();
    await assert.rejects(page.waitForLoadState('networkidle', { timeout: 1500 }), /Timeout/);
    assert.equal(analyticsRequests, 1, 'The stalled third party, not docs readiness, blocks networkidle');
    await original.close();

    const context = await createDocsContext(browser, base);
    const isolated = await context.newPage();
    assert.equal((await isolated.goto(base, { waitUntil: 'networkidle', timeout: 5000 })).status(), 200);
    assert.equal(await isolated.locator('body').getAttribute('data-ready'), 'true', 'First-party script still executes');
    assert.equal(analyticsRequests, 1, 'Isolated docs checks never contact the second origin');
    await context.close();
    console.log('PASS stalled third-party reproduction; isolation retains real first-party loading');
  } finally {
    await browser?.close();
    docs.closeAllConnections();
    analytics.closeAllConnections();
    await Promise.all([new Promise(resolve => docs.close(resolve)), new Promise(resolve => analytics.close(resolve))]);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
