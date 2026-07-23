#!/usr/bin/env node
// Transforms a GitHub Release body (release-please format) into a changelog.mdx
// section and inserts it below the marker. Usage:
//   node scripts/changelog-from-release.mjs <version> <bodyFile> <changelogFile>
import { readFileSync, writeFileSync } from "node:fs";

const MARKER = "{/* changelog:insert-below — automation inserts new releases here; do not remove */}";

// Escape characters that are syntactically significant in MDX ({/} for JSX
// expressions, < for JSX tags) so release-body content can't break the build.
export function escapeMdx(text) {
  return text
    .replace(/</g, "&lt;")
    .replace(/\{/g, "&#123;")
    .replace(/\}/g, "&#125;");
}

// Must stay in lockstep with the visible changelog-sections in future-agi/future-agi release-please-config.json — a visible section missing here is silently dropped from the docs page.
const SECTION_MAP = new Map([
  ["Features", "New Features"],
  ["Bug Fixes", "Bug Fixes"],
  ["Performance Improvements", "Improvements"],
  ["Reverts", "Reverts"],
]);

export function transform(version, body, now = new Date()) {
  const month = now.toLocaleString("en-US", { month: "long", year: "numeric" });
  const lines = body.split("\n");
  const out = [`## ${version} - ${month}`, ""];
  let currentMapped = null;
  let breaking = [];
  let inBreaking = false;
  for (const line of lines) {
    const h = line.match(/^#{2,3}\s+(.*)$/);
    if (h) {
      const title = h[1].trim();
      if (/BREAKING CHANGES/i.test(title)) { inBreaking = true; currentMapped = null; continue; }
      inBreaking = false;
      currentMapped = SECTION_MAP.get(title) ?? null;
      if (currentMapped) out.push(`### ${currentMapped}`, "");
      continue;
    }
    if (inBreaking && line.trim().startsWith("*")) breaking.push(escapeMdx(line.replace(/^\s*\*/, "-")));
    else if (currentMapped && line.trim().startsWith("*")) out.push(escapeMdx(line.replace(/^\s*\*/, "-")));
    else if (currentMapped && line.trim() === "") {
      if (out[out.length - 1] !== "") out.push("");
    }
  }
  if (breaking.length) out.push("### Breaking Changes", "", ...breaking, "");
  if (out[out.length - 1] !== "") out.push("");
  out.push("---", "");
  return out.join("\n");
}

export function insert(changelog, section) {
  const idx = changelog.indexOf(MARKER);
  if (idx === -1) throw new Error("changelog marker not found");
  const insertAt = idx + MARKER.length;
  return changelog.slice(0, insertAt) + "\n\n" + section.trimEnd() + "\n" + changelog.slice(insertAt);
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop());
if (isMain && process.argv.length >= 5) {
  const [, , version, bodyFile, changelogFile] = process.argv;
  const body = readFileSync(bodyFile, "utf8");
  const changelog = readFileSync(changelogFile, "utf8");
  writeFileSync(changelogFile, insert(changelog, transform(version, body)));
  console.log(`Inserted ${version} into ${changelogFile}`);
}
