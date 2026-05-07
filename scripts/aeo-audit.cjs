const fs = require('fs');
const path = require('path');

const ROOT = 'C:/Users/Shibu/docs';
const DOCS_DIR = path.join(ROOT, 'src/pages/docs');

// ── Helpers ──────────────────────────────────────────────────────────────────

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
  if (!match) return { _raw: '' };
  const fm = { _raw: match[1] };
  const re = /^(\w+):\s*(?:"([^"]*?)"|'([^']*?)'|(.*?))\s*$/gm;
  let m;
  while ((m = re.exec(match[1])) !== null) {
    fm[m[1]] = m[2] !== undefined ? m[2] : m[3] !== undefined ? m[3] : (m[4] || '');
  }
  return fm;
}

function getBody(content) {
  return content.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, '');
}

// Extract headings with their level and line number
function extractHeadings(body) {
  const lines = body.split(/\r?\n/);
  const headings = [];
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(#{1,6})\s+(.+)/);
    if (m) headings.push({ level: m[1].length, text: m[2].trim(), line: i + 1 });
  }
  return headings;
}

// Get first non-empty paragraph after the first heading
function firstParaAfterFirstHeading(body) {
  const lines = body.split(/\r?\n/);
  let pastFirstHeading = false;
  let para = [];
  for (const line of lines) {
    if (!pastFirstHeading && /^#{1,6}\s/.test(line)) { pastFirstHeading = true; continue; }
    if (!pastFirstHeading) continue;
    if (line.trim() === '') {
      if (para.length > 0) break;
      continue;
    }
    para.push(line.trim());
  }
  return para.join(' ');
}

// ── Constants ─────────────────────────────────────────────────────────────────

const GENERIC_TITLES = new Set([
  'overview', 'quickstart', 'concepts', 'concepts', 'features', 'guides',
  'introduction', 'getting started', 'faqs', 'faq', 'index', 'home',
  'details', 'more', 'info', 'docs', 'documentation', 'setup', 'configuration',
  'reference', 'examples', 'tutorials', 'about', 'summary'
]);

const VAGUE_HEADINGS = new Set([
  'overview', 'details', 'info', 'more', 'introduction', 'background',
  'notes', 'summary', 'misc', 'other', 'additional', 'extra', 'further',
  'general', 'basics', 'advanced', 'setup', 'configuration', 'usage',
  'example', 'examples', 'reference', 'resources', 'related'
]);

const BAD_DESC_STARTS = [
  /^this page/i,
  /^learn how to/i,
  /^a guide to/i,
  /^an overview of/i,
  /^this document/i,
  /^this section/i,
  /^welcome to/i,
];

// ── Audit ─────────────────────────────────────────────────────────────────────

const files = getAllMdx(DOCS_DIR);
const rel = (f) => path.relative(ROOT, f).split(path.sep).join('/');

const issues = {
  // Critical
  missingDesc: [],
  dupTitle: {},          // title -> [files]
  noAboutHeading: [],
  // Warning
  titleTooShort: [],
  titleTooLong: [],
  titleGeneric: [],
  descTooShort: [],
  descTooLong: [],
  descBadStart: [],
  descNoKeywords: [],
  vagueHeading: [],      // [{rel, headings}]
  skippedHeadingLevel: [],
  h3WithoutH2: [],
  // Info / AEO
  noTldr: [],
  firstParaIsCodeOrList: [],
  hasQuestionHeadings: [],  // pages that DO have question headings (good)
  noQuestionHeadings: [],   // pages that don't (opportunity)
  hasAccordionOrFaq: [],
};

const pageScores = {}; // rel -> issue count
const titleMap = {};

for (const f of files) {
  const r = rel(f);
  const content = fs.readFileSync(f, 'utf-8');
  // Only read first 100 lines for most checks (speed), full file for heading hierarchy
  const lines = content.split(/\r?\n/);
  const head100 = lines.slice(0, 100).join('\n');

  const fm = parseFrontmatter(content);
  const body = getBody(content);
  const headings = extractHeadings(body);

  const title = (fm.title || '').trim();
  const desc = (fm.description || '').trim();
  let issueCount = 0;

  // ── 1. Missing description ──
  if (!desc) { issues.missingDesc.push(r); issueCount += 3; }

  // ── 2. Duplicate titles ──
  if (title) {
    if (!titleMap[title]) titleMap[title] = [];
    titleMap[title].push(r);
  }

  // ── 3. Title length ──
  if (title && title.length < 15) { issues.titleTooShort.push({ r, title, len: title.length }); issueCount++; }
  if (title && title.length > 60) { issues.titleTooLong.push({ r, title, len: title.length }); issueCount++; }

  // ── 4. Generic/keyword-poor title ──
  if (title && GENERIC_TITLES.has(title.toLowerCase())) {
    issues.titleGeneric.push({ r, title }); issueCount += 2;
  }

  // ── 5. Description length ──
  if (desc && desc.length < 120) { issues.descTooShort.push({ r, len: desc.length }); issueCount++; }
  if (desc && desc.length > 155) { issues.descTooLong.push({ r, len: desc.length }); issueCount++; }

  // ── 6. Description bad starts ──
  if (desc) {
    for (const pat of BAD_DESC_STARTS) {
      if (pat.test(desc)) { issues.descBadStart.push({ r, desc: desc.slice(0, 80) }); issueCount++; break; }
    }
  }

  // ── 7. Description repeats title verbatim ──
  if (desc && title && desc.toLowerCase().startsWith(title.toLowerCase())) {
    issues.descNoKeywords.push({ r, note: 'starts with title verbatim' }); issueCount++;
  }

  // ── 8. First heading == ## About ──
  const firstH = headings[0];
  if (!firstH || !(firstH.level === 2 && firstH.text.toLowerCase().startsWith('about'))) {
    issues.noAboutHeading.push({ r, firstH: firstH ? `${'#'.repeat(firstH.level)} ${firstH.text}` : '(none)' });
    issueCount += 2;
  }

  // ── 9. Vague single-word headings ──
  const vagueFound = headings.filter(h => VAGUE_HEADINGS.has(h.text.toLowerCase()));
  if (vagueFound.length > 0) {
    issues.vagueHeading.push({ r, headings: vagueFound.map(h => `${'#'.repeat(h.level)} ${h.text}`) });
    issueCount += vagueFound.length;
  }

  // ── 10. Heading hierarchy: skipped levels or H3 without H2 ──
  let hasH2 = false;
  let prevLevel = 0;
  let hierarchyIssues = [];
  for (const h of headings) {
    if (h.level === 2) hasH2 = true;
    if (h.level === 3 && !hasH2) hierarchyIssues.push(`H3 "${h.text}" with no preceding H2`);
    if (prevLevel > 0 && h.level > prevLevel + 1) hierarchyIssues.push(`H${prevLevel}→H${h.level} skip at "${h.text}"`);
    prevLevel = h.level;
  }
  if (hierarchyIssues.length > 0) {
    issues.skippedHeadingLevel.push({ r, problems: hierarchyIssues });
    issueCount += hierarchyIssues.length;
  }

  // ── 11. Question-style headings ──
  const questionH = headings.filter(h => h.text.endsWith('?') || /^(what|how|why|when|where|which|can|does|is|are|do)\b/i.test(h.text));
  if (questionH.length > 0) {
    issues.hasQuestionHeadings.push({ r, count: questionH.length });
  } else {
    issues.noQuestionHeadings.push(r);
  }

  // ── 12. TLDR block ──
  if (!/<TLDR|<tldr|:::tip\s*TLDR|## TL;DR|## TLDR/i.test(body)) {
    issues.noTldr.push(r); issueCount++;
  }

  // ── 13. First para after first heading is code/list ──
  const firstPara = firstParaAfterFirstHeading(body);
  if (firstPara.startsWith('```') || firstPara.startsWith('<CodeBlock') || firstPara.startsWith('- ') || firstPara.startsWith('1.') || firstPara.startsWith('*')) {
    issues.firstParaIsCodeOrList.push(r); issueCount++;
  }

  // ── 14. FAQ / Accordion blocks ──
  if (/<Accordion|<details|## FAQ|## Frequently Asked/i.test(body)) {
    issues.hasAccordionOrFaq.push(r);
  }

  pageScores[r] = issueCount;
}

// Finalize duplicate titles
for (const [t, fs_] of Object.entries(titleMap)) {
  if (fs_.length > 1) issues.dupTitle[t] = fs_;
}
const dupTitleFiles = Object.values(issues.dupTitle).flat();

// Top-20 most issues
const top20 = Object.entries(pageScores)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 20);

