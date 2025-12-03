#!/usr/bin/env python3
"""
Fix duplicate imports and scattered imports in migrated MDX files.
Also fixes component references that don't exist (AccordionGroup -> div, Info -> Tip).
"""

import os
import re
from pathlib import Path

DOCS_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")

# Components that need to be imported
COMPONENT_MAP = {
    'CardGroup': 'CardGroup.astro',
    'Card': 'Card.astro',
    'Accordion': 'Accordion.astro',
    'Tip': 'Tip.astro',
    'Note': 'Note.astro',
    'Warning': 'Warning.astro',
    'CodeGroup': 'CodeGroup.astro',
    'Steps': 'Steps.astro',
    'Step': 'Step.astro',
    'Tabs': 'Tabs.astro',
    'Tab': 'Tab.astro',
    'Frame': 'Frame.astro',
    'Update': 'Update.astro',
}

def get_component_path(file_path):
    """Calculate the relative path to components/docs based on file depth."""
    rel_path = file_path.relative_to(DOCS_DIR)
    depth = len(rel_path.parts) - 1  # -1 for the file itself
    return '../' * (depth + 1) + 'components/docs'

def fix_mdx_file(file_path):
    """Fix imports and component references in a single MDX file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # Extract frontmatter
    frontmatter_match = re.match(r'^(---\n.*?\n---)\n', content, re.DOTALL)
    if not frontmatter_match:
        return False

    frontmatter = frontmatter_match.group(1)
    body = content[frontmatter_match.end():]

    # Remove ALL existing import statements from the body
    body = re.sub(r'^import\s+\w+\s+from\s+[\'"].*?[\'"];?\s*\n?', '', body, flags=re.MULTILINE)

    # Fix AccordionGroup -> use regular div or remove wrapper
    body = re.sub(r'<AccordionGroup>', '<div class="accordion-group">', body)
    body = re.sub(r'</AccordionGroup>', '</div>', body)

    # Fix Info -> Tip (Info is Mintlify's alias for Tip)
    body = re.sub(r'<Info>', '<Tip>', body)
    body = re.sub(r'</Info>', '</Tip>', body)
    body = re.sub(r'<Info\s+', '<Tip ', body)

    # Detect which components are actually used in the body
    used_components = set()
    for comp in COMPONENT_MAP.keys():
        if f'<{comp}' in body or f'<{comp}>' in body:
            used_components.add(comp)

    # Also check if Tip was added via Info replacement
    if '<Tip' in body:
        used_components.add('Tip')

    # Build import statements
    component_path = get_component_path(file_path)
    imports = []
    for comp in sorted(used_components):
        if comp in COMPONENT_MAP:
            imports.append(f"import {comp} from '{component_path}/{COMPONENT_MAP[comp]}';")

    # Reconstruct the file
    if imports:
        import_block = '\n'.join(imports)
        new_content = f"{frontmatter}\n{import_block}\n{body}"
    else:
        new_content = f"{frontmatter}\n{body}"

    # Clean up multiple blank lines
    new_content = re.sub(r'\n{4,}', '\n\n\n', new_content)

    if new_content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

def main():
    print("=== Fixing MDX Imports ===\n")

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
