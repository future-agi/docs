#!/usr/bin/env python3
"""
Batch MDX Migration Script
Migrates all MDX files from source docs to Astro format
"""

import os
import re
import shutil
from pathlib import Path

# Paths
SOURCE_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/futureagi-docs-source")
DEST_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")

# Mapping from source paths to destination paths
PATH_MAPPINGS = {
    # Get Started / Quickstart
    "quickstart/setup-observability.mdx": "quickstart/observability.mdx",
    "quickstart/generate-synthetic-data.mdx": "quickstart/synthetic-data.mdx",
    "quickstart/setup-mcp-server.mdx": "quickstart/mcp-server.mdx",

    # Dataset
    "product/dataset/overview.mdx": "dataset/index.mdx",
    "product/dataset/quickstart.mdx": "dataset/quickstart.mdx",
    "product/dataset/how-to/create-new-dataset.mdx": "dataset/create.mdx",
    "product/dataset/how-to/add-rows-to-dataset.mdx": "dataset/add-rows.mdx",
    "product/dataset/how-to/run-prompt-in-dataset.mdx": "dataset/run-prompt.mdx",
    "product/dataset/how-to/experiments-in-dataset.mdx": "dataset/experiments.mdx",
    "product/dataset/how-to/annotate-dataset.mdx": "dataset/annotate.mdx",

    # Simulation
    "product/simulation/overview.mdx": "simulation/index.mdx",
    "product/simulation/agent-definition.mdx": "simulation/agent-definition.mdx",
    "product/simulation/scenarios.mdx": "simulation/scenarios.mdx",
    "product/simulation/personas.mdx": "simulation/personas.mdx",
    "product/simulation/run-tests.mdx": "simulation/run-tests.mdx",
    "product/simulation/how-to/evaluate-tool-calling.mdx": "simulation/tool-calling.mdx",
    "product/simulation/how-to/voice-observability.mdx": "simulation/voice.mdx",

    # Evaluation
    "future-agi/get-started/evaluation/create-custom-evals.mdx": "evaluation/custom.mdx",
    "future-agi/get-started/evaluation/eval-groups.mdx": "evaluation/groups.mdx",
    "future-agi/get-started/evaluation/use-custom-models.mdx": "evaluation/custom-models.mdx",
    "future-agi/get-started/evaluation/future-agi-models.mdx": "evaluation/futureagi-models.mdx",
    "future-agi/get-started/evaluation/evaluate-ci-cd-pipeline.mdx": "evaluation/cicd.mdx",
    "future-agi/get-started/evaluation/builtin-evals/overview.mdx": "evaluation/builtin/index.mdx",

    # Prompt
    "products/prompt/overview.mdx": "prompt/index.mdx",
    "products/prompt/how-to/create-prompt-from-scratch.mdx": "prompt/create.mdx",
    "products/prompt/how-to/create-prompt-from-existing-template.mdx": "prompt/templates.mdx",
    "products/prompt/how-to/prompt-workbench-using-sdk.mdx": "prompt/sdk.mdx",
    "products/prompt/how-to/linked-traces.mdx": "prompt/linked-traces.mdx",
    "products/prompt/how-to/manage-folders.mdx": "prompt/folders.mdx",

    # Prototype
    "future-agi/get-started/prototype/overview.mdx": "prototype/index.mdx",
    "future-agi/get-started/prototype/quickstart.mdx": "prototype/quickstart.mdx",
    "future-agi/get-started/prototype/evals.mdx": "prototype/evals.mdx",
    "future-agi/get-started/prototype/winner.mdx": "prototype/winner.mdx",

    # Observe
    "future-agi/products/observe/overview.mdx": "observe/index.mdx",
    "future-agi/products/observe/quickstart.mdx": "observe/quickstart.mdx",
    "future-agi/products/observe/evals.mdx": "observe/evals.mdx",
    "future-agi/products/observe/session.mdx": "observe/session.mdx",
    "future-agi/products/observe/users.mdx": "observe/users.mdx",
    "future-agi/products/observe/alerts-and-monitors.mdx": "observe/alerts.mdx",
    "future-agi/products/observe/voice/overview.mdx": "observe/voice/index.mdx",
    "future-agi/products/observe/voice/quickstart.mdx": "observe/voice/quickstart.mdx",

    # Tracing
    "future-agi/products/observability/overview.mdx": "tracing/index.mdx",
    "future-agi/products/observability/concept/overview.mdx": "tracing/concepts.mdx",
    "future-agi/products/observability/concept/core-components.mdx": "tracing/components.mdx",
    "future-agi/products/observability/concept/spans.mdx": "tracing/spans.mdx",
    "future-agi/products/observability/concept/traces.mdx": "tracing/traces.mdx",
    "future-agi/products/observability/concept/otel.mdx": "tracing/otel.mdx",
    "future-agi/products/observability/concept/traceai.mdx": "tracing/traceai.mdx",
    "future-agi/products/observability/auto-instrumentation/overview.mdx": "tracing/auto.mdx",

    # Agent Compass
    "future-agi/products/agent-compass/overview.mdx": "agent-compass/index.mdx",
    "future-agi/products/agent-compass/quickstart.mdx": "agent-compass/quickstart.mdx",
    "future-agi/products/agent-compass/taxonomy.mdx": "agent-compass/taxonomy.mdx",

    # Optimization
    "future-agi/get-started/optimization/overview.mdx": "optimization/index.mdx",
    "future-agi/get-started/optimization/quickstart.mdx": "optimization/quickstart.mdx",
    "future-agi/get-started/optimization/optimizers/overview.mdx": "optimization/overview.mdx",
    "future-agi/get-started/optimization/optimizers/bayesian-search.mdx": "optimization/bayesian.mdx",
    "future-agi/get-started/optimization/optimizers/meta-prompt.mdx": "optimization/meta-prompt.mdx",
    "future-agi/get-started/optimization/optimizers/protegi.mdx": "optimization/protegi.mdx",
    "future-agi/get-started/optimization/optimizers/promptwizard.mdx": "optimization/promptwizard.mdx",
    "future-agi/get-started/optimization/optimizers/gepa.mdx": "optimization/gepa.mdx",
    "future-agi/get-started/optimization/optimizers/random-search.mdx": "optimization/random-search.mdx",

    # Protect
    "future-agi/get-started/protect/overview.mdx": "protect/index.mdx",
    "future-agi/get-started/protect/concept.mdx": "protect/concept.mdx",
    "future-agi/get-started/protect/how-to.mdx": "protect/how-to.mdx",

    # Knowledge Base
    "future-agi/get-started/knowledge-base/overview.mdx": "knowledge-base/index.mdx",
    "future-agi/get-started/knowledge-base/concept.mdx": "knowledge-base/concept.mdx",
    "future-agi/get-started/knowledge-base/how-to/create-kb-using-sdk.mdx": "knowledge-base/sdk.mdx",
    "future-agi/get-started/knowledge-base/how-to/create-kb-using-ui.mdx": "knowledge-base/ui.mdx",

    # Resources
    "admin-settings.mdx": "admin-settings.mdx",
    "faq.mdx": "faq.mdx",

    # SDK Reference
    "sdk-reference/python-sdk-client.mdx": "sdk/index.mdx",
    "sdk-reference/evals.mdx": "sdk/evals.mdx",
    "sdk-reference/datasets.mdx": "sdk/datasets.mdx",
    "sdk-reference/protect.mdx": "sdk/protect.mdx",
    "sdk-reference/knowledgebase.mdx": "sdk/knowledgebase.mdx",
    "sdk-reference/tracing.mdx": "sdk/tracing.mdx",
    "sdk-reference/testcase.mdx": "sdk/testcase.mdx",
}

