import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:http';

const root = new URL('../', import.meta.url);
const names = ['index', 'quickstart', 'import-skills', 'versions-and-labels', 'use-in-agents', 'mcp-tools', 'checks-reference', 'api-reference', 'troubleshooting'];
const read = name => readFileSync(new URL(`src/pages/docs/skills/${name}.mdx`, root), 'utf8');
const navigation = readFileSync(new URL('src/lib/navigation.ts', root), 'utf8');

for (const name of names) {
  test(`${name}: page structure, discovery, links, and hand-written examples`, () => {
    const page = read(name);
    assert.match(page, /^---\ntitle: "[^"]+"\ndescription: "[^"]+"\n---\n\n## About\n/);
    assert.match(page, /\n## Next steps\n/);
    assert.doesNotMatch(page, /<ApiPlayground|TODO|FIXME/);
    assert.ok(navigation.includes(`'/docs/skills${name === 'index' ? '' : `/${name}`}'`));
    for (const [, path] of page.matchAll(/\]\((\/docs\/[^)#]+)(?:#[^)]*)?\)/g)) {
      assert.ok(['.mdx', '.astro', '/index.mdx', '/index.astro'].some(suffix => existsSync(new URL(`src/pages${path}${suffix}`, root))), `Broken link ${path}`);
    }
    for (const [, language, code] of page.matchAll(/```(bash|python|typescript|json)\n([\s\S]*?)```/g)) {
      if (language === 'json') {
        assert.doesNotThrow(() => JSON.parse(code));
        continue;
      }
      const command = language === 'bash' ? ['bash', ['-n']] : language === 'python'
        ? ['python3', ['-I', '-c', 'import ast, sys; ast.parse(sys.stdin.read())']]
        : [process.execPath, ['--input-type=module', '--check']];
      const result = spawnSync(command[0], command[1], { input: code, encoding: 'utf8' });
      assert.equal(result.status, 0, `${language} syntax: ${result.stderr || result.error}`);
    }
  });
}

test('API reference covers all 21 endpoint groups and every method', () => {
  const page = read('api-reference');
  const operations = [
    ['GET', ''], ['POST', ''], ['GET', 'templates/'], ['POST', 'checks/'],
    ['POST', 'publish/'], ['GET', 'resolve/'], ['GET', 'download/'],
    ['POST', 'import/preview/'], ['POST', 'import/'],
    ['GET', '{skill_id}/'], ['PATCH', '{skill_id}/'], ['DELETE', '{skill_id}/'],
    ['GET', '{skill_id}/versions/'], ['POST', '{skill_id}/versions/'],
    ['GET', '{skill_id}/versions/{number}/'], ['GET', '{skill_id}/versions/{number}/files/'],
    ['GET', '{skill_id}/versions/{number}/download/'], ['POST', '{skill_id}/versions/{number}/restore/'],
    ['GET', '{skill_id}/compare/'], ['GET', '{skill_id}/labels/'],
    ['PUT', '{skill_id}/labels/{label}/'], ['DELETE', '{skill_id}/labels/{label}/'],
    ['GET', '{skill_id}/labels/history/'], ['GET', '{skill_id}/draft/'],
    ['PUT', '{skill_id}/draft/'], ['DELETE', '{skill_id}/draft/'],
    ['POST', '{skill_id}/draft/publish/'], ['GET', '{skill_id}/usage/'],
  ];
  for (const [method, path] of operations) {
    assert.ok(page.includes(`\`${method} /model-hub/skills/${path}\``), `Missing ${method} ${path}`);
  }
  for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
    assert.ok(page.includes(`-X ${method}`), `No explicit ${method} example`);
  }
  for (const field of ['version_id', 'digest', 'next_offset', 'expected_version', 'revision', 'include_content', 'If-None-Match', 'X-Workspace-Id']) {
    assert.ok(page.includes(field), `Missing contract field ${field}`);
  }
  assert.match(page, /JWT.*not.*API key/);
});

test('checks and error references retain the complete public code inventory', () => {
  const checks = read('checks-reference');
  const codes = ['root_missing', 'frontmatter_missing', 'frontmatter_invalid', 'name_missing', 'name_invalid', 'name_mismatch', 'description_missing', 'description_too_long', 'compatibility_too_long', 'metadata_invalid', 'path_invalid', 'path_duplicate', 'file_too_large', 'too_many_files', 'bundle_too_large', 'file_not_text', 'secret_suspected', 'link_broken', 'skill_md_long', 'skill_md_tokens', 'description_short', 'frontmatter_unknown_key', 'file_empty', 'host_extension', 'allowed_tools_note', 'executable_content', 'description_trigger_hint'];
  for (const code of codes) assert.ok(checks.includes(`\`${code}\``), `Missing check ${code}`);
  const errors = read('troubleshooting');
  for (const code of ['workspace_required', 'skill_not_found', 'version_not_found', 'label_not_found', 'draft_not_found', 'nothing_to_download', 'invalid_selector', 'invalid_name', 'invalid_label', 'invalid_tags', 'name_taken', 'stale_base', 'label_conflict', 'draft_conflict', 'checks_failed', 'warnings_unacknowledged', 'payload_too_large', 'import_invalid']) {
    assert.ok(errors.includes(`\`${code}\``), `Missing error ${code}`);
  }
});

test('consumption docs preserve selector, installation, and MCP safety contracts', () => {
  const page = read('use-in-agents');
  for (const dir of ['.claude/skills', '~/.claude/skills', '.agents/skills', '~/.agents/skills', '.cursor/skills', '~/.cursor/skills', '.gemini/skills', '~/.gemini/skills', '.github/skills', '~/.copilot/skills']) assert.ok(page.includes(dir));
  // Application reads use the read-only Context credential and the SDK, matching the Install tab.
  for (const field of ['FI_CONTEXT_CREDENTIAL', 'FI_CONTEXT_ORIGIN', 'FI_CONTEXT_ORGANIZATION_ID', 'FI_CONTEXT_WORKSPACE_ID', 'SkillsClient', 'ContextAuth', '/model-hub/skills/consumption/resolve/', 'version_id', 'digest']) assert.ok(page.includes(field), field);
  assert.ok(read('quickstart').includes('.futureagi-skills.lock.json'));
  const versions = read('versions-and-labels');
  assert.match(versions, /neither.*`production`/);
  assert.match(versions, /missing label.*404/);
  const mcp = read('mcp-tools');
  for (const tool of ['list_skills', 'get_skill', 'read_skill_file', 'publish_skill', 'set_skill_label', 'update_skill_tags']) assert.ok(mcp.includes(`\`${tool}\``));
  for (const field of ['next_offset', 'eof', 'sha256', '24000', 'character offsets', 'standalone']) assert.ok(mcp.includes(field));
  assert.match(read('index'), /fetch.*does not prove.*used/i);
});

test('amendments use files multipart field and workspace-wide list stats', () => {
  for (const name of names) assert.doesNotMatch(read(name), /files\[\]/);
  assert.match(read('import-skills'), /-F 'files=@team-skills\.zip/);
  const api = read('api-reference');
  for (const field of ['stats', 'total', 'in_production', 'fetches_7d', 'my_drafts']) assert.ok(api.includes(field));
  assert.match(api, /statistics cover the workspace, unaffected/);
});

test('skill links point to real headings, not just existing pages', () => {
  const slug = heading => heading.toLowerCase().replace(/[`*_]/g, '').replace(/[^\p{L}\p{N}\s-]/gu, '').replace(/\s+/g, '-');
  for (const name of names) {
    for (const [, target, anchor] of read(name).matchAll(/\]\(\/docs\/skills(?:\/([a-z-]+))?#([a-z-]+)\)/g)) {
      const headings = [...read(target ?? 'index').matchAll(/^##+ (.+)$/gm)].map(([, heading]) => slug(heading));
      assert.ok(headings.includes(anchor), `${name}: missing anchor ${target}#${anchor}`);
    }
  }
});

test('screenshots have either explicit placeholders or existing image files', () => {
  const all = names.map(read).join('\n');
  const shots = [...all.matchAll(/\{\/\* screenshot: ([a-z-]+\.png) — ([^\n]+) \*\/\}/g)];
  const images = [...all.matchAll(/!\[([^\]]+)\]\(\/images\/docs\/skills\/([a-z-]+\.png)\)/g)];
  // The sealed guides replace obsolete label-dialog instructions with exact release review.
  // Preserve all original assets while validating every currently referenced screenshot.
  // use-in-agents now links (rather than embeds) its two earlier captures.
  assert.equal(shots.length + images.length, 8);
  assert.equal(new Set([...shots.map(([, file]) => file), ...images.map(([, , file]) => file)]).size, shots.length + images.length);
  for (const file of ['skills-library', 'skills-create', 'skills-editor-checks', 'skills-publish', 'skills-import-preview', 'skills-import-result', 'skills-compare', 'skills-move-label', 'skills-label-history', 'skills-use-clients', 'skills-use-claude-code', 'skills-usage']) {
    assert.ok(existsSync(new URL(`public/images/docs/skills/${file}.png`, root)), `Missing retained original capture ${file}`);
  }
  for (const [, , description] of shots) assert.match(description, /light theme/);
  for (const [, alt, file] of images) {
    assert.ok(alt.trim().length > 10, `Descriptive alt text required for ${file}`);
    assert.ok(existsSync(new URL(`public/images/docs/skills/${file}`, root)), `Missing screenshot ${file}`);
  }
});

test('all 31 cURL operation examples send the documented verb, route, headers, and multipart field', async () => {
  const page = read('api-reference');
  const requests = [];
  const server = createServer((req, res) => {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      requests.push({ method: req.method, url: req.url, headers: req.headers, body });
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: true, result: req.url.endsWith('/restore-review/')
        ? { name_collision: false, resource: { release_revision: 7 }, review_fingerprint: `sha256:${'a'.repeat(64)}` }
        : {} }));
    });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const cwd = mkdtempSync(join(tmpdir(), 'skills-docs-curl-'));
  try {
    const json = [...page.matchAll(/```json\n([\s\S]*?)```/g)].map(([, code]) => code);
    for (const [index, file] of ['files.json', 'version.json', 'draft.json'].entries()) writeFileSync(join(cwd, file), json[index]);
    writeFileSync(join(cwd, 'team-skills.zip'), 'Synthetic transport fixture, not an archive-parser test.');
    const sections = page.split(/(?=^`(?:GET|POST|PUT|PATCH|DELETE) \/model-hub\/skills\/)/m).slice(1);
    assert.equal(sections.length, 31);
    for (const section of sections) {
      const [, method, path] = section.match(/^`(\w+) (\/model-hub\/skills\/[^`]+|\/model-hub\/skills\/)`/);
      const [, code] = section.match(/```bash\n([\s\S]*?)```/);
      const child = spawn('bash', ['-e', '-c', `BASE="$HOST_API/model-hub/skills"\nAUTH=(-H "X-Api-Key: $FI_API_KEY" -H "X-Secret-Key: $FI_SECRET_KEY" -H "X-Workspace-Id: $FI_WORKSPACE_ID")\nJSON=(-H 'Content-Type: application/json')\n${code}`], {
        cwd,
        env: { ...process.env, HOST_API: `http://127.0.0.1:${server.address().port}`, FI_API_KEY: 'synthetic-key', FI_SECRET_KEY: 'synthetic-secret', FI_WORKSPACE_ID: 'synthetic-workspace', SKILL_ID: 'synthetic-id', ARCHIVED_SKILL_ID: '00000000-0000-4000-8000-000000000001', RESTORE_OPERATION_ID: '00000000-0000-4000-8000-000000000002', SELECTED_KEYS: '["reviewed-key"]' },
        timeout: 15000,
      });
      let stderr = '';
      child.stderr.on('data', data => { stderr += data; });
      child.stdout.resume();
      const exit = await new Promise((resolve, reject) => { child.on('error', reject); child.on('close', resolve); });
      assert.equal(exit, 0, stderr);
      const request = requests.at(-1);
      assert.equal(request.method, method);
      const expected = path.replace('{skill_id}', 'synthetic-id').replace('{resource_id}', '00000000-0000-4000-8000-000000000001').replace('{number}', '1').replace('{label}', method === 'DELETE' ? 'staging' : 'production');
      assert.equal(new URL(request.url, 'http://localhost').pathname, expected);
      assert.equal(request.headers['x-api-key'], 'synthetic-key');
      assert.equal(request.headers['x-secret-key'], 'synthetic-secret');
      assert.equal(request.headers['x-workspace-id'], 'synthetic-workspace');
      if (path.includes('/import/')) {
        assert.match(request.headers['content-type'], /multipart\/form-data; boundary=/);
        assert.match(request.body, /name="files"; filename="team-skills.zip"/);
        assert.doesNotMatch(request.body, /name="files\[\]"/);
      } else if (request.body) assert.doesNotThrow(() => JSON.parse(request.body));
      if (path === '/model-hub/skills/archived/') {
        assert.deepEqual(Object.fromEntries(new URL(request.url, 'http://localhost').searchParams), { page: '1', page_size: '25' });
      }
      if (path === '/model-hub/skills/archived/{resource_id}/restore/') {
        assert.equal(request.headers['idempotency-key'], '00000000-0000-4000-8000-000000000002');
        assert.deepEqual(JSON.parse(request.body), {
          expected_release_revision: 7,
          expected_review_fingerprint: `sha256:${'a'.repeat(64)}`,
          note: 'Restore the reviewed original skill',
        });
      }
    }
    assert.equal(requests.length, 31);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    rmSync(cwd, { recursive: true, force: true });
  }
});

// The application examples are the Install tab's SDK snippets. Statically, they must use the
// read-only Context credential, resolve once, and read verified files; with
// SKILLS_DOCS_LIVE=1 they run unmodified against an isolated localhost stack with the SDK installed.
const appExamples = () => Object.fromEntries([...read('use-in-agents').matchAll(/```(python|typescript)\n([\s\S]*?)```/g)]
  .filter(([, , code]) => code.includes('SkillsClient')).map(([, language, code]) => [language, code]));

test('application examples use the read-only SDK client, never broad keys', () => {
  const { python, typescript } = appExamples();
  assert.ok(python && typescript);
  for (const code of [python, typescript]) {
    for (const name of ['FI_CONTEXT_CREDENTIAL', 'FI_CONTEXT_ORIGIN', 'FI_CONTEXT_WORKSPACE_ID', 'FI_CONTEXT_ORGANIZATION_ID']) assert.ok(code.includes(name), name);
    assert.doesNotMatch(code, /FI_API_KEY|FI_SECRET_KEY|X-Api-Key|X-Secret-Key/);
    assert.match(code, /resolve\("support-policy", \{? ?label: ?"production"|resolve\("support-policy", label="production"\)/);
  }
  assert.match(python, /from fi\.platform import Client, ContextAuth/);
  assert.match(python, /skill\.read_file\("SKILL\.md"\)/);
  assert.match(typescript, /from "@future-agi\/sdk"/);
  assert.match(typescript, /auth: \{ type: "context", credential \}/);
  assert.match(typescript, /await skill\.readFile\("SKILL\.md"\)/);
});

for (const language of ['python', 'typescript']) {
  test(`${language} application example runs against the isolated stack`, { skip: process.env.SKILLS_DOCS_LIVE === '1' ? false : 'set SKILLS_DOCS_LIVE=1 on the cloud lane' }, async () => {
    for (const name of ['FI_CONTEXT_CREDENTIAL', 'FI_CONTEXT_ORIGIN', 'FI_CONTEXT_WORKSPACE_ID', 'FI_CONTEXT_ORGANIZATION_ID']) assert.ok(process.env[name], name);
    assert.equal(new URL(process.env.FI_CONTEXT_ORIGIN).hostname, 'localhost', 'Only the isolated localhost stack is permitted');
    const code = appExamples()[language];
    const executable = language === 'python' ? (process.env.SKILLS_DOCS_PYTHON ?? 'python3') : process.execPath;
    const args = language === 'python' ? ['-I', '-c', code] : ['--input-type=module', '-e', code];
    const child = spawn(executable, args, { cwd: process.env.SKILLS_DOCS_NODE_CWD ?? process.cwd(), env: process.env, timeout: 60000 });
    let stdout = '', stderr = '';
    child.stdout.on('data', data => { stdout += data; });
    child.stderr.on('data', data => { stderr += data; });
    const exit = await new Promise((resolve, reject) => { child.on('error', reject); child.on('close', resolve); });
    assert.equal(exit, 0, stderr.split('\n').filter(line => /Error|error/.test(line)).slice(-3).join('\n'));
    assert.match(stdout, /^[0-9a-f-]{36} sha256:[0-9a-f]{64}$/m);
    if (process.env.SKILLS_DOCS_EXPECT_VERSION_ID) assert.ok(stdout.includes(process.env.SKILLS_DOCS_EXPECT_VERSION_ID));
  });
}
