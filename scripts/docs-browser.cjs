// Docs UI checks exercise the built site, not analytics, font CDNs or GitHub's
// star API. Keep first-party requests real, including navigation and Pagefind.
/**
 * @param {import('playwright').Browser} browser
 * @param {string} base
 * @param {import('playwright').BrowserContextOptions} [options]
 * @returns {Promise<import('playwright').BrowserContext>}
 */
async function createDocsContext(browser, base, options = {}) {
  const context = await browser.newContext(options);
  const origin = new URL(base).origin;
  await context.route('**/*', route =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  return context;
}

module.exports = { createDocsContext };