# Integration mappings
INTEGRATION_FILES = [
    "anthropic", "autogen", "bedrock", "crewai", "dspy", "google_adk",
    "google_genai", "groq", "guardrails", "haystack", "instructor",
    "langchain", "langgraph", "litellm", "livekit", "llamaindex",
    "llamaindex-workflows", "mistralai", "mongodb", "n8n", "ollama",
    "openai", "openai_agents", "pipecat", "portkey", "promptflow",
    "smol_agents", "togetherai", "vercel", "vertexai"
]

# Built-in eval mappings
BUILTIN_EVALS = [
    "answer-refusal", "audio-quality", "audio-transcription", "bias-detection",
    "bleu", "caption-hallucination", "chunk-attribution", "chunk-utilization",
    "clinically-inappropriate-tone", "completeness", "content-moderation",
    "content-safety-violation", "context-adherence", "context-relevance",
    "conversation-coherence", "conversation-resolution", "cultural-sensitivity",
    "data-privacy", "detect-hallucination", "embedding-similarity", "eval-ranking",
    "factual-accuracy", "fuzzy-match", "groundedness", "instruction-adherence",
    "is-compliant", "is-concise", "is-email", "is-factually-consistent",
    "is-good-summary", "is-harmful-advice", "is-helpful", "is-informal-tone",
    "is-json", "is-polite", "lavenshtein-similarity", "length-evals",
    "llm-function-calling", "no-age-bias", "no-apologies", "no-gender-bias",
    "no-harmful-therapeutic-guidance", "no-llm-reference", "no-racial-bias",
    "numeric-similarity", "pii", "prompt-injection", "recall-score", "rouge",
    "semantic-list-contains", "sexist", "summary-quality",
    "synthetic-image-evaluator", "task-completion", "text-to-sql", "tone",
    "toxicity", "translation-accuracy", "contains-valid-link", "no-invalid-links"
]

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
    print("=== Batch MDX Migration ===\n")

    # Migrate mapped files
    print("Migrating core documentation...")
    success = 0
    failed = 0

    for src, dest in PATH_MAPPINGS.items():
        if migrate_file(src, dest):
            success += 1
        else:
            failed += 1

    # Add integrations
    print("\nMigrating integrations...")
    DEST_DIR.joinpath("integrations").mkdir(parents=True, exist_ok=True)

    # Integration overview
    if migrate_file("future-agi/integrations/overview.mdx", "integrations/index.mdx"):
        success += 1
    else:
        failed += 1

    for integration in INTEGRATION_FILES:
        src = f"future-agi/integrations/{integration}.mdx"
        # Normalize filename (replace underscores with hyphens)
        dest_name = integration.replace("_", "-")
        dest = f"integrations/{dest_name}.mdx"
        if migrate_file(src, dest):
            success += 1
        else:
            failed += 1

    # Add built-in evals
    print("\nMigrating built-in evaluators...")
    DEST_DIR.joinpath("evaluation/builtin").mkdir(parents=True, exist_ok=True)

    for eval_name in BUILTIN_EVALS:
        src = f"future-agi/get-started/evaluation/builtin-evals/{eval_name}.mdx"
        dest = f"evaluation/builtin/{eval_name}.mdx"
        if migrate_file(src, dest):
            success += 1
        else:
            failed += 1

    print(f"\n=== Migration Complete ===")
    print(f"Success: {success}")
    print(f"Failed/Skipped: {failed}")

if __name__ == '__main__':
    main()
