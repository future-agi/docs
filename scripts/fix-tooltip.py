#!/usr/bin/env python3
"""
Add Tooltip import to files that use it.
"""

import os
import re
from pathlib import Path

DOCS_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")

def get_prefix_for_file(file_path):
    """Calculate the prefix to reach src/ from a file."""
    rel_path = file_path.relative_to(DOCS_DIR)
    depth = len(rel_path.parts) - 1
    return '../' * (depth + 2)

def fix_mdx_file(file_path):
    """Add Tooltip import to a single MDX file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if '<Tooltip' not in content:
        return False

    if 'import Tooltip' in content:
        return False

    original_content = content
    prefix = get_prefix_for_file(file_path)

    # Add import after frontmatter/existing imports
    frontmatter_match = re.search(r'^---\n.*?\n---\n', content, re.DOTALL)
    if frontmatter_match:
        insert_pos = frontmatter_match.end()
        # Check if there are already imports
        import_match = re.search(r'(import\s+\w+\s+from.*?\n)+', content[insert_pos:])
        if import_match:
            insert_pos += import_match.end()

        import_stmt = f"import Tooltip from '{prefix}components/docs/Tooltip.astro';\n"
        content = content[:insert_pos] + import_stmt + content[insert_pos:]

    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    print("=== Fixing Tooltip Component ===\n")

    fixed = 0
    for mdx_file in sorted(DOCS_DIR.rglob("*.mdx")):
        if fix_mdx_file(mdx_file):
            print(f"  [FIXED] {mdx_file.relative_to(DOCS_DIR)}")
            fixed += 1

    print(f"\n=== Complete ===")
    print(f"Fixed: {fixed}")

if __name__ == '__main__':
    main()