// ── Report ────────────────────────────────────────────────────────────────────

const total = files.length;
const pct = (n) => `${n} (${Math.round(n / total * 100)}%)`;

let out = `# AEO / GEO / SEO Audit Report\n\n`;
out += `**Site:** docs.futureagi.com | **Files scanned:** ${total} | **Date:** ${new Date().toISOString().slice(0, 10)}\n\n`;

out += `---\n\n## Summary Table\n\n`;
out += `| Check | Affected | % |\n|---|---|---|\n`;
out += `| Missing description | ${issues.missingDesc.length} | ${Math.round(issues.missingDesc.length/total*100)}% |\n`;
out += `| Duplicate title | ${dupTitleFiles.length} | ${Math.round(dupTitleFiles.length/total*100)}% |\n`;
out += `| No \`## About\` first heading | ${issues.noAboutHeading.length} | ${Math.round(issues.noAboutHeading.length/total*100)}% |\n`;
out += `| Title too short (<15) | ${issues.titleTooShort.length} | ${Math.round(issues.titleTooShort.length/total*100)}% |\n`;
out += `| Title too long (>60) | ${issues.titleTooLong.length} | ${Math.round(issues.titleTooLong.length/total*100)}% |\n`;
out += `| Generic/bare title | ${issues.titleGeneric.length} | ${Math.round(issues.titleGeneric.length/total*100)}% |\n`;
out += `| Description too short (<120) | ${issues.descTooShort.length} | ${Math.round(issues.descTooShort.length/total*100)}% |\n`;
out += `| Description too long (>155) | ${issues.descTooLong.length} | ${Math.round(issues.descTooLong.length/total*100)}% |\n`;
out += `| Description bad start phrase | ${issues.descBadStart.length} | ${Math.round(issues.descBadStart.length/total*100)}% |\n`;
out += `| Vague single-word headings | ${issues.vagueHeading.length} | ${Math.round(issues.vagueHeading.length/total*100)}% |\n`;
out += `| Heading hierarchy skip/H3-no-H2 | ${issues.skippedHeadingLevel.length} | ${Math.round(issues.skippedHeadingLevel.length/total*100)}% |\n`;
out += `| No TLDR block (AEO opportunity) | ${issues.noTldr.length} | ${Math.round(issues.noTldr.length/total*100)}% |\n`;
out += `| First para is code/list | ${issues.firstParaIsCodeOrList.length} | ${Math.round(issues.firstParaIsCodeOrList.length/total*100)}% |\n`;
out += `| Has question-style headings ✅ | ${issues.hasQuestionHeadings.length} | ${Math.round(issues.hasQuestionHeadings.length/total*100)}% |\n`;
out += `| Has Accordion/FAQ block ✅ | ${issues.hasAccordionOrFaq.length} | ${Math.round(issues.hasAccordionOrFaq.length/total*100)}% |\n`;

