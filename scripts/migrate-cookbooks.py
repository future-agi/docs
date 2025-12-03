#!/usr/bin/env python3
"""
Cookbook Migration Script
Migrates all cookbook MDX files from source docs to Astro format
"""

import os
import re
from pathlib import Path

# Paths
SOURCE_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/futureagi-docs-source")
DEST_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")

# Cookbook mappings
COOKBOOK_MAPPINGS = {
    "cookbook/overview.mdx": "cookbook/index.mdx",
    # Getting Started
    "cookbook/cookbook10/Using-FutureAGI-Evals.mdx": "cookbook/using-futureagi-evals.mdx",
    "cookbook/cookbook10/Using-FutureAGI-Protect.mdx": "cookbook/using-futureagi-protect.mdx",
    "cookbook/cookbook10/Using-FutureAGI-Dataset.mdx": "cookbook/using-futureagi-dataset.mdx",
    "cookbook/cookbook10/Using-FutureAGI-KB.mdx": "cookbook/using-futureagi-kb.mdx",
    # Integrations
    "cookbook/cookbook11/integrate-portkey-and-futureagi.mdx": "cookbook/portkey-integration.mdx",
    "cookbook/cookbook13/Adding-Reliability-to-Your-LangChain-LangGraph-Application-with-Future AGI.mdx": "cookbook/langchain-langgraph.mdx",
    "cookbook/cookbook14/Build-Reliable-PDF-RAG-chatbots-with-LlamaIndex-and-Future-AGI.mdx": "cookbook/llamaindex-pdf-rag.mdx",
    "cookbook/cookbook16/Building-AI-Research-Team-with-CrewAI-and-FutureAGI.mdx": "cookbook/crewai-research-team.mdx",
    "cookbook/integrations/mongodb.mdx": "cookbook/mongodb.mdx",
    # Evaluation
    "cookbook/cookbook1/AI-Evaluation-for-Meeting-Summarization.mdx": "cookbook/meeting-summarization.mdx",
    "cookbook/cookbook2/AI-Evaluation-for-AI-SDR.mdx": "cookbook/ai-sdr.mdx",
    "cookbook/cookbook3/Mastering-Evaluation-of-AI-Agents.mdx": "cookbook/ai-agents.mdx",
    # Observability
    "cookbook/cookbook8/How-To-Implement-Observability.mdx": "cookbook/observability.mdx",
    "cookbook/cookbook12/Evaluating-Text-to-SQL-Agent-using-Future-AGI.mdx": "cookbook/text-to-sql.mdx",
    # RAG
    "cookbook/cookbook5/How-to-build-and-incrementally-improve-RAG-applications-in-Langchain.mdx": "cookbook/rag-langchain.mdx",
    "cookbook/cookbook6/How-to-evaluate-RAG-Applications.mdx": "cookbook/evaluate-rag.mdx",
    "cookbook/cookbook7/Creating-Trustworthy-RAGs-for-Chatbots.mdx": "cookbook/trustworthy-rag.mdx",
    "cookbook/cookbook9/How-To-Decrease-RAG-Hallucination.mdx": "cookbook/decrease-hallucination.mdx",
    # Optimization
    "cookbook/optimization/basic-prompt-optimization.mdx": "cookbook/basic-optimization.mdx",
    "cookbook/optimization/evolutionary-optimization-with-gepa.mdx": "cookbook/gepa-optimization.mdx",
    "cookbook/optimization/eval-metrics-for-optimization.mdx": "cookbook/eval-metrics-optimization.mdx",
    "cookbook/optimization/comparing-optimization-strategies.mdx": "cookbook/compare-optimization.mdx",
    "cookbook/optimization/importing-and-using-datasets.mdx": "cookbook/import-datasets.mdx",
    # Simulate
    "cookbook/cookbook17/simulate-sdk-demo.mdx": "cookbook/simulate-sdk.mdx",
}

def get_layout_depth(dest_path):
    """Calculate the layout depth based on destination path"""
    parts = Path(dest_path).parts
    return len(parts)

