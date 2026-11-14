// @ts-check
/**
 * Decide which futureagi-sdk revision the reference should be synced from, and
 * whether the resulting docs PR may be published as stable or must stay a draft.
 *
 *   node scripts/sdk-reference-release.mjs [--ref <sha|tag|branch>] [--stage released|candidate|preview] [--json]
 *
 * Without --ref it picks the newest published SDK release: the SDK versions and
 * publishes its Python and TypeScript packages independently, so it takes the newest
 * `python-v*` tag and the newest `typescript-v*` tag and keeps whichever commit is
 * later, so a TypeScript-only release is never missed and older pages are never
 * proposed over newer ones. The result (printed as `key=value` lines, or JSON with
 * --json) carries the full commit SHA, the Python/TypeScript versions from the
 * SDK's release manifest at that commit, the backend release the contract was
 * synced from, and `branch`, the docs branch for this release: one branch (so one
 * PR) per SDK version pair, however many times the sync runs.
 *
 * `stage` is what the caller claims; `publish` is what the registries confirm.
 * A `released` claim is downgraded to `candidate` unless its commit matches a
 * component release tag AND BOTH manifest versions are installable from PyPI
 * and npm. Any package not tagged at that commit must have an identical source
 * tree to its own release tag. Published version strings alone are not enough.
 * `preview` (any ref, usually dev) is
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

/**
 * The newest `<prefix>vX.Y.Z` tag's name (by semantic version, not by push order), or
 * null when that package has no release tag yet.
 * @param {{ref: string}[]} refs @param {'python-' | 'typescript-'} prefix
 */
export function newestTag(refs, prefix) {
  const pattern = new RegExp(`^${prefix}v(\\d+)\\.(\\d+)\\.(\\d+)$`);
  const versions = refs
    .map((ref) => ref.ref.replace('refs/tags/', ''))
    .map((tag) => ({ tag, match: pattern.exec(tag) }))
    .filter((entry) => entry.match)
    .map((entry) => ({ tag: entry.tag, version: entry.match.slice(1, 4).map(Number) }))
    .sort((a, b) => a.version[0] - b.version[0] || a.version[1] - b.version[1] || a.version[2] - b.version[2]);
  return versions.length ? versions[versions.length - 1].tag : null;
}

/** Kept for callers of the old name: the newest python-v* tag, or an error when none. */
export function newestPythonTag(/** @type {{ref: string}[]} */ refs) {
  const tag = newestTag(refs, 'python-');
  if (!tag) throw new Error(`${SDK_REPO} has no python-v* release tag yet`);
  return tag;
}

/**
 * The newest published SDK commit across both package release streams: the newest
 * Python tag and the newest TypeScript tag, resolved to commits, the later commit wins.
 * @param {{ref: string}[]} refs
 * @param {(ref: string) => Promise<string>} resolveSha
 * @param {(sha: string) => Promise<string>} commitDate ISO 8601 committer date
 * @returns {Promise<{ref: string, sha: string}>}
 */
export async function newestRelease(refs, resolveSha, commitDate) {
  const tags = [newestTag(refs, 'python-'), newestTag(refs, 'typescript-')].filter((t) => t !== null);
  if (!tags.length) throw new Error(`${SDK_REPO} has no python-v* or typescript-v* release tag yet`);
  const candidates = await Promise.all(tags.map(async (tag) => {
    const sha = await resolveSha(tag);
    return { ref: tag, sha, date: Date.parse(await commitDate(sha)) };
  }));
  candidates.sort((a, b) => b.date - a.date || a.ref.localeCompare(b.ref));
  return { ref: candidates[0].ref, sha: candidates[0].sha };
}

/** @param {string} ref a tag, branch or commit; returns the full commit SHA. */
async function resolveSha(ref) {
  const commit = await github(`commits/${encodeURIComponent(ref)}`);
  if (!/^[0-9a-f]{40}$/.test(commit.sha)) throw new Error(`cannot resolve ${ref} to a commit`);
  return commit.sha;
}

/** @param {string} sha */
async function commitDate(sha) {
  const commit = await github(`commits/${sha}`);
  return commit.commit.committer.date;
}

/** Content identity of a package directory; non-recursive trees cannot truncate a file diff.
 * @param {string} sha @param {string} directory
 */
async function packageTree(sha, directory) {
  let tree = sha;
  for (const part of directory.split('/')) {
    const result = await github(`git/trees/${tree}`);
    if (result.truncated) throw new Error(`truncated tree for ${directory} at ${sha}`);
    const entry = result.tree.find((item) => item.path === part && item.type === 'tree');
    if (!entry) throw new Error(`missing package ${directory} at ${sha}`);
    tree = entry.sha;
  }
  return tree;
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
 * @param {{resolveSha?: typeof resolveSha, fileAt?: typeof fileAt, commitDate?: typeof commitDate, packageTree?: typeof packageTree, tags?: () => Promise<{ref: string}[]>, onPyPI?: typeof onPyPI, onNpm?: typeof onNpm}} [io]
 */
export async function resolve(options, io = {}) {
  const get = {
    resolveSha: io.resolveSha ?? resolveSha,
    fileAt: io.fileAt ?? fileAt,
    commitDate: io.commitDate ?? commitDate,
    packageTree: io.packageTree ?? packageTree,
    // Both package release streams; the SDK versions Python and TypeScript independently.
    tags: io.tags ?? (async () => [...(await github('git/matching-refs/tags/python-v')), ...(await github('git/matching-refs/tags/typescript-v'))]),
    onPyPI: io.onPyPI ?? onPyPI,
    onNpm: io.onNpm ?? onNpm,
  };
  let ref = options.ref?.trim() || '';
  let stage = options.stage?.trim() || (ref ? 'preview' : 'released');
  let sha;
  if (!ref) {
    ({ ref, sha } = await newestRelease(await get.tags(), get.resolveSha, get.commitDate));
    stage = options.stage?.trim() || 'released';
  } else {
    sha = await get.resolveSha(ref);
  }
  const manifest = JSON.parse(await get.fileAt('.release-please-manifest.json', sha));
  const python = manifest['python'];
  const typescript = manifest['typescript/futureagi'];
  if (!python || !typescript) throw new Error(`release manifest at ${sha} lacks the python or typescript/futureagi version`);
  const backend = (await get.fileAt('sdkgen/contracts/BACKEND_VERSION', sha)).trim();
  const installable = stage === 'released' ? (await get.onPyPI(python)) && (await get.onNpm(typescript)) : false;
  // A dev/candidate commit can retain already-published version strings while
  // adding methods. Registry existence alone must not make its pages stable.
  // Independent releases are valid only if the other package is byte-identical
  // to its own release tag. Otherwise a chore-only source change could hide behind
  // an unchanged, already-installable version while the other package releases.
  let releaseCommit = false;
  if (installable) {
    const refs = new Set((await get.tags()).map((tag) => tag.ref.replace('refs/tags/', '')));
    let tagged = false;
    let aligned = true;
    for (const [tag, directory] of [[`python-v${python}`, 'python'], [`typescript-v${typescript}`, 'typescript/futureagi']]) {
      if (!refs.has(tag)) { aligned = false; break; }
      const releasedSha = await get.resolveSha(tag);
      if (releasedSha === sha) {
        tagged = true;
      } else if (await get.packageTree(releasedSha, directory) !== await get.packageTree(sha, directory)) {
        aligned = false;
      }
    }
    releaseCommit = tagged && aligned;
  }
  const decision = decide({ stage, sha, python, typescript, installable: installable && releaseCommit });
  return { ref, sha, python, typescript, backend, installable, releaseCommit, ...decision };
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
