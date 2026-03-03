import path from 'node:path';

/**
 * Map of component names to their import paths.
 * When a component like <Card> is used in MDX, the plugin auto-injects the import.
 */
const COMPONENT_MAP = {
  Accordion: '@docs/Accordion.astro',
  AccordionGroup: '@docs/AccordionGroup.astro',
  ApiEndpoint: '@docs/ApiEndpoint.astro',
  ApiPlayground: '@docs/ApiPlayground.astro',
  Callout: '@docs/Callout.astro',
  Card: '@docs/Card.astro',
  CardGrid: '@docs/CardGrid.astro',
  CardGroup: '@docs/CardGroup.astro',
  Check: '@docs/Check.astro',
  CodeBlock: '@docs/CodeBlock.astro',
  CodeGroup: '@docs/CodeGroup.astro',
  CodePanel: '@docs/CodePanel.astro',
  CopyButton: '@docs/CopyButton.astro',
  Expandable: '@docs/Expandable.astro',
  Icon: '@docs/Icon.astro',
  Note: '@docs/Note.astro',
  ParamField: '@docs/ParamField.astro',
  Prerequisites: '@docs/Prerequisites.astro',
  ResponseField: '@docs/ResponseField.astro',
  Step: '@docs/Step.astro',
  Steps: '@docs/Steps.astro',
  Tab: '@docs/Tab.astro',
  TabPanel: '@docs/TabPanel.astro',
  Tabs: '@docs/Tabs.astro',
  Tip: '@docs/Tip.astro',
  TLDR: '@docs/TLDR.astro',
  Tooltip: '@docs/Tooltip.astro',
  Update: '@docs/Update.astro',
  Warning: '@docs/Warning.astro',
};

/**
 * Vite plugin that auto-injects layout and component imports into MDX files
 * under src/pages/docs/. Runs before Astro processes the files.
 *
 * Authors only need to write:
 *   ---
 *   title: "Page Title"
 *   description: "..."
 *   ---
 *   Content with <Card>, <Note>, etc.
 *
 * The plugin handles the rest.
 */
export function viteDocsTransform() {
  return {
    name: 'vite-docs-transform',
    enforce: 'pre',

    transform(code, id) {
      // Only process MDX files under src/pages/docs/
      if (!id.endsWith('.mdx')) return null;
      if (!id.includes('/src/pages/docs/')) return null;

      let modified = code;

      // --- 1. Auto-inject layout if missing ---
      modified = injectLayout(modified, id);

      // --- 2. Auto-inject component imports ---
      modified = injectComponentImports(modified, id);

      if (modified === code) return null;
      return { code: modified, map: null };
    },
  };
}

/**
 * If the frontmatter doesn't have a `layout:` field, inject one
 * with the correct relative path to DocsLayout.astro.
 */
function injectLayout(code, filePath) {
  const frontmatterMatch = code.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!frontmatterMatch) return code;

  const frontmatter = frontmatterMatch[1];
  if (/^layout\s*:/m.test(frontmatter)) return code;

  // Calculate relative path from MDX file to src/layouts/
  const fileDir = path.dirname(filePath);
  const srcRoot = filePath.split('/src/pages/docs/')[0] + '/src';
  const layoutsDir = path.join(srcRoot, 'layouts');
  const relativePath = path.relative(fileDir, layoutsDir).replace(/\\/g, '/');
  const layoutLine = `layout: ${relativePath}/DocsLayout.astro`;

  // Insert layout as first line of frontmatter
  return code.replace(/^---\r?\n/, `---\n${layoutLine}\n`);
}

/**
 * Scan the MDX content (after frontmatter) for <ComponentName usage.
 * For each detected component that isn't already imported, inject an import.
 */
function injectComponentImports(code, filePath) {
  const frontmatterMatch = code.match(/^---\r?\n[\s\S]*?\r?\n---/);
  if (!frontmatterMatch) return code;

  const afterFrontmatter = code.slice(frontmatterMatch[0].length);

  // Find which components are used in the content
  const usedComponents = [];
  for (const name of Object.keys(COMPONENT_MAP)) {
    // Match <ComponentName (with word boundary to avoid partial matches)
    const pattern = new RegExp(`<${name}[\\s/>]`);
    if (pattern.test(afterFrontmatter)) {
      usedComponents.push(name);
    }
  }

  if (usedComponents.length === 0) return code;

  // Check which are already imported
  const existingImports = afterFrontmatter.match(/^import\s+(\w+)\s+from\s/gm) || [];
  const alreadyImported = new Set(
    existingImports.map((line) => {
      const match = line.match(/^import\s+(\w+)/);
      return match ? match[1] : null;
    }).filter(Boolean)
  );

  // Build missing import lines
  const newImports = usedComponents
    .filter((name) => !alreadyImported.has(name))
    .map((name) => `import ${name} from '${COMPONENT_MAP[name]}'`);

  if (newImports.length === 0) return code;

  // Insert imports right after the frontmatter closing ---
  const insertionPoint = frontmatterMatch[0].length;
  const existingAfter = code.slice(insertionPoint);

  // Add imports after frontmatter, ensuring a blank line before content
  const importBlock = '\n' + newImports.join('\n') + '\n';

  return code.slice(0, insertionPoint) + importBlock + existingAfter;
}
