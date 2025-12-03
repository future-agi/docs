#!/usr/bin/env python3
"""
Fix relative image references in MDX files by:
1. Finding all images referenced with ./
2. Finding those images in the source docs
3. Copying them to public/images/docs/
4. Updating the references to absolute paths
"""

import os
import re
import shutil
from pathlib import Path

SOURCE_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/futureagi-docs-source")
DOCS_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")
PUBLIC_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/public")

# Path mapping from destination MDX to source directory
PATH_MAP = {
    "observe/voice/quickstart.mdx": "future-agi/products/observe/voice",
    "observe/voice/index.mdx": "future-agi/products/observe/voice",
    "agent-compass/index.mdx": "future-agi/products/agent-compass",
    "agent-compass/quickstart.mdx": "future-agi/products/agent-compass",
    "prompt/create.mdx": "products/prompt/how-to",
    "prompt/templates.mdx": "products/prompt/how-to",
    "cookbook/observability.mdx": "cookbook/cookbook8",
    "cookbook/mongodb.mdx": "cookbook/integrations",
    "cookbook/llamaindex-pdf-rag.mdx": "cookbook/cookbook14",
    "cookbook/decrease-hallucination.mdx": "cookbook/cookbook9",
    "cookbook/rag-langchain.mdx": "cookbook/cookbook5",
    "cookbook/portkey-integration.mdx": "cookbook/cookbook11",
    "cookbook/meeting-summarization.mdx": "cookbook/cookbook1",
    "cookbook/crewai-research-team.mdx": "cookbook/cookbook16",
}

def find_relative_images(content):
    """Find all relative image references like ![...](./image.png) or ![...](./images/image.png)"""
    pattern = r'!\[([^\]]*)\]\(\./([^)]+)\)'
    return re.findall(pattern, content)

def fix_mdx_file(mdx_file):
    """Fix relative image references in a single MDX file."""
    rel_path = str(mdx_file.relative_to(DOCS_DIR))

    with open(mdx_file, 'r', encoding='utf-8') as f:
        content = f.read()

    images = find_relative_images(content)
    if not images:
        return 0

    # Try to find the source directory
    source_subdir = PATH_MAP.get(rel_path)
    if not source_subdir:
        print(f"  [WARN] No mapping for {rel_path}, images may not be found")
        return 0

    source_dir = SOURCE_DIR / source_subdir

    # Create target directory in public
    target_subdir = rel_path.replace('/', '-').replace('.mdx', '')
    target_base = PUBLIC_DIR / "images" / "docs" / target_subdir

    copied = 0
    original_content = content

    for alt, image_path in images:
        source_image = source_dir / image_path
        if source_image.exists():
            # Handle nested paths like ./images/image.png
            image_name = Path(image_path).name  # Just the filename
            target_dir = target_base
            target_dir.mkdir(parents=True, exist_ok=True)
            target_image = target_dir / image_name

            shutil.copy2(source_image, target_image)

            # Update reference in content
            old_ref = f"![{alt}](./{image_path})"
            new_ref = f"![{alt}](/images/docs/{target_subdir}/{image_name})"
            content = content.replace(old_ref, new_ref)
            copied += 1
            print(f"    Copied: {image_path} -> {image_name}")
        else:
            print(f"    [NOT FOUND] {source_image}")

    if content != original_content:
        with open(mdx_file, 'w', encoding='utf-8') as f:
            f.write(content)

    return copied

def main():
    print("=== Fixing Relative Image References ===\n")

    total_copied = 0
    files_fixed = 0

    for mdx_file in sorted(DOCS_DIR.rglob("*.mdx")):
        rel = mdx_file.relative_to(DOCS_DIR)

        with open(mdx_file, 'r', encoding='utf-8') as f:
            content = f.read()

        if './' in content and '![' in content:
            images = find_relative_images(content)
            if images:
                print(f"  Processing: {rel} ({len(images)} images)")
                copied = fix_mdx_file(mdx_file)
                if copied > 0:
                    files_fixed += 1
                    total_copied += copied

    print(f"\n=== Complete ===")
    print(f"Files fixed: {files_fixed}")
    print(f"Images copied: {total_copied}")

if __name__ == '__main__':
    main()
