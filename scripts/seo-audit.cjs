const fs = require('fs');
const path = require('path');

const ROOT = 'C:/Users/Shibu/docs';
const DOCS_DIR = path.join(ROOT, 'src/pages/docs');

function getAllMdx(dir) {
  const results = [];
  for (const entry of fs.readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (fs.statSync(full).isDirectory()) results.push(...getAllMdx(full));
    else if (entry.endsWith('.mdx') || entry.endsWith('.md')) results.push(full);
  }
  return results;
}

function parseFrontmatter(content) {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!match) return {};
  const fm = {};
  const raw = match[1];
  // Match key: "value" or key: value (handles quoted and unquoted)
  const re = /^(\w+):\s*(?:"([^"]*?)"|'([^']*?)'|(.*?))\s*$/gm;
  let m;
  while ((m = re.exec(raw)) !== null) {
    fm[m[1]] = m[2] !== undefined ? m[2] : m[3] !== undefined ? m[3] : m[4];
  }
  return fm;
}

function getBody(content) {
  return content.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '');
}

function firstHeading(body) {
  const lines = body.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (/^#{1,6} /.test(trimmed)) return trimmed;
  }
  return null;
}

function hasNextSteps(body) {
  if (/##\s+Next Steps/i.test(body)) return true;
  // CardGroup with at least one Card that has href
  if (/<CardGroup[\s\S]*?<Card\s[^>]*href=/i.test(body)) return true;
  return false;
}

function isFeaturePage(relPath) {
  return /\/features\//.test(relPath);
}

const files = getAllMdx(DOCS_DIR);

const missingDesc = [];
const titleTooShort = [];
const titleTooLong = [];
const descTooShort = [];
const descTooLong = [];
const titleMap = {};
const noAboutHeading = [];
const featureMissingNextSteps = [];

for (const f of files) {
  const rel = path.relative(ROOT, f).split(path.sep).join('/');
  const content = fs.readFileSync(f, 'utf-8');
  const fm = parseFrontmatter(content);
  const body = getBody(content);
  const title = (fm.title || '').trim();
  const desc = (fm.description || '').trim();

  // 1. Missing description
  if (!desc) missingDesc.push(rel);

  // 2. Title length
  if (title && title.length < 15) titleTooShort.push({ rel, title, len: title.length });
  if (title && title.length > 60) titleTooLong.push({ rel, title, len: title.length });

  // 3. Description length
  if (desc) {
    if (desc.length < 120) descTooShort.push({ rel, len: desc.length, desc: desc.slice(0, 80) });
    if (desc.length > 155) descTooLong.push({ rel, len: desc.length, desc: desc.slice(0, 80) });
  }

  // 4. Duplicate titles
  if (title) {
    if (!titleMap[title]) titleMap[title] = [];
    titleMap[title].push(rel);
  }

  // 5. First heading == ## About
  const h = firstHeading(body);
  if (!h || !h.startsWith('## About')) {
    noAboutHeading.push({ rel, heading: h || '(no heading)' });
  }

  // 6. Feature pages missing Next Steps
  if (isFeaturePage(rel) && !hasNextSteps(body)) {
    featureMissingNextSteps.push(rel);
  }
}

const dupTitles = Object.entries(titleMap).filter(([, v]) => v.length > 1);

let out = '';
out += '# SEO Audit Report\n\n';
out += `Site: src/pages/docs/ | Files scanned: ${files.length}\n\n---\n\n`;

out += `## 1. Missing \`description\` — ${missingDesc.length} files\n\n`;
out += missingDesc.length === 0 ? '_None — all files have descriptions._\n'
  : missingDesc.map(f => `- ${f}`).join('\n') + '\n';

out += `\n## 2. Title too short (<15 chars) — ${titleTooShort.length} files\n\n`;
out += titleTooShort.length === 0 ? '_None._\n'
  : titleTooShort.map(x => `- "${x.title}" (${x.len} chars) → ${x.rel}`).join('\n') + '\n';

out += `\n## 3. Title too long (>60 chars) — ${titleTooLong.length} files\n\n`;
out += titleTooLong.length === 0 ? '_None._\n'
  : titleTooLong.map(x => `- "${x.title}" (${x.len} chars) → ${x.rel}`).join('\n') + '\n';

out += `\n## 4. Description too short (<120 chars) — ${descTooShort.length} files\n\n`;
out += descTooShort.length === 0 ? '_None._\n'
  : descTooShort.map(x => `- (${x.len} chars) "${x.desc}..." → ${x.rel}`).join('\n') + '\n';

out += `\n## 5. Description too long (>155 chars) — ${descTooLong.length} files\n\n`;
out += descTooLong.length === 0 ? '_None._\n'
  : descTooLong.map(x => `- (${x.len} chars) "${x.desc}..." → ${x.rel}`).join('\n') + '\n';

out += `\n## 6. Duplicate titles — ${dupTitles.length} groups\n\n`;
if (dupTitles.length === 0) out += '_None._\n';
else out += dupTitles.map(([t, fs]) =>
  `**"${t}"** (${fs.length} files)\n${fs.map(f => `  - ${f}`).join('\n')}`
).join('\n\n') + '\n';

out += `\n## 7. First body heading ≠ \`## About\` — ${noAboutHeading.length} files\n\n`;
if (noAboutHeading.length === 0) out += '_All files open with ## About._\n';
else {
  const shown = noAboutHeading.slice(0, 100);
  out += shown.map(x => `- \`${x.heading}\` → ${x.rel}`).join('\n');
  if (noAboutHeading.length > 100) out += `\n... and ${noAboutHeading.length - 100} more`;
  out += '\n';
}

out += `\n## 8. Feature pages missing Next Steps / CardGroup — ${featureMissingNextSteps.length} files\n\n`;
out += featureMissingNextSteps.length === 0 ? '_None._\n'
  : featureMissingNextSteps.map(f => `- ${f}`).join('\n') + '\n';

fs.writeFileSync(path.join(ROOT, 'seo-audit-report.md'), out);
console.log(out);
