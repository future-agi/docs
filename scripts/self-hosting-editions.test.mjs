// Checks the self-hosted Community and Enterprise editions page, its nav
// entry and the pages that link to it. Run: node --test scripts/self-hosting-editions.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PAGES = path.join(ROOT, "src/pages");
const EDITIONS = "src/pages/docs/self-hosting/editions.mdx";
const USERS = "src/pages/docs/self-hosting/user-management.mdx";

const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const exists = (rel) => fs.existsSync(path.join(ROOT, rel));
// What a reader sees: MDX comments removed.
const rendered = (s) => s.replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
const comments = (s) => [...s.matchAll(/\{\/\*([\s\S]*?)\*\/\}/g)].map((m) => m[1]);
const withoutFences = (s) => s.replace(/^```[\s\S]*?^```/gm, "");
// One line per sentence-ish chunk, so phrases split over lines still match.
const flat = (s) => s.replace(/\s+/g, " ");

function editions() {
  assert.ok(exists(EDITIONS), `${EDITIONS} is missing`);
  return read(EDITIONS);
}

function tableRows(s) {
  return s
    .split("\n")
    .filter((l) => /^\|.*\|$/.test(l) && !/^\|[-| ]+\|$/.test(l))
    .map((l) => l.slice(1, -1).split("|").map((c) => c.trim()));
}

