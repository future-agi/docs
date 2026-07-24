#!/usr/bin/env node
// Transforms a GitHub Release body (release-please format) into a section for
// src/pages/docs/release-notes.mdx — matching that page's existing convention
// (## heading + styled wrapper div + "Features" / "Bugs/Improvements"
// subsections) — and inserts it below the marker, on top of existing entries.
// Usage:
//   node scripts/changelog-from-release.mjs <version> <bodyFile> <releaseNotesFile>
import { readFileSync, writeFileSync } from "node:fs";

const MARKER = "{/* release-notes:insert-below — automation inserts new releases here; do not remove */}";

// Must stay in lockstep with the visible changelog-sections in
// future-agi/future-agi release-please-config.json — a visible section missing
// here is silently dropped from the release-notes page.
// Maps release-please section -> release-notes subsection (several merge into
// the page's existing "Bugs/Improvements" bucket).
const SECTION_MAP = new Map([
  ["Features", "Features"],
  ["Bug Fixes", "Bugs/Improvements"],
  ["Performance Improvements", "Bugs/Improvements"],
  ["Reverts", "Bugs/Improvements"],
]);
const SUBSECTION_ORDER = ["Features", "Bugs/Improvements", "Breaking Changes"];

const WRAPPER_OPEN = '<div class="mb-12 pb-8 border-b border-[var(--color-border-subtle)] last:border-b-0">';
const subsectionHeading = (title) => `<div class="mt-6 mb-3 text-lg font-semibold">${title}</div>`;

// Escape characters that are syntactically significant in MDX ({/} for JSX
// expressions, < for JSX tags) so release-body content can't break the build.
// Applied to release-body content lines only — never to the markup this
// script generates itself.
export function escapeMdx(text) {
  return text
    .replace(/</g, "&lt;")
    .replace(/\{/g, "&#123;")
    .replace(/\}/g, "&#125;");
}

export function transform(version, body, now = new Date()) {
  const date = now.toISOString().slice(0, 10);
  const buckets = new Map(SUBSECTION_ORDER.map((k) => [k, []]));
  let current = null;
  for (const line of body.split("\n")) {
    const h = line.match(/^#{2,3}\s+(.*)$/);
    if (h) {
      const title = h[1].trim();
      current = /BREAKING CHANGES/i.test(title) ? "Breaking Changes" : SECTION_MAP.get(title) ?? null;
      continue;
    }
    if (current && line.trim().startsWith("*")) {
      buckets.get(current).push(escapeMdx(line.replace(/^\s*\*/, "-")));
    }
  }
  const out = [`## ${version} (${date})`, "", WRAPPER_OPEN, ""];
  for (const title of SUBSECTION_ORDER) {
    const bullets = buckets.get(title);
    if (!bullets.length) continue;
    out.push(subsectionHeading(title), "", ...bullets.flatMap((b) => [b, ""]));
  }
  out.push("</div>", "");
  return out.join("\n");
}

export function insert(releaseNotes, section) {
  const idx = releaseNotes.indexOf(MARKER);
  if (idx === -1) throw new Error("release-notes marker not found");
  const insertAt = idx + MARKER.length;
  return releaseNotes.slice(0, insertAt) + "\n\n" + section.trimEnd() + "\n" + releaseNotes.slice(insertAt);
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop());
if (isMain && process.argv.length >= 5) {
  const [, , version, bodyFile, notesFile] = process.argv;
  const body = readFileSync(bodyFile, "utf8");
  const notes = readFileSync(notesFile, "utf8");
  writeFileSync(notesFile, insert(notes, transform(version, body)));
  console.log(`Inserted ${version} into ${notesFile}`);
}