// ── CRITICAL ──────────────────────────────────────────────────────────────────
out += `\n---\n\n## 🔴 Critical Issues\n\n`;

out += `### 1. Missing \`description\` — ${pct(issues.missingDesc.length)}\n\n`;
if (issues.missingDesc.length === 0) out += '_None._\n';
else out += issues.missingDesc.map(f => `- ${f}`).join('\n') + '\n';

out += `\n### 2. Duplicate Titles — ${Object.keys(issues.dupTitle).length} groups\n\n`;
if (Object.keys(issues.dupTitle).length === 0) out += '_None._\n';
else out += Object.entries(issues.dupTitle).map(([t, fs_]) =>
  `**"${t}"** (${fs_.length} files)\n${fs_.map(f => `  - ${f}`).join('\n')}`
).join('\n\n') + '\n';

out += `\n### 3. No \`## About\` First Heading — ${pct(issues.noAboutHeading.length)}\n\n`;
if (issues.noAboutHeading.length === 0) out += '_None._\n';
else {
  // Group: no heading at all vs wrong heading
  const noHeading = issues.noAboutHeading.filter(x => x.firstH === '(none)');
  const wrongHeading = issues.noAboutHeading.filter(x => x.firstH !== '(none)');
  if (noHeading.length) {
    out += `**No headings at all** (${noHeading.length} files — typically API reference pages):\n`;
    out += noHeading.map(x => `- ${x.r}`).join('\n') + '\n\n';
  }
  if (wrongHeading.length) {
    out += `**Different first heading** (${wrongHeading.length} files):\n`;
    out += wrongHeading.map(x => `- \`${x.firstH}\` → ${x.r}`).join('\n') + '\n';
  }
}

// ── WARNING ───────────────────────────────────────────────────────────────────
out += `\n---\n\n## 🟡 Warnings\n\n`;

out += `### 4. Title Too Short (<15 chars) — ${pct(issues.titleTooShort.length)}\n\n`;
if (issues.titleTooShort.length === 0) out += '_None._\n';
else out += issues.titleTooShort.map(x => `- "${x.title}" (${x.len}) → ${x.r}`).join('\n') + '\n';

out += `\n### 5. Title Too Long (>60 chars) — ${pct(issues.titleTooLong.length)}\n\n`;
if (issues.titleTooLong.length === 0) out += '_None._\n';
else out += issues.titleTooLong.map(x => `- "${x.title}" (${x.len}) → ${x.r}`).join('\n') + '\n';

out += `\n### 6. Generic / Keyword-Poor Title — ${pct(issues.titleGeneric.length)}\n\n`;
if (issues.titleGeneric.length === 0) out += '_None._\n';
else out += issues.titleGeneric.map(x => `- "${x.title}" → ${x.r}`).join('\n') + '\n';

