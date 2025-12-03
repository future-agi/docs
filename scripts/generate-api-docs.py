#!/usr/bin/env python3
"""
Generate API documentation pages from OpenAPI spec.
Creates MDX files with API playground for each endpoint.
"""

import json
import os
import re
from pathlib import Path

# Paths
OPENAPI_PATH = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/data/openapi.json")
API_DOCS_DIR = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/pages/docs/api")

def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')

def get_method_color(method: str) -> str:
    """Get color class for HTTP method."""
    colors = {
        'get': 'emerald',
        'post': 'blue',
        'put': 'amber',
        'delete': 'red',
        'patch': 'purple',
    }
    return colors.get(method.lower(), 'gray')

def format_schema_for_display(schema: dict, indent: int = 0) -> str:
    """Format a JSON schema for display."""
    if not schema:
        return ""

    lines = []
    prefix = "  " * indent

    if schema.get('type') == 'object':
        props = schema.get('properties', {})
        required = schema.get('required', [])
        for name, prop in props.items():
            req_mark = " (required)" if name in required else ""
            prop_type = prop.get('type', 'any')
            desc = prop.get('description', '')
            example = prop.get('example', '')

            if prop_type == 'object':
                lines.append(f"{prefix}- **{name}**{req_mark}: object")
                if desc:
                    lines.append(f"{prefix}  {desc}")
                lines.append(format_schema_for_display(prop, indent + 1))
            elif prop_type == 'array':
                item_type = prop.get('items', {}).get('type', 'any')
                lines.append(f"{prefix}- **{name}**{req_mark}: array of {item_type}")
                if desc:
                    lines.append(f"{prefix}  {desc}")
            else:
                enum_vals = prop.get('enum', [])
                if enum_vals:
                    lines.append(f"{prefix}- **{name}**{req_mark}: {prop_type} (one of: {', '.join(map(str, enum_vals))})")
                else:
                    lines.append(f"{prefix}- **{name}**{req_mark}: {prop_type}")
                if desc:
                    lines.append(f"{prefix}  {desc}")
                if example:
                    lines.append(f"{prefix}  Example: `{example}`")

    return "\n".join(lines)

def generate_example_body(schema: dict) -> dict:
    """Generate an example request body from schema."""
    if not schema:
        return {}

    example = {}
    props = schema.get('properties', {})

    for name, prop in props.items():
        if 'example' in prop:
            example[name] = prop['example']
        elif prop.get('type') == 'string':
            if 'enum' in prop:
                example[name] = prop['enum'][0]
            else:
                example[name] = f"your-{name}"
        elif prop.get('type') == 'integer':
            example[name] = 1
        elif prop.get('type') == 'boolean':
            example[name] = True
        elif prop.get('type') == 'array':
            example[name] = []
        elif prop.get('type') == 'object':
            example[name] = generate_example_body(prop)

    return example

