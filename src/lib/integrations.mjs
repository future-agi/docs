// @ts-check
/**
 * Published integration discovery. Cards and the Integrations sidebar both use
 * this catalog. Add a guide only after its route exists on the deployment branch.
 * A method describes the connection path, not a support or testing badge.
 * Run `npm run test:integrations` when changing this file.
 *
 * @typedef {'providers'|'frameworks'|'coding'|'gateways'|'voice'|'java'|'apps'|'import'|'export'} IntegrationCategory
 * @typedef {{id: string, name: string, href: string, category: IntegrationCategory,
 * summary: string, method: string, logo: string, aliases?: string[], sharedGuide?: boolean}} Integration
 * @typedef {{id: IntegrationCategory, name: string, description: string}} Category
 */

/** @type {ReadonlyArray<Category>} */
export const integrationCategories = [
  { id: 'providers', name: 'Model providers', description: 'Trace model calls from your application.' },
  { id: 'frameworks', name: 'Frameworks & agents', description: 'Connect the steps, tools and model calls in your application.' },
  { id: 'coding', name: 'Coding agents', description: 'Connect coding-agent sessions, turns and tools.' },
  { id: 'gateways', name: 'Gateways', description: 'Trace proxied requests, using the connection method in each guide.' },
  { id: 'voice', name: 'Voice & realtime', description: 'Follow conversations across your voice stack.' },
  { id: 'java', name: 'Java', description: 'Set up JVM tracing with client wrappers or native OpenTelemetry.' },
  { id: 'apps', name: 'Apps & workflows', description: 'Connect chat applications and visual workflows.' },
  { id: 'import', name: 'Import traces', description: 'Bring existing traces into Future AGI.' },
  { id: 'export', name: 'Export & alerts', description: 'Send Future AGI data to the tools your team already uses.' },
];

/** @type {ReadonlyArray<Integration>} */
export const integrations = [
  { id: 'z-ai', name: 'Z.ai', href: '/docs/integrations/providers/z-ai', category: 'providers', summary: 'Trace Python chat completions on the general-platform endpoint.', method: 'OpenAI client', logo: 'generic-model' },