function slug(heading) {
  return heading
    .toLowerCase()
    .replace(/`/g, "")
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/\s/g, "-");
}

function headingIds(rel) {
  return new Set(
    [...withoutFences(read(rel)).matchAll(/^#{2,4} (.+)$/gm)].map((m) => slug(m[1])),
  );
}

function pageFile(href) {
  const p = href.split("#")[0].replace(/\/$/, "");
  for (const candidate of [`${p}.mdx`, `${p}.md`, `${p}/index.mdx`, `${p}.astro`]) {
    if (fs.existsSync(path.join(PAGES, candidate))) return path.join("src/pages", candidate);
  }
  return null;
}

function assertLinksResolve(rel) {
  const text = rendered(read(rel));
  const links = [...text.matchAll(/(?:\]\(|href=")(\/docs\/[^)"\s]*|#[^)"\s]+)/g)].map((m) => m[1]);
  assert.ok(links.length > 0, `${rel} has no internal links`);
  for (const href of links) {
    const target = href.startsWith("#") ? rel : pageFile(href);
    assert.ok(target, `${rel}: ${href} names no page`);
    const anchor = href.split("#")[1];
    if (anchor) {
      assert.ok(headingIds(target).has(anchor), `${rel}: ${href} names no heading in ${target}`);
    }
  }
}

test("editions page: frontmatter, first heading About, no H1, no em dash", () => {
  const s = editions();
  assert.match(s, /^---\ntitle: "[^"\n]+"\ndescription: "[^"\n]+"\n---\n/);
  const headings = [...withoutFences(s).matchAll(/^## (.+)$/gm)].map((m) => m[1]);
  assert.equal(headings[0], "About");
  assert.doesNotMatch(withoutFences(s), /^# /m);
  assert.ok(!rendered(s).includes("—"), "public page has an em dash");
});

test("editions page: the approved edition matrix, exactly", () => {
  const rows = tableRows(rendered(editions()));
  const want = [
    ["Falcon AI, Turing Models, Protect, Error Feed", "Not available", "Available"],
    ["Organization members", "Up to 3", "More than 3"],
    ["Organizations", "1", "More than 1"],
    ["Workspaces", "1", "More than 1"],
    [
      "Other products included in Community",
      "Available, no commercial usage caps",
      "Available, no commercial usage caps",
    ],
  ];
  for (const row of want) {
    assert.ok(
      rows.some((r) => JSON.stringify(r) === JSON.stringify(row)),
      `matrix row missing: ${row.join(" | ")}`,
    );
  }
  const tldr = flat(editions().match(/<TLDR>([\s\S]*?)<\/TLDR>/)?.[1] ?? "");
  assert.match(tldr, /one organization, one workspace and up to 3 members/);
  assert.match(tldr, /Falcon AI, Turing Models, Protect, Error Feed/);
});

test("editions page: no blanket billing or every-product claims", () => {
  const text = flat(rendered(editions()));
  assert.doesNotMatch(text, /every other product/i);
  assert.doesNotMatch(text, /no usage[- ]based billing|no usage billing/i);
  assert.doesNotMatch(text, /doesn't charge for them/i);
  // Optional hosted services keep contracted entitlements and need a connection.
  assert.match(text, /hosted by Future AGI[^.]*(entitlements|credits)/i);
  assert.match(text, /hosted by Future AGI[^.]*\.[^.]*connection/i);
});

test("editions page: sales@futureagi.com is the only contact", () => {
  const text = rendered(editions());
  const emails = new Set(text.match(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g) ?? []);
  assert.deepEqual([...emails], ["sales@futureagi.com"]);
  const mailtos = text.match(/mailto:[^)"\s]+/g) ?? [];
  assert.ok(mailtos.length > 0);
  for (const m of mailtos) assert.equal(m, "mailto:sales@futureagi.com");
});

test("editions page: expiry scopes in-flight work and keeps data", () => {
  const text = flat(rendered(editions()));
  assert.doesNotMatch(text, /A job that's already running finishes/);
  assert.doesNotMatch(text, /(every|all) (running )?jobs? (finish|complete)/i);
  assert.match(text, /already running[^.]*may finish/i);
  assert.match(text, /next[^.]*(refused|refuses)/i);
  // Removal is qualified: the four products also need a usable license.
  assert.doesNotMatch(text, /only new organizations, workspaces and members are blocked/i);
  assert.match(text, /Falcon AI, Turing Models, Protect and Error Feed[^.]*usable license/);
  assert.doesNotMatch(text, /stay visible/i);
});

test("editions page: license limitations stated without a waiver", () => {
  const text = flat(rendered(editions()));
  assert.match(text, /doesn't tie a license to one install/);
  assert.match(text, /revok/);
  assert.doesNotMatch(text, /\b(approved|waive[sd]?|waiver)\b/i);
});

test("editions page: activation commands are scoped and keep keys off the command line", () => {
  const s = editions();
  const text = rendered(s);
  // Production overlay uses its own env file and both compose files.
  assert.match(
    flat(text),
    /docker compose --env-file deploy\/\.env\.production \\? ?-f docker-compose\.distributed\.yml -f deploy\/docker-compose\.production\.yml up -d/,
  );
  // The public key goes in the root .env even with the overlay.
  assert.match(flat(text), /EE_LICENSE_PUBLIC_KEY[^.]*root `\.env`/);
  // Helm restarts only this release's backend and workers.
  assert.match(text, /-l app\.kubernetes\.io\/instance=futureagi/);
  assert.match(text, /futureagi-\(backend\|worker\)/);
  assert.doesNotMatch(text, /grep worker/);
  // No license value on a command line, no real-looking key material.
  assert.doesNotMatch(text, /--from-literal=EE_LICENSE_KEY/);
  assert.doesNotMatch(text, /eyJ[A-Za-z0-9_-]{10,}/);
  assert.doesNotMatch(text, /MII[A-Za-z0-9+/]{16,}/);
  for (const m of text.matchAll(/EE_LICENSE_KEY=(\S+)/g)) {
    assert.match(m[1], /^(YOUR_LICENSE_KEY|license\.jwt|\.\/license\.jwt)$/, `unexpected key value ${m[1]}`);
  }
});

test("editions page: hidden markers only for unfinished implementation details", () => {
  const s = editions();
  assert.doesNotMatch(rendered(s), /To be confirmed|\bTBC\b/);
  for (const c of comments(s)) {
    assert.doesNotMatch(c, /multi-line PEM|Deployment names|migration step|DRAFT/i, `resolved marker left: ${c.trim()}`);
  }
});

test("editions page: every internal link and anchor resolves", () => {
  editions();
  assertLinksResolve(EDITIONS);
});

test("nav: Self-Hosting lists the editions page after Container images", () => {
  const nav = read("src/lib/navigation.ts");
  const start = nav.indexOf("title: 'Self-Hosting'");
  const end = nav.indexOf("title: 'Release notes'", start);
  assert.ok(start > 0 && end > start);
  const group = nav.slice(start, end);
  const entry = "{ title: 'Community & Enterprise', href: '/docs/self-hosting/editions' }";
  assert.ok(group.includes(entry), "nav entry missing from Self-Hosting");
  assert.ok(group.indexOf("/docs/self-hosting/images") < group.indexOf(entry));
  assert.equal(nav.split("/docs/self-hosting/editions'").length - 1, 1, "nav entry duplicated");
});

test("users page: members join by invitation on Community", () => {
  const s = read(USERS);
  const text = flat(rendered(s));
  assert.doesNotMatch(text, /Anyone who can reach the instance can create an account/);
  const tldr = flat(s.match(/<TLDR>([\s\S]*?)<\/TLDR>/)?.[1] ?? "");
  assert.doesNotMatch(tldr, /sign-up in the UI/i);
  assert.match(tldr, /invite/i);
  assert.match(text, /On Community[^.]*(second|another)[^.]*refused/);
  assert.match(text, /\]\(\/docs\/self-hosting\/editions\)/);
  assertLinksResolve(USERS);
});

test("helm and support pages point to the editions page", () => {
  const helm = read("src/pages/docs/self-hosting/helm.mdx");
  assert.match(helm, /^- \*\*Enterprise\.\*\*[^\n]*\]\(\/docs\/self-hosting\/editions\)/m);
  const support = flat(read("src/pages/docs/self-hosting/support.mdx"));
  assert.match(support, /## Commercial support[^#]*license[^#]*sales@futureagi\.com/i);
  assert.match(support, /## Commercial support[^#]*\/docs\/self-hosting\/editions/);
});
