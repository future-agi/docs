#!/usr/bin/env python3
"""
Fix MDX structure issues:
1. Ensure blank line between imports and content
2. Remove stray --- delimiters
3. Ensure imports are only at the top after frontmatter
"""

import os
import re
from pathlib import Path

DOCS_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")

def fix_mdx_file(file_path):
    """Fix MDX structure in a single file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # Extract frontmatter
    frontmatter_match = re.match(r'^(---\n.*?\n---)\n', content, re.DOTALL)
    if not frontmatter_match:
        return False

    frontmatter = frontmatter_match.group(1)
    rest = content[frontmatter_match.end():]

    # Split into lines
    lines = rest.split('\n')

    # Separate imports from content
    import_lines = []
    content_lines = []
    in_imports = True

    for line in lines:
        stripped = line.strip()
        if in_imports:
            if stripped.startswith('import '):
                import_lines.append(line)
            elif stripped == '' and not content_lines:
                # Skip empty lines at the start
                continue
            elif stripped == '---':
                # Skip stray ---
                continue
            else:
                in_imports = False
                content_lines.append(line)
        else:
            # After imports, remove any standalone --- at the start of content
            if stripped == '---' and not content_lines:
                continue
            content_lines.append(line)

    # Reconstruct the file
    parts = [frontmatter]

    if import_lines:
        parts.append('\n'.join(import_lines))
        parts.append('')  # Blank line after imports

    if content_lines:
        # Remove leading empty lines from content
        while content_lines and content_lines[0].strip() == '':
            content_lines.pop(0)
        parts.append('\n'.join(content_lines))

    new_content = '\n'.join(parts)

    # Clean up multiple blank lines
    new_content = re.sub(r'\n{4,}', '\n\n\n', new_content)

    if new_content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

def main():
    print("=== Fixing MDX Structure ===\n")

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
