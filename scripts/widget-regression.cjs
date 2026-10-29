const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const BASE = process.env.DOCS_BASE_URL || 'http://127.0.0.1:4321';

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    // These lifecycle checks must not talk to the chat backend or external CDNs.
    await page.route('**/*', route => new URL(route.request().url()).origin === new URL(BASE).origin ? route.continue() : route.abort());
    await page.goto(BASE + '/docs/integrations');
    await page.waitForFunction(() => typeof window.openAiChat === 'function');
    await page.evaluate(() => { window.loadChatDeps = () => Promise.resolve(); window.openAiChat(); });
    const visible = async () => {
      await page.waitForTimeout(300); // Outlive the old 200 ms hide callback.
      assert.equal(await page.locator('#ai-chat-popup').isVisible(), true);
      assert.equal(await page.locator('#ai-restore-chip').isVisible(), false);
      assert.equal(await page.evaluate(() => sessionStorage.getItem('ai-chat-open')), 'true');
    };
    // Synchronous clicks reproduce the <200 ms minimize/restore race exactly.
    await page.evaluate(() => {
      document.getElementById('ai-minimize-btn').click();
      document.getElementById('ai-restore-chip').click();
    });
    await visible();
    // Close/reopen has the same delayed-hide hazard.
    await page.evaluate(() => { window.closeAiChat(); window.openAiChat(); });
    await visible();
    // The focused native button must restore with both keyboard activators.
    for (const key of ['Enter', 'Space']) {
      await page.locator('#ai-widget-input').focus();
      await page.keyboard.press('Escape');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'ai-restore-chip');
      await page.keyboard.press(key);
      await visible();
    }
    // A pending open-focus callback must not steal focus from the restore chip.
    await page.evaluate(() => {
      window.closeAiChat(); window.openAiChat();
      document.getElementById('ai-minimize-btn').click();
    });
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'ai-restore-chip');
    assert.equal(await page.locator('#ai-chat-popup').isVisible(), false);
    await page.keyboard.press('Enter');
    await visible();
    console.log('PASS immediate Restore, close/reopen, focused Enter/Space, pending input focus');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
