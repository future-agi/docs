#!/usr/bin/env python3
"""
MDX Migration Script
Converts Mintlify MDX files to Astro-compatible format
"""

import re
import os
import sys
from pathlib import Path

def get_layout_path(depth):
    """Generate the correct relative path to DocsLayout based on folder depth"""
    return '../' * (depth + 1) + 'layouts/DocsLayout.astro'

def convert_mdx(content, layout_depth=2):
    """Convert Mintlify MDX to Astro-compatible MDX"""

    # Extract frontmatter
    frontmatter_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)
        body = content[frontmatter_match.end():]

        # Add layout to frontmatter if not present
        if 'layout:' not in frontmatter:
            layout_path = get_layout_path(layout_depth)
            frontmatter = f'layout: {layout_path}\n{frontmatter}'

        # Remove Mintlify-specific frontmatter fields
        frontmatter = re.sub(r'^icon:.*$', '', frontmatter, flags=re.MULTILINE)
        frontmatter = re.sub(r'^sidebarTitle:.*$', '', frontmatter, flags=re.MULTILINE)
        frontmatter = re.sub(r'^mode:.*$', '', frontmatter, flags=re.MULTILINE)

        # Clean up empty lines in frontmatter
        frontmatter = re.sub(r'\n{3,}', '\n\n', frontmatter)
        frontmatter = frontmatter.strip()

        content = f'---\n{frontmatter}\n---\n{body}'

    # Add component imports after frontmatter
    imports = []

    # Check which components are used and add imports
    if '<CardGroup' in content or '<Card ' in content:
        imports.append("import CardGroup from '../../components/docs/CardGroup.astro';")
        imports.append("import Card from '../../components/docs/Card.astro';")
    if '<Accordion' in content:
        imports.append("import Accordion from '../../components/docs/Accordion.astro';")
    if '<Tip' in content:
        imports.append("import Tip from '../../components/docs/Tip.astro';")
    if '<Note' in content:
        imports.append("import Note from '../../components/docs/Note.astro';")
    if '<Warning' in content:
        imports.append("import Warning from '../../components/docs/Warning.astro';")
    if '<CodeGroup' in content:
        imports.append("import CodeGroup from '../../components/docs/CodeGroup.astro';")
    if '<Steps' in content:
        imports.append("import Steps from '../../components/docs/Steps.astro';")
        imports.append("import Step from '../../components/docs/Step.astro';")
    if '<Tabs' in content:
        imports.append("import Tabs from '../../components/docs/Tabs.astro';")
        imports.append("import TabPanel from '../../components/docs/TabPanel.astro';")

    if imports:
        # Insert imports after frontmatter
        import_block = '\n'.join(imports)
        content = re.sub(r'(---\n.*?\n---)', r'\1\n' + import_block + '\n', content, flags=re.DOTALL)

    # Fix image paths (remove leading /images and add proper path)
    content = re.sub(r'!\[(.*?)\]\(/images/', r'![\1](/images/', content)

    # Fix internal links - convert Mintlify paths to Astro paths
    # /future-agi/... -> /docs/...
    content = re.sub(r'\]\(/future-agi/', r'](/docs/', content)
    content = re.sub(r'href="/future-agi/', r'href="/docs/', content)

    # /quickstart/... -> /docs/quickstart/...
    content = re.sub(r'\]\(/quickstart/', r'](/docs/quickstart/', content)
    content = re.sub(r'href="/quickstart/', r'href="/docs/quickstart/', content)

    # /products/... -> /docs/...
    content = re.sub(r'\]\(/products/', r'](/docs/', content)
    content = re.sub(r'href="/products/', r'href="/docs/', content)

    # /cookbook/... -> /docs/cookbook/...
    content = re.sub(r'\]\(/cookbook/', r'](/docs/cookbook/', content)
    content = re.sub(r'href="/cookbook/', r'href="/docs/cookbook/', content)

    # /sdk-reference/... -> /docs/sdk/...
    content = re.sub(r'\]\(/sdk-reference/', r'](/docs/sdk/', content)
    content = re.sub(r'href="/sdk-reference/', r'href="/docs/sdk/', content)

    # /admin-settings -> /docs/admin-settings
    content = re.sub(r'\]\(/admin-settings', r'](/docs/admin-settings', content)
    content = re.sub(r'href="/admin-settings', r'href="/docs/admin-settings', content)

    return content

def process_file(src_path, dest_path, layout_depth=2):
    """Process a single MDX file"""
    with open(src_path, 'r', encoding='utf-8') as f:
        content = f.read()

    converted = convert_mdx(content, layout_depth)

    # Ensure destination directory exists
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    with open(dest_path, 'w', encoding='utf-8') as f:
        f.write(converted)

    print(f"Converted: {src_path} -> {dest_path}")

def main():
    if len(sys.argv) < 3:
        print("Usage: migrate-mdx.py <source_file> <dest_file> [layout_depth]")
        sys.exit(1)

    src = sys.argv[1]
    dest = sys.argv[2]
    depth = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    process_file(src, dest, depth)

if __name__ == '__main__':
    main()
