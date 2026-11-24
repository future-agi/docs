# Released SDK reference

The stable reference must describe packages that readers can install. The
backend contract/catalog in SDK `dev` is not a substitute for a released SDK,
even when its manifest still contains the same version strings.

## Normal synchronization

`sdk-reference-release.mjs` selects the latest release across both package tag
streams. A `released` request becomes ready only when the selected SDK commit
matches a tag for one of the manifest's package versions and **both** versions
exist in their registries. An untagged commit with published version strings
stays a candidate draft. Independent Python-only and TypeScript-only releases
remain supported only when the other package's Git tree is identical to its own
release tag; unversioned source changes cannot hide behind an installable version.

`sync-sdk-reference.mjs --from <sdk checkout>` copies the SDK-generated pages
and navigation. It also records the immutable SDK commit, package versions and
backend pin in `src/lib/sdk-reference-source.json`. That provenance file travels
in the same update as the pages; it is not edited by hand.

## First-release bootstrap

Python 0.7.0 and TypeScript 0.2.0 were published from
`e61149de72c9907abd0921371126e4d40eb3e04a`, before the docs emitter existed.
That release contains **162** platform methods. The later `dev` reference added
methods that these packages do not contain, so copying it would be incorrect.

For this one historical commit, `bootstrap-sdk-reference.py` runs the reviewed
emitter at `3269d584fc668f959d8c125cf9acb33d3c36d1fb` with **only the released
commit's contract and catalog**. Before rendering, it checks both immutable
checkout heads and verifies that these inputs regenerate the exact released
Python and TypeScript operation files. Neither API inputs nor generated clients
are copied from the emitter's newer checkout. Other releases must carry their
own generated reference; they do not silently fall back to `dev`.

The sync workflow contains this same pinned bootstrap, so scheduled recovery
also works before the next SDK release. It can be reproduced in a disposable
cloud environment:

```sh
python -m pip install PyYAML==6.0.2
python -I scripts/bootstrap-sdk-reference.py --sdk /path/to/released-sdk --renderer /path/to/pinned-emitter
node scripts/sync-sdk-reference.mjs --from /path/to/released-sdk
```

## Verification

- Run the resolver and PR-lifecycle tests, including an untagged commit that
  retains published version strings, an independent package release, and failed
  GitHub lookups.
- Check every Python example against the **installed published wheel**, and
  compile every TypeScript example against the **installed published npm package**.
- Build the site, audit its links and exercise all reference pages at phone width.
- Run generation twice and compare output to catch accidental input drift.

Merging the docs receiver does not deploy the sender. The SDK's docs-dispatch
changes still need their own reviewed promotion to SDK `main`; package
publication is separate from this docs change.
