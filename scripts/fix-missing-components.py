#!/usr/bin/env python3
"""
Add missing component imports to MDX files.
"""

import os
import re
from pathlib import Path

DOCS_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")

# Components to check and add imports for
COMPONENTS = [
    ('Accordion', 'Accordion.astro'),
    ('ApiEndpoint', 'ApiEndpoint.astro'),
    ('Callout', 'Callout.astro'),
    ('Card', 'Card.astro'),
    ('CardGrid', 'CardGrid.astro'),
    ('CardGroup', 'CardGroup.astro'),
    ('Check', 'Check.astro'),
    ('CodeBlock', 'CodeBlock.astro'),
    ('CodeGroup', 'CodeGroup.astro'),
    ('CodePanel', 'CodePanel.astro'),
    ('CopyButton', 'CopyButton.astro'),
    ('Expandable', 'Expandable.astro'),
    ('Icon', 'Icon.astro'),
    ('Note', 'Note.astro'),
    ('ParamField', 'ParamField.astro'),
    ('Prerequisites', 'Prerequisites.astro'),
    ('ResponseField', 'ResponseField.astro'),
    ('Step', 'Step.astro'),
    ('Steps', 'Steps.astro'),
    ('Tab', 'Tab.astro'),
    ('TabPanel', 'TabPanel.astro'),
    ('Tabs', 'Tabs.astro'),
    ('Tip', 'Tip.astro'),
    ('TLDR', 'TLDR.astro'),
    ('Tooltip', 'Tooltip.astro'),
    ('Update', 'Update.astro'),
    ('Warning', 'Warning.astro'),
    ('Frame', 'Frame.astro'),
]

def get_prefix_for_file(file_path):
    """Calculate the prefix to reach src/ from a file."""
    rel_path = file_path.relative_to(DOCS_DIR)
    depth = len(rel_path.parts) - 1
    return '../' * (depth + 2)

def fix_mdx_file(file_path):
    """Add missing component imports to a single MDX file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    prefix = get_prefix_for_file(file_path)

    # Find position to insert imports
    frontmatter_match = re.search(r'^---\n.*?\n---\n', content, re.DOTALL)
    if not frontmatter_match:
        return False

    insert_pos = frontmatter_match.end()
    # Check if there are already imports and move past them
    import_match = re.search(r'(import\s+\w+\s+from.*?\n)+', content[insert_pos:])
    if import_match:
        insert_pos += import_match.end()

    imports_to_add = []

    for component, filename in COMPONENTS:
        # Check if component is used
        if f'<{component}' in content or f'<{component}>' in content:
            # Check if already imported
            if f'import {component}' not in content:
                import_stmt = f"import {component} from '{prefix}components/docs/{filename}';"
                imports_to_add.append(import_stmt)

    if imports_to_add:
        import_block = '\n'.join(imports_to_add) + '\n'
        content = content[:insert_pos] + import_block + content[insert_pos:]

    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    print("=== Fixing Missing Component Imports ===\n")

    fixed = 0
    for mdx_file in sorted(DOCS_DIR.rglob("*.mdx")):
        if fix_mdx_file(mdx_file):
            print(f"  [FIXED] {mdx_file.relative_to(DOCS_DIR)}")
            fixed += 1

    print(f"\n=== Complete ===")
    print(f"Fixed: {fixed}")

if __name__ == '__main__':
    main()
