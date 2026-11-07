import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

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
  for (const field of ['.futureagi-skills.lock.json', 'X-Api-Key', 'X-Secret-Key', 'requests', 'fetch(', 'version_id', 'digest']) assert.ok(page.includes(field));
  const versions = read('versions-and-labels');
  assert.match(versions, /neither.*`production`/);
  assert.match(versions, /missing label.*404/);
  const mcp = read('mcp-tools');
  for (const tool of ['list_skills', 'get_skill', 'read_skill_file', 'publish_skill', 'set_skill_label', 'update_skill_tags']) assert.ok(mcp.includes(`\`${tool}\``));
  for (const field of ['next_offset', 'eof', 'sha256', '24000', 'character offsets', 'standalone']) assert.ok(mcp.includes(field));
  assert.match(read('index'), /fetch.*does not prove.*used/i);
});