def generate_endpoint_page(path: str, method: str, operation: dict, tag: str) -> str:
    """Generate MDX content for an endpoint."""
    summary = operation.get('summary', 'API Endpoint')
    description = operation.get('description', '')
    operation_id = operation.get('operationId', '')

    # Parse parameters
    parameters = operation.get('parameters', [])
    path_params = [p for p in parameters if p.get('in') == 'path']
    query_params = [p for p in parameters if p.get('in') == 'query']

    # Parse request body
    request_body = operation.get('requestBody', {})
    body_schema = None
    if request_body:
        content = request_body.get('content', {})
        json_content = content.get('application/json', {})
        body_schema = json_content.get('schema', {})

    # Parse responses
    responses = operation.get('responses', {})

    # Generate example body
    example_body = generate_example_body(body_schema) if body_schema else None

    # Build parameters JSON for playground
    params_json = []
    for p in path_params:
        params_json.append({
            'name': p.get('name'),
            'in': 'path',
            'required': p.get('required', False),
            'description': p.get('description', ''),
            'type': p.get('schema', {}).get('type', 'string')
        })
    for p in query_params:
        params_json.append({
            'name': p.get('name'),
            'in': 'query',
            'required': p.get('required', False),
            'description': p.get('description', ''),
            'type': p.get('schema', {}).get('type', 'string')
        })

    # Generate MDX content
    mdx = f'''---
layout: ../../../../layouts/DocsLayout.astro
title: "{summary}"
description: "{description[:150]}{'...' if len(description) > 150 else ''}"
---
import ApiPlayground from '../../../../components/docs/ApiPlayground.astro';
import Callout from '../../../../components/docs/Callout.astro';

# {summary}

{description}

<ApiPlayground
  method="{method.upper()}"
  endpoint="{path}"
  baseUrl="https://api.futureagi.com"
  parameters={{{json.dumps(params_json)}}}
  {f'requestBody={{{json.dumps(example_body)}}}' if example_body else ''}
/>

'''

    # Add authentication section
    security = operation.get('security', [])
    if security:
        mdx += '''
## Authentication

This endpoint requires authentication. Include your API key in the Authorization header:

```bash
Authorization: Bearer YOUR_API_KEY
```

'''

    # Add parameters section
    if path_params or query_params:
        mdx += "## Parameters\n\n"

        if path_params:
            mdx += "### Path Parameters\n\n"
            mdx += "| Parameter | Type | Required | Description |\n"
            mdx += "|-----------|------|----------|-------------|\n"
            for p in path_params:
                name = p.get('name', '')
                ptype = p.get('schema', {}).get('type', 'string')
                required = 'Yes' if p.get('required') else 'No'
                desc = p.get('description', '')
                mdx += f"| `{name}` | {ptype} | {required} | {desc} |\n"
            mdx += "\n"

        if query_params:
            mdx += "### Query Parameters\n\n"
            mdx += "| Parameter | Type | Required | Description |\n"
            mdx += "|-----------|------|----------|-------------|\n"
            for p in query_params:
                name = p.get('name', '')
                ptype = p.get('schema', {}).get('type', 'string')
                required = 'Yes' if p.get('required') else 'No'
                desc = p.get('description', '')
                mdx += f"| `{name}` | {ptype} | {required} | {desc} |\n"
            mdx += "\n"

    # Add request body section
    if body_schema:
        mdx += "## Request Body\n\n"
        mdx += format_schema_for_display(body_schema)
        mdx += "\n\n"

        if example_body:
            mdx += "### Example\n\n"
            mdx += "```json\n"
            mdx += json.dumps(example_body, indent=2)
            mdx += "\n```\n\n"

    # Add responses section
    if responses:
        mdx += "## Responses\n\n"
        for status, response in responses.items():
            desc = response.get('description', '')
            mdx += f"### {status}\n\n{desc}\n\n"

            content = response.get('content', {})
            json_content = content.get('application/json', {})
            resp_schema = json_content.get('schema', {})
            examples = json_content.get('examples', {})

            if examples:
                for ex_name, ex_value in examples.items():
                    mdx += f"```json\n{json.dumps(ex_value.get('value', {}), indent=2)}\n```\n\n"
            elif resp_schema:
                mdx += format_schema_for_display(resp_schema)
                mdx += "\n\n"

    # Add code examples
    mdx += "## Code Examples\n\n"

    # cURL example
    curl_cmd = f'curl -X {method.upper()} "https://api.futureagi.com{path}"'
    curl_cmd += ' \\\n  -H "Authorization: Bearer YOUR_API_KEY"'
    curl_cmd += ' \\\n  -H "Content-Type: application/json"'
    if example_body:
        curl_cmd += f" \\\n  -d '{json.dumps(example_body)}'"

    mdx += f'''### cURL

```bash
{curl_cmd}
```

'''

    # Python example
    python_code = f'''import requests

url = "https://api.futureagi.com{path}"
headers = {{
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}}
'''
    if example_body:
        python_code += f'''data = {json.dumps(example_body, indent=4)}

response = requests.{method.lower()}(url, headers=headers, json=data)
'''
    else:
        python_code += f'''
response = requests.{method.lower()}(url, headers=headers)
'''
    python_code += "print(response.json())"

    mdx += f'''### Python

```python
{python_code}
```

'''

    # JavaScript example
    js_code = f'''const response = await fetch("https://api.futureagi.com{path}", {{
  method: "{method.upper()}",
  headers: {{
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
  }},'''
    if example_body:
        js_code += f'''
  body: JSON.stringify({json.dumps(example_body, indent=4)})'''
    js_code += '''
});

const data = await response.json();
console.log(data);'''

    mdx += f'''### JavaScript

```javascript
{js_code}
```

'''

    return mdx

