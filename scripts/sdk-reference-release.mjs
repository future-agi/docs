// @ts-check
/**
 * Decide which futureagi-sdk revision the reference should be synced from, and
 * whether the resulting docs PR may be published as stable or must stay a draft.
 *
 *   node scripts/sdk-reference-release.mjs [--ref <sha|tag|branch>] [--stage released|candidate|preview] [--json]
 *
 * Without --ref it picks the newest published SDK release: the commit of the
 * newest `python-v*` tag. The result (printed as `key=value` lines, or JSON with
 * --json) carries the full commit SHA, the Python/TypeScript versions from the
 * SDK's release manifest at that commit, the backend release the contract was
 * synced from, and `branch`, the docs branch for this release: one branch (so one
 * PR) per SDK version pair, however many times the sync runs.
 *
 * `stage` is what the caller claims; `publish` is what the registries confirm.
 * A `released` claim is downgraded to `candidate` unless BOTH packages at those
 * versions are installable from PyPI and npm, so a docs PR never leaves draft
 * for an SDK users cannot install yet. `preview` (any ref, usually dev) is
 * always a draft and gets its own branch keyed by commit.
 *
 * Reads only public endpoints (api.github.com, pypi.org, registry.npmjs.org);
 * GH_TOKEN or GITHUB_TOKEN is used for GitHub when present to avoid rate limits.
 * .github/workflows/sdk-reference-sync.yml runs it; `node --test scripts/` covers it.
 */
import process from 'node:process';

export const SDK_REPO = 'future-agi/futureagi-sdk';
const STAGES = new Set(['released', 'candidate', 'preview']);

/** @param {string} url @param {RequestInit} [init] */
async function fetchJson(url, init) {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

/** @param {string} path */
async function github(path) {
  const token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN;
  /** @type {Record<string, string>} */
  const headers = { accept: 'application/vnd.github+json', 'user-agent': 'future-agi-docs-sdk-reference' };
  if (token) headers.authorization = `Bearer ${token}`;
  return fetchJson(`https://api.github.com/repos/${SDK_REPO}/${path}`, { headers });
}

/** The newest python-v* tag's name (by semantic version, not by push order). */
export function newestPythonTag(/** @type {{ref: string}[]} */ refs) {
  const versions = refs
    .map((ref) => ref.ref.replace('refs/tags/', ''))
    .map((tag) => ({ tag, match: /^python-v(\d+)\.(\d+)\.(\d+)$/.exec(tag) }))
    .filter((entry) => entry.match)
    .map((entry) => ({ tag: entry.tag, version: entry.match.slice(1, 4).map(Number) }))
    .sort((a, b) => a.version[0] - b.version[0] || a.version[1] - b.version[1] || a.version[2] - b.version[2]);
  if (!versions.length) throw new Error(`${SDK_REPO} has no python-v* release tag yet`);
  return versions[versions.length - 1].tag;
}

/** @param {string} ref a tag, branch or commit; returns the full commit SHA. */
async function resolveSha(ref) {
  const commit = await github(`commits/${encodeURIComponent(ref)}`);
  if (!/^[0-9a-f]{40}$/.test(commit.sha)) throw new Error(`cannot resolve ${ref} to a commit`);
  return commit.sha;
}

/** @param {string} path @param {string} sha */
async function fileAt(path, sha) {
  const file = await github(`contents/${path}?ref=${sha}`);
  return Buffer.from(file.content, 'base64').toString('utf-8');
}

/** @param {string} version */
export async function onPyPI(version) {
  const response = await fetch(`https://pypi.org/pypi/futureagi/${version}/json`);
  return response.status === 200;
}

/** @param {string} version */
export async function onNpm(version) {
  const response = await fetch(`https://registry.npmjs.org/@future-agi%2fsdk/${version}`);
  return response.status === 200;
}

/**
 * Pure part: branch and publish decision from the facts.
 * @param {{stage: string, sha: string, python: string, typescript: string, installable: boolean}} facts
 */
export function decide({ stage, sha, python, typescript, installable }) {
  if (!STAGES.has(stage)) throw new Error(`stage must be one of ${[...STAGES].join(', ')}, not ${stage}`);
  if (stage === 'preview') {
    return { branch: `sdk-reference/preview-${sha.slice(0, 12)}`, publish: 'draft', stage };
  }
  const branch = `sdk-reference/python-v${python}-typescript-v${typescript}`;
  if (stage === 'released' && installable) return { branch, publish: 'ready', stage };
  return { branch, publish: 'draft', stage: 'candidate' };
}

/**
 * @param {{ref?: string, stage?: string}} options
 * @param {{resolveSha?: typeof resolveSha, fileAt?: typeof fileAt, tags?: () => Promise<{ref: string}[]>, onPyPI?: typeof onPyPI, onNpm?: typeof onNpm}} [io]
 */
export async function resolve(options, io = {}) {
  const get = {
    resolveSha: io.resolveSha ?? resolveSha,
    fileAt: io.fileAt ?? fileAt,
    tags: io.tags ?? (() => github('git/matching-refs/tags/python-v')),
    onPyPI: io.onPyPI ?? onPyPI,
    onNpm: io.onNpm ?? onNpm,
  };
  let ref = options.ref?.trim() || '';
  let stage = options.stage?.trim() || (ref ? 'preview' : 'released');
  if (!ref) {
    ref = newestPythonTag(await get.tags());
    stage = options.stage?.trim() || 'released';
  }
  const sha = await get.resolveSha(ref);
  const manifest = JSON.parse(await get.fileAt('.release-please-manifest.json', sha));
  const python = manifest['python'];
  const typescript = manifest['typescript/futureagi'];
  if (!python || !typescript) throw new Error(`release manifest at ${sha} lacks the python or typescript/futureagi version`);
  const backend = (await get.fileAt('sdkgen/contracts/BACKEND_VERSION', sha)).trim();
  const installable = stage === 'released' ? (await get.onPyPI(python)) && (await get.onNpm(typescript)) : false;
  const decision = decide({ stage, sha, python, typescript, installable });
  return { ref, sha, python, typescript, backend, installable, ...decision };
}

function parseArgs(argv) {
  /** @type {{ref?: string, stage?: string, json?: boolean}} */
  const options = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--ref') options.ref = argv[++i];
    else if (argv[i] === '--stage') options.stage = argv[++i];
    else if (argv[i] === '--json') options.json = true;
    else throw new Error(`unknown argument ${argv[i]}`);
  }
  return options;
}

if (process.argv[1] && import.meta.url === new URL(process.argv[1], 'file://').href) {
  const options = parseArgs(process.argv.slice(2));
  resolve(options)
    .then((result) => {
      if (options.json) {
        console.log(JSON.stringify(result, null, 2));
      } else {
        for (const [key, value] of Object.entries(result)) console.log(`${key}=${value}`);
      }
    })
    .catch((error) => {
      console.error(error.message);
      process.exit(1);
    });
}
