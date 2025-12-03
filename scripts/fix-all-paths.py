#!/usr/bin/env python3
"""
Fix all relative paths in MDX files based on their depth from the docs directory.
- Fixes layout paths
- Fixes component import paths

File structure:
src/pages/docs/file.mdx -> needs ../../ to reach src/
src/pages/docs/folder/file.mdx -> needs ../../../ to reach src/
src/pages/docs/folder/subfolder/file.mdx -> needs ../../../../ to reach src/
"""

import os
import re
from pathlib import Path

DOCS_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")

def get_prefix_for_file(file_path):
    """Calculate the prefix to reach src/ from a file."""
    rel_path = file_path.relative_to(DOCS_DIR)
    # Number of directories deep from docs (not counting the file)
    depth = len(rel_path.parts) - 1
    # To reach src/ from docs/file.mdx we need ../ twice (docs -> pages -> src)
    # To reach src/ from docs/folder/file.mdx we need ../ three times
    # So prefix = '../' * (depth + 2)
    return '../' * (depth + 2)

def fix_mdx_file(file_path):
    """Fix paths in a single MDX file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    prefix = get_prefix_for_file(file_path)

    # Fix layout paths in frontmatter
    # Replace any ../ pattern followed by layouts/DocsLayout.astro
    def fix_layout(match):
        return f"layout: {prefix}layouts/DocsLayout.astro"

    content = re.sub(
        r"layout:\s*(?:\.\./)+layouts/DocsLayout\.astro",
        fix_layout,
        content
    )

    # Fix component import paths
    # Replace import paths like '../components/docs/' or '../../components/docs/'
    # Pattern matches: import Foo from '../components/docs/Bar.astro'
    # or: import Foo from '../../components/docs/Bar.astro;  (without closing quote - bug from previous run)
    def fix_import(match):
        import_start = match.group(1)  # "import Foo from '"
        component_file = match.group(2)  # "Bar.astro" (without the quote)
        # Ensure we have a closing quote
        return f"{import_start}{prefix}components/docs/{component_file}'"

    # This handles both proper quotes and missing closing quotes
    content = re.sub(
        r"(import\s+\w+\s+from\s+')(?:\.\./)+components/docs/([^';\n]+)'?;?",
        fix_import,
        content
    )

    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    print("=== Fixing Relative Paths ===\n")

    fixed = 0
    skipped = 0
    errors = []

    for mdx_file in sorted(DOCS_DIR.rglob("*.mdx")):
        try:
            # Debug: show expected prefix
            prefix = get_prefix_for_file(mdx_file)
            rel = mdx_file.relative_to(DOCS_DIR)

            if fix_mdx_file(mdx_file):
                print(f"  [FIXED] {rel} -> prefix: {prefix}")
                fixed += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  [ERROR] {mdx_file.relative_to(DOCS_DIR)}: {e}")
            errors.append(str(e))

    print(f"\n=== Complete ===")
    print(f"Fixed: {fixed}")
    print(f"Unchanged: {skipped}")
    if errors:
        print(f"Errors: {len(errors)}")

if __name__ == '__main__':
    main()