def main():
    print("=== Generating API Documentation ===\n")

    # Load OpenAPI spec
    with open(OPENAPI_PATH, 'r') as f:
        spec = json.load(f)

    # Create API docs directory
    API_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Group endpoints by tag
    tags = {t['name']: t for t in spec.get('tags', [])}
    endpoints_by_tag = {tag: [] for tag in tags}

    for path, methods in spec.get('paths', {}).items():
        for method, operation in methods.items():
            if method.lower() not in ['get', 'post', 'put', 'delete', 'patch']:
                continue

            op_tags = operation.get('tags', ['Other'])
            for tag in op_tags:
                if tag not in endpoints_by_tag:
                    endpoints_by_tag[tag] = []
                endpoints_by_tag[tag].append((path, method, operation))

    # Generate navigation structure
    nav_items = []

    # Create a directory for each tag
    for tag, endpoints in endpoints_by_tag.items():
        if not endpoints:
            continue

        tag_slug = slugify(tag)
        tag_dir = API_DOCS_DIR / tag_slug
        tag_dir.mkdir(exist_ok=True)

        tag_nav = {
            'title': tag,
            'items': []
        }

        for path, method, operation in endpoints:
            summary = operation.get('summary', 'Endpoint')
            operation_id = operation.get('operationId', slugify(summary))
            endpoint_slug = slugify(operation_id or summary)

            # Generate the page
            content = generate_endpoint_page(path, method, operation, tag)

            # Write the file
            file_path = tag_dir / f"{endpoint_slug}.mdx"
            with open(file_path, 'w') as f:
                f.write(content)

            print(f"  Created: {file_path.relative_to(API_DOCS_DIR.parent.parent.parent)}")

            tag_nav['items'].append({
                'title': summary,
                'href': f"/docs/api/{tag_slug}/{endpoint_slug}",
                'method': method.upper()
            })

        nav_items.append(tag_nav)

    # Generate navigation TypeScript file
    nav_ts = '''/**
 * Auto-generated API navigation from OpenAPI spec
 */

export interface ApiNavItem {
  title: string;
  href: string;
  method: string;
}

export interface ApiNavGroup {
  title: string;
  items: ApiNavItem[];
}

export const apiNavigation: ApiNavGroup[] = '''
    nav_ts += json.dumps(nav_items, indent=2) + ';\n'

    nav_file = Path("/Users/nikhilpareek/Documents/futureAGI/code/landing-page/src/lib/api-navigation.ts")
    with open(nav_file, 'w') as f:
        f.write(nav_ts)

    print(f"\n  Created navigation: {nav_file}")

    # Create index page
    index_content = '''---
layout: ../../../layouts/DocsLayout.astro
title: API Reference
description: Complete REST API reference for the Future AGI platform.
---
import Card from '../../../components/docs/Card.astro';
import CardGroup from '../../../components/docs/CardGroup.astro';
import Callout from '../../../components/docs/Callout.astro';

# API Reference

The Future AGI REST API provides programmatic access to all platform features including simulations, evaluations, datasets, and more.

## Base URL

```
https://api.futureagi.com
```

## Authentication

All API endpoints require authentication using an API key. Include your API key in the `Authorization` header:

```bash
Authorization: Bearer YOUR_API_KEY
```

<Callout type="info">
Get your API key from the [Future AGI Dashboard](https://app.futureagi.com/settings/api-keys).
</Callout>

## API Categories

<CardGroup cols={2}>
'''

    for tag, info in tags.items():
        tag_slug = slugify(tag)
        description = info.get('description', '')
        index_content += f'''  <Card title="{tag}" href="/docs/api/{tag_slug}" icon="code">
    {description}
  </Card>
'''

    index_content += '''</CardGroup>

## Rate Limits

- **Standard tier**: 100 requests per minute
- **Pro tier**: 1000 requests per minute
- **Enterprise**: Custom limits

Rate limit headers are included in all responses:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1699900000
```

## Error Handling

All errors return a consistent JSON structure:

```json
{
  "error": {
    "code": "error_code",
    "message": "Human readable error message",
    "details": {}
  }
}
```

### Common Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Invalid or missing API key |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error |
'''

    with open(API_DOCS_DIR / 'index.mdx', 'w') as f:
        f.write(index_content)

    print(f"  Updated: API index page")
    print(f"\n=== Complete ===")
    print(f"Generated {sum(len(e) for e in endpoints_by_tag.values())} endpoint pages")

if __name__ == '__main__':
    main()