out += `\n### 7. Description Too Short (<120 chars) — ${pct(issues.descTooShort.length)}\n\n`;
if (issues.descTooShort.length === 0) out += '_None._\n';
else out += issues.descTooShort.map(x => `- (${x.len} chars) → ${x.r}`).join('\n') + '\n';

out += `\n### 8. Description Too Long (>155 chars) — ${pct(issues.descTooLong.length)}\n\n`;
if (issues.descTooLong.length === 0) out += '_None._\n';
else out += issues.descTooLong.map(x => `- (${x.len} chars) → ${x.r}`).join('\n') + '\n';

out += `\n### 9. Description Bad Start Phrase — ${pct(issues.descBadStart.length)}\n\n`;
if (issues.descBadStart.length === 0) out += '_None._\n';
else out += issues.descBadStart.map(x => `- "${x.desc}..." → ${x.r}`).join('\n') + '\n';

out += `\n### 10. Vague Single-Word Headings — ${pct(issues.vagueHeading.length)} files affected\n\n`;
if (issues.vagueHeading.length === 0) out += '_None._\n';
else out += issues.vagueHeading.map(x => `- ${x.r}\n${x.headings.map(h => `  - \`${h}\``).join('\n')}`).join('\n') + '\n';

out += `\n### 11. Heading Hierarchy Issues (skipped level / H3 before H2) — ${pct(issues.skippedHeadingLevel.length)}\n\n`;
if (issues.skippedHeadingLevel.length === 0) out += '_None._\n';
else out += issues.skippedHeadingLevel.map(x => `- ${x.r}\n${x.problems.map(p => `  - ${p}`).join('\n')}`).join('\n') + '\n';

// ── INFO / AEO ────────────────────────────────────────────────────────────────
out += `\n---\n\n## 🔵 AEO / GEO Opportunities\n\n`;

out += `### 12. No TLDR Block — ${pct(issues.noTldr.length)} files lack a summary block\n\n`;
out += `_A \`<TLDR>\` component or \`## TL;DR\` section near the top helps LLMs extract concise answers for AI-generated responses._\n\n`;
out += `Pages with highest priority (most content, no TLDR) — top 30:\n\n`;
// Sort by file path depth (deeper = more specific = higher value for TLDR)
const noTldrTop = issues.noTldr
  .filter(f => !f.includes('/api/') && !f.includes('index'))
  .slice(0, 30);
out += noTldrTop.map(f => `- ${f}`).join('\n') + '\n';
if (issues.noTldr.length > 30) out += `\n_...and ${issues.noTldr.length - 30} more (mostly API reference pages)._\n`;

out += `\n### 13. First Paragraph Is Code Block or List — ${pct(issues.firstParaIsCodeOrList.length)}\n\n`;
out += `_Generative engines prefer prose definitions before code. Pages that open with a code block or bullet list after the heading miss the chance to define the concept in plain language._\n\n`;
if (issues.firstParaIsCodeOrList.length === 0) out += '_None._\n';
else out += issues.firstParaIsCodeOrList.map(f => `- ${f}`).join('\n') + '\n';

out += `\n### 14. Question-Style Headings (AEO signal) ✅\n\n`;
out += `${issues.hasQuestionHeadings.length} pages already use question-style headings — good for AEO.\n\n`;
out += `**${issues.noQuestionHeadings.length} pages have no question-style headings** — opportunity to add "What is X?", "How does Y work?", "When should I use Z?" sub-sections.\n\n`;
out += `Pages with question headings (examples):\n`;
out += issues.hasQuestionHeadings.slice(0, 15).map(x => `- ${x.r} (${x.count} question headings)`).join('\n') + '\n';

out += `\n### 15. Accordion / FAQ Blocks (AEO signal) ✅\n\n`;
out += `${issues.hasAccordionOrFaq.length} pages have \`<Accordion>\` or FAQ sections — these are strong AEO signals.\n\n`;
if (issues.hasAccordionOrFaq.length > 0) {
  out += issues.hasAccordionOrFaq.map(f => `- ${f}`).join('\n') + '\n';
}

// ── TOP 20 ────────────────────────────────────────────────────────────────────
out += `\n---\n\n## 📋 Top 20 Pages by Issue Count (Priority Rewrite List)\n\n`;
out += `| # | File | Issues |\n|---|---|---|\n`;
out += top20.map(([f, n], i) => `| ${i + 1} | ${f} | ${n} |`).join('\n') + '\n';

fs.writeFileSync(path.join(ROOT, 'aeo-audit-report.md'), out);
console.log(out);
console.error('\nReport saved to aeo-audit-report.md');
