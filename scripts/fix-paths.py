#!/usr/bin/env python3
"""
Fix all relative paths in MDX files based on their depth from the docs directory.
- Fixes layout paths
- Fixes component import paths
"""

import os
import re
from pathlib import Path

DOCS_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")

def get_depth(file_path):
    """Calculate the depth of a file from DOCS_DIR."""
    rel_path = file_path.relative_to(DOCS_DIR)
    # Number of directories to traverse up to get to src/pages/docs
    return len(rel_path.parts) - 1  # -1 because the file itself counts

def fix_mdx_file(file_path):
    """Fix paths in a single MDX file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    depth = get_depth(file_path)

    # Calculate correct relative path prefix
    # From docs/file.mdx -> ../../ (to get to src/)
    # From docs/folder/file.mdx -> ../../../ (to get to src/)
    prefix = '../' * (depth + 1)  # +1 to get out of docs

    # Fix layout paths in frontmatter
    # Match layout: anything.astro and replace with correct path
    content = re.sub(
        r"(layout:\s*)['\"]?\.*/+layouts/DocsLayout\.astro['\"]?",
        f"layout: {prefix}layouts/DocsLayout.astro",
        content
    )

    # Fix component import paths
    # Match import ... from '../components/docs/...'
    content = re.sub(
        r"(import\s+\w+\s+from\s+['\"])\.*/+components/docs/",
        f"\\g<1>{prefix}components/docs/",
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

    for mdx_file in DOCS_DIR.rglob("*.mdx"):
        try:
            if fix_mdx_file(mdx_file):
                print(f"  [FIXED] {mdx_file.relative_to(DOCS_DIR)}")
                fixed += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  [ERROR] {mdx_file.relative_to(DOCS_DIR)}: {e}")

    print(f"\n=== Complete ===")
    print(f"Fixed: {fixed}")
    print(f"Unchanged: {skipped}")

if __name__ == '__main__':
    main()
