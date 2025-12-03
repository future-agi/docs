#!/usr/bin/env python3
"""
Fix LaTeX math blocks in MDX files that use curly braces,
which conflict with JSX expression parsing.
Replace $$ blocks with plain text equivalents.
"""

import os
import re
from pathlib import Path

DOCS_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs")

def remove_latex_blocks(content):
    """Remove or simplify LaTeX $$ blocks."""
    # Pattern to match $$ ... $$ blocks (multiline)
    pattern = r'\$\$\s*(.*?)\s*\$\$'

    def replace_latex(match):
        latex = match.group(1).strip()

        # Common LaTeX to plain text conversions
        # These are approximations - adjust as needed

        # Handle \text{...} - extract the text
        latex = re.sub(r'\\text\{([^}]*)\}', r'\1', latex)

        # Handle \frac{a}{b} -> a/b
        latex = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1)/(\2)', latex)

        # Handle \sqrt{...} -> √(...)
        latex = re.sub(r'\\sqrt\{([^}]*)\}', r'√(\1)', latex)

        # Handle \sum_{i=1}^{n} -> Σ
        latex = re.sub(r'\\sum_\{[^}]*\}\^\{[^}]*\}', 'Σ', latex)
        latex = re.sub(r'\\sum', 'Σ', latex)

        # Handle \mathbf{...} -> bold markers
        latex = re.sub(r'\\mathbf\{([^}]*)\}', r'**\1**', latex)

        # Handle subscripts _{...}
        latex = re.sub(r'_\{([^}]*)\}', r'_\1', latex)
        latex = re.sub(r'_(\w)', r'_\1', latex)

        # Handle superscripts ^{...}
        latex = re.sub(r'\^\{([^}]*)\}', r'^(\1)', latex)

        # Handle \cdot -> ×
        latex = re.sub(r'\\cdot', '×', latex)

        # Handle \ldots -> ...
        latex = re.sub(r'\\ldots', '...', latex)

        # Handle \exp -> exp
        latex = re.sub(r'\\exp', 'exp', latex)

        # Handle \log -> log
        latex = re.sub(r'\\log', 'log', latex)

        # Handle \left( and \right)
        latex = re.sub(r'\\left\(', '(', latex)
        latex = re.sub(r'\\right\)', ')', latex)
        latex = re.sub(r'\\left\[', '[', latex)
        latex = re.sub(r'\\right\]', ']', latex)

        # Handle \| -> ||
        latex = re.sub(r'\\\|', '||', latex)

        # Handle |...| for absolute value
        # Keep as is

        # Handle \geq, \leq
        latex = re.sub(r'\\geq', '≥', latex)
        latex = re.sub(r'\\leq', '≤', latex)

        # Handle \times
        latex = re.sub(r'\\times', '×', latex)

        # Handle \in
        latex = re.sub(r'\\in', '∈', latex)

        # Handle remaining backslash commands
        latex = re.sub(r'\\[a-zA-Z]+', '', latex)

        # Remove any remaining curly braces
        latex = latex.replace('{', '').replace('}', '')

        # Clean up whitespace
        latex = ' '.join(latex.split())

        if latex.strip():
            return f'**{latex.strip()}**'
        return ''

    return re.sub(pattern, replace_latex, content, flags=re.DOTALL)

def fix_mdx_file(file_path):
    """Fix LaTeX in a single MDX file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if file has LaTeX
    if '$$' not in content:
        return False

    original_content = content
    content = remove_latex_blocks(content)

    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    print("=== Fixing LaTeX Blocks ===\n")

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