def convert_mdx(content, layout_depth=2):
    """Convert Mintlify MDX to Astro-compatible MDX"""

    # Extract frontmatter
    frontmatter_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)
        body = content[frontmatter_match.end():]

        # Add layout to frontmatter if not present
        if 'layout:' not in frontmatter:
            layout_path = '../' * (layout_depth + 1) + 'layouts/DocsLayout.astro'
            frontmatter = f'layout: {layout_path}\n{frontmatter}'

        # Remove Mintlify-specific frontmatter fields
        frontmatter = re.sub(r'^icon:.*$', '', frontmatter, flags=re.MULTILINE)
        frontmatter = re.sub(r'^sidebarTitle:.*$', '', frontmatter, flags=re.MULTILINE)
        frontmatter = re.sub(r'^mode:.*$', '', frontmatter, flags=re.MULTILINE)

        # Clean up empty lines in frontmatter
        frontmatter = re.sub(r'\n{3,}', '\n\n', frontmatter)
        frontmatter = frontmatter.strip()

        content = f'---\n{frontmatter}\n---\n{body}'

    # Build import paths based on depth
    component_path = '../' * (layout_depth + 1) + 'components/docs'

    # Add component imports after frontmatter
    imports = []
    if '<CardGroup' in content or '<Card ' in content:
        imports.append(f"import CardGroup from '{component_path}/CardGroup.astro';")
        imports.append(f"import Card from '{component_path}/Card.astro';")
    if '<Accordion' in content:
        imports.append(f"import Accordion from '{component_path}/Accordion.astro';")
    if '<Tip' in content:
        imports.append(f"import Tip from '{component_path}/Tip.astro';")
    if '<Note' in content:
        imports.append(f"import Note from '{component_path}/Note.astro';")
    if '<Warning' in content:
        imports.append(f"import Warning from '{component_path}/Warning.astro';")
    if '<CodeGroup' in content:
        imports.append(f"import CodeGroup from '{component_path}/CodeGroup.astro';")
    if '<Steps' in content:
        imports.append(f"import Steps from '{component_path}/Steps.astro';")
        imports.append(f"import Step from '{component_path}/Step.astro';")

    if imports:
        import_block = '\n'.join(imports)
        content = re.sub(r'(---\n.*?\n---)', r'\1\n' + import_block + '\n', content, flags=re.DOTALL)

    # Fix internal links
    content = re.sub(r'\]\(/future-agi/', r'](/docs/', content)
    content = re.sub(r'href="/future-agi/', r'href="/docs/', content)
    content = re.sub(r'\]\(/quickstart/', r'](/docs/quickstart/', content)
    content = re.sub(r'href="/quickstart/', r'href="/docs/quickstart/', content)
    content = re.sub(r'\]\(/products/', r'](/docs/', content)
    content = re.sub(r'href="/products/', r'href="/docs/', content)
    content = re.sub(r'\]\(/cookbook/', r'](/docs/cookbook/', content)
    content = re.sub(r'href="/cookbook/', r'href="/docs/cookbook/', content)
    content = re.sub(r'\]\(/sdk-reference/', r'](/docs/sdk/', content)
    content = re.sub(r'href="/sdk-reference/', r'href="/docs/sdk/', content)
    content = re.sub(r'\]\(/admin-settings', r'](/docs/admin-settings', content)
    content = re.sub(r'href="/admin-settings', r'href="/docs/admin-settings', content)
    content = re.sub(r'\]\(/product/', r'](/docs/', content)
    content = re.sub(r'href="/product/', r'href="/docs/', content)

    # Fix external docs.futureagi.com links to internal links
    content = re.sub(r'https://docs\.futureagi\.com/future-agi/', r'/docs/', content)
    content = re.sub(r'https://docs\.futureagi\.com/', r'/docs/', content)

    return content

def migrate_file(src_path, dest_path):
    """Migrate a single MDX file"""
    src_full = SOURCE_DIR / src_path
    dest_full = DEST_DIR / dest_path

    if not src_full.exists():
        print(f"  [SKIP] Source not found: {src_path}")
        return False

    # Read source content
    with open(src_full, 'r', encoding='utf-8') as f:
        content = f.read()

    # Calculate layout depth
    depth = len(Path(dest_path).parts) - 1

    # Convert content
    converted = convert_mdx(content, depth)

    # Ensure destination directory exists
    dest_full.parent.mkdir(parents=True, exist_ok=True)

    # Write converted content
    with open(dest_full, 'w', encoding='utf-8') as f:
        f.write(converted)

    print(f"  [OK] {src_path} -> {dest_path}")
    return True

def main():
    print("=== Cookbook Migration ===\n")

    DEST_DIR.joinpath("cookbook").mkdir(parents=True, exist_ok=True)

    success = 0
    failed = 0

    for src, dest in COOKBOOK_MAPPINGS.items():
        if migrate_file(src, dest):
            success += 1
        else:
            failed += 1

    print(f"\n=== Migration Complete ===")
    print(f"Success: {success}")
    print(f"Failed/Skipped: {failed}")

if __name__ == '__main__':
    main()
