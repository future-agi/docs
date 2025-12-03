#!/usr/bin/env python3
"""
Fix stray --- delimiters that appear after import statements.
MDX should only have 2 --- (opening and closing frontmatter).
"""

import os
import re
from pathlib import Path

DOCS_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")

def fix_mdx_file(file_path):
    """Fix stray --- delimiters in a single MDX file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # Match frontmatter and any following content
    # Find the frontmatter section (between first two ---)
    frontmatter_match = re.match(r'^(---\n.*?\n---)\n', content, re.DOTALL)
    if not frontmatter_match:
        return False

    frontmatter = frontmatter_match.group(1)
    rest = content[frontmatter_match.end():]

    # Remove any standalone --- lines right after imports
    # This pattern: imports followed by --- on its own line
    rest = re.sub(r'^((?:import\s+.*?\n)+)---\n', r'\1', rest)

    # Also remove --- that appears at the end of an import line block
    # or between import sections
    lines = rest.split('\n')
    new_lines = []
    i = 0
    in_import_section = True

    while i < len(lines):
        line = lines[i]

        # Check if we're past the import section
        if in_import_section and not line.startswith('import ') and line.strip() != '' and line.strip() != '---':
            in_import_section = False

        # Skip stray --- that appear in or right after import section
        if line.strip() == '---' and (in_import_section or (i > 0 and (lines[i-1].startswith('import ') or lines[i-1].strip() == ''))):
            # Check if next non-empty line is content (not frontmatter)
            next_content = False
            for j in range(i+1, len(lines)):
                if lines[j].strip():
                    if not lines[j].strip().startswith('---'):
                        next_content = True
                    break
            if next_content:
                i += 1
                continue

        new_lines.append(line)
        i += 1

    rest = '\n'.join(new_lines)
    new_content = frontmatter + '\n' + rest

    if new_content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

def main():
    print("=== Fixing Stray Delimiters ===\n")

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
