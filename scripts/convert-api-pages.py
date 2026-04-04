#!/usr/bin/env python3
"""
Convert old-format API MDX pages to the new Fern-style component-based format.

Old format: markdown headings, bullet-point params, code examples sections
New format: <ApiSection>, <ParamField>, <ResponseField> components

Skips: index.mdx, createevalgroup.mdx (already converted)
"""

import os
import re
import json
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent / "src" / "pages" / "docs" / "api"

# Files to skip
SKIP_FILES = {
    "index.mdx",
    "createevalgroup.mdx",
}

# HTTP status code to status text mapping
STATUS_TEXT = {
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    500: "Internal Server Error",
}


def find_mdx_files(api_dir: Path):
    """Find all MDX files recursively, excluding SKIP_FILES."""
    files = []
    for f in sorted(api_dir.rglob("*.mdx")):
        if f.name in SKIP_FILES:
            continue
        files.append(f)
    return files


def parse_frontmatter(content: str):
    """Extract frontmatter and body from MDX content."""
    match = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    if not match:
        return {}, content
    fm_text = match.group(1)
    body = match.group(2)
    fm = {}
    for line in fm_text.split("\n"):
        m = re.match(r'^(\w+):\s*"?(.*?)"?\s*$', line)
        if m:
            fm[m.group(1)] = m.group(2)
    return fm, body


def extract_api_playground(body: str):
    """Extract the <ApiPlayground ... /> block and return it + remaining body."""
    # Match the full ApiPlayground block (may span many lines)
    pattern = r"<ApiPlayground\b.*?/>"
    match = re.search(pattern, body, re.DOTALL)
    if not match:
        return None, body
    playground = match.group(0)
    remaining = body[:match.start()] + body[match.end():]
    return playground, remaining


def extract_playground_props(playground: str):
    """Parse key props from the ApiPlayground tag."""
    props = {}
    # method
    m = re.search(r'method="(\w+)"', playground)
    if m:
        props["method"] = m.group(1)
    # endpoint
    m = re.search(r'endpoint="([^"]+)"', playground)
    if m:
        props["endpoint"] = m.group(1)
    # baseUrl
    m = re.search(r'baseUrl="([^"]+)"', playground)
    if m:
        props["baseUrl"] = m.group(1)
    # Check if has requestBody
    props["has_request_body"] = "requestBody=" in playground
    # Check if has parameters
    m = re.search(r'parameters=\{(\[.*?\])\}', playground, re.DOTALL)
    if m:
        props["parameters_raw"] = m.group(1)
    # Check if already has responseExample
    props["has_response_example"] = "responseExample=" in playground
    return props


def parse_parameters_from_playground(params_raw: str):
    """Parse parameters array from ApiPlayground parameters prop."""
    params = []
    if not params_raw or params_raw.strip() == "[]":
        return params
    # Match individual objects in the array
    obj_pattern = r'\{([^}]+)\}'
    for m in re.finditer(obj_pattern, params_raw, re.DOTALL):
        obj_str = m.group(1)
        param = {}
        # name
        nm = re.search(r'name:\s*"([^"]+)"', obj_str) or re.search(r'"name":\s*"([^"]+)"', obj_str)
        if nm:
            param["name"] = nm.group(1)
        # type
        tp = re.search(r'type:\s*"([^"]+)"', obj_str) or re.search(r'"type":\s*"([^"]+)"', obj_str)
        if tp:
            param["type"] = tp.group(1)
        # in
        loc = re.search(r'in:\s*"([^"]+)"', obj_str) or re.search(r'"in":\s*"([^"]+)"', obj_str)
        if loc:
            param["in"] = loc.group(1)
        # required
        req = re.search(r'required:\s*(true|false)', obj_str) or re.search(r'"required":\s*(true|false)', obj_str)
        if req:
            param["required"] = req.group(1) == "true"
        else:
            param["required"] = False
        # description
        desc = re.search(r'description:\s*"([^"]*)"', obj_str) or re.search(r'"description":\s*"([^"]*)"', obj_str)
        if desc:
            param["description"] = desc.group(1)
        if param.get("name"):
            params.append(param)
    return params


def remove_heading(body: str, frontmatter: dict):
    """Remove the duplicate # Title heading that matches frontmatter title."""
    title = frontmatter.get("title", "")
    # Remove # Title and the description paragraph after it
    lines = body.split("\n")
    new_lines = []
    skip_next_blank = False
    i = 0
    while i < len(lines):
        line = lines[i]
        # Match # Title heading
        if re.match(r'^#\s+', line) and not re.match(r'^##', line):
            heading_text = re.sub(r'^#\s+', '', line).strip()
            # Skip this heading line
            i += 1
            # Skip blank lines after heading
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            # Check if the next paragraph repeats the description
            desc = frontmatter.get("description", "")
            if i < len(lines) and desc:
                # Collect the paragraph
                para_lines = []
                while i < len(lines) and lines[i].strip() != "":
                    para_lines.append(lines[i])
                    i += 1
                para = " ".join(l.strip() for l in para_lines)
                # If para is similar to description, skip it
                if para.strip().rstrip(".") == desc.strip().rstrip(".") or \
                   para.strip() == desc.strip() or \
                   len(para) > 10 and para.strip()[:50] == desc.strip()[:50]:
                    # Skip the paragraph - already consumed
                    pass
                else:
                    # Keep the paragraph
                    new_lines.extend(para_lines)
            continue
        new_lines.append(line)
        i += 1
    return "\n".join(new_lines)


def find_response_json(body: str):
    """Find JSON code blocks in the Responses section (for 200/201/202)."""
    # Look for ```json blocks after ### 200/201/202
    response_json = None
    response_status = None
    response_status_text = None

    # Find ### 2xx headings and their json blocks
    pattern = r'###\s+(2\d{2})\b.*?\n(.*?)(?=###\s+\d{3}|##\s+|$)'
    for m in re.finditer(pattern, body, re.DOTALL):
        status = int(m.group(1))
        section = m.group(2)
        json_match = re.search(r'```json\s*\n(.*?)\n```', section, re.DOTALL)
        if json_match:
            response_json = json_match.group(1).strip()
            response_status = status
            response_status_text = STATUS_TEXT.get(status, "OK")
            break
        # Even without JSON, record the status
        if response_status is None:
            response_status = status
            response_status_text = STATUS_TEXT.get(status, "OK")

    return response_json, response_status, response_status_text


def find_response_fields_from_section(body: str):
    """Extract response field info from ### 2xx sections."""
    fields = []
    pattern = r'###\s+(2\d{2})\b.*?\n(.*?)(?=###\s+\d{3}|##\s+|$)'
    for m in re.finditer(pattern, body, re.DOTALL):
        status = int(m.group(1))
        section = m.group(2)
        # Parse bullet-point fields: - **name**: type\n  Description
        field_pattern = r'-\s+\*\*(\w+)\*\*(?:\s*\((\w+)\))?\s*:\s*(\S+(?:\s+of\s+\S+)?)\s*\n?\s*(.*?)(?=\n-\s+\*\*|\n###|\n##|$)'
        for fm in re.finditer(field_pattern, section, re.DOTALL):
            name = fm.group(1)
            req = fm.group(2)
            ftype = fm.group(3).strip()
            desc = fm.group(4).strip()
            # Clean up description - remove Example: lines
            desc = re.sub(r'Example:.*$', '', desc, flags=re.MULTILINE).strip()
            fields.append({
                "name": name,
                "type": ftype,
                "description": desc,
                "required": req == "required" if req else False,
                "status": status,
            })
        # Also parse table-format response fields
        table_pattern = r'\|\s*`?(\w+)`?\s*\|\s*(\w+)\s*\|\s*(.*?)\s*\|'
        for tm in re.finditer(table_pattern, section):
            name = tm.group(1)
            if name.lower() in ("field", "parameter", "---", "-----"):
                continue
            ftype = tm.group(2)
            desc = tm.group(3).strip()
            fields.append({
                "name": name,
                "type": ftype,
                "description": desc,
                "required": False,
                "status": status,
            })
        break  # Only first 2xx
    return fields


def find_error_codes(body: str):
    """Extract error response codes from ### 4xx/5xx sections."""
    errors = []
    # Find the ## Responses section
    responses_match = re.search(r'##\s+Responses?\s*\n(.*?)(?=##\s+(?!#)|$)', body, re.DOTALL)
    if not responses_match:
        return errors
    responses_section = responses_match.group(1)

    # Find ### 4xx and ### 5xx headings
    error_pattern = r'###\s+([45]\d{2})\s*\n\s*(.*?)(?=###\s+\d{3}|$)'
    for m in re.finditer(error_pattern, responses_section, re.DOTALL):
        code = int(m.group(1))
        desc = m.group(2).strip()
        # Take just the first line/paragraph as description
        desc_lines = []
        for line in desc.split("\n"):
            if line.strip() == "" or line.strip().startswith("-") or line.strip().startswith("|"):
                break
            desc_lines.append(line.strip())
        desc_text = " ".join(desc_lines).strip()
        if not desc_text:
            desc_text = STATUS_TEXT.get(code, "Error")
        errors.append({
            "code": code,
            "description": desc_text,
            "status_text": STATUS_TEXT.get(code, "Error"),
        })
    return errors


def parse_request_body_bullets(body: str):
    """Parse request body parameters from bullet-point format."""
    params = []
    # Find ## Request Body section
    rb_match = re.search(r'##\s+Request\s+Body\s*\n(.*?)(?=##\s+(?!#)|$)', body, re.DOTALL)
    if not rb_match:
        return params
    rb_section = rb_match.group(1)

    # Remove ### Example and subsequent JSON block
    rb_section = re.sub(r'###\s+Example\s*\n```json\s*\n.*?\n```', '', rb_section, flags=re.DOTALL)

    # Check if it already has <ParamField> components - skip bullet parsing
    if "<ParamField" in rb_section:
        return "ALREADY_COMPONENTS"

    # Check if it's a table format
    if re.search(r'\|\s*Field\s*\|', rb_section) or re.search(r'\|\s*`\w+`\s*\|', rb_section):
        return parse_request_body_table(rb_section)

    # Parse bullet format: - **name** (required): type\n  Description
    # Also handle: - **name**: type (one of: x, y)\n  Description
    bullet_pattern = r'-\s+\*\*(\w[\w.]*)\*\*\s*(?:\((\w+)\))?\s*:\s*(.*?)\n((?:\s+[^\-#\n].*\n?)*)'
    for m in re.finditer(bullet_pattern, rb_section):
        name = m.group(1)
        req_flag = m.group(2)
        type_str = m.group(3).strip()
        desc = m.group(4).strip()

        # Parse type - might have "(one of: x, y)" or just "string"
        enum_match = re.match(r'(\w+(?:\s+of\s+\w+)?)\s*\(one\s+of:\s*(.*?)\)', type_str)
        if enum_match:
            ptype = enum_match.group(1)
            enum_vals = enum_match.group(2)
        else:
            ptype = type_str
            enum_vals = None

        required = req_flag == "required" if req_flag else False

        params.append({
            "name": name,
            "type": ptype,
            "required": required,
            "description": desc,
            "enum": enum_vals,
        })

    return params


def parse_request_body_table(section: str):
    """Parse request body from table format."""
    params = []
    # Match table rows: | `name` | type | Yes/No | description |
    row_pattern = r'\|\s*`?(\w[\w.\[\]]*)`?\s*\|\s*([\w\s/]+?)\s*\|\s*(Yes|No|Conditional)?\s*\|?\s*(.*?)\s*\|'
    for m in re.finditer(row_pattern, section):
        name = m.group(1)
        if name.lower() in ("field", "parameter", "---", "-----", "type"):
            continue
        ptype = m.group(2).strip()
        req_text = m.group(3)
        desc = m.group(4).strip() if m.group(4) else ""

        required = req_text == "Yes" if req_text else False

        params.append({
            "name": name,
            "type": ptype,
            "required": required,
            "description": desc,
        })
    return params


def parse_path_params_table(body: str):
    """Parse path parameters from table format."""
    params = []
    # Find ## Path Parameters or ### Path Parameters section
    pp_match = re.search(r'(?:##|###)\s+Path\s+Parameters?\s*\n(.*?)(?=##\s+(?!#)|###\s+(?!Path)|$)', body, re.DOTALL)
    if not pp_match:
        return params
    pp_section = pp_match.group(1)

    row_pattern = r'\|\s*`?(\w+)`?\s*\|\s*(\w+)\s*\|\s*(Yes|No)\s*\|\s*(.*?)\s*\|'
    for m in re.finditer(row_pattern, pp_section):
        name = m.group(1)
        if name.lower() in ("parameter", "---", "-----"):
            continue
        ptype = m.group(2).strip()
        required = m.group(3) == "Yes"
        desc = m.group(4).strip()
        params.append({
            "name": name,
            "type": ptype,
            "required": required,
            "description": desc,
        })
    return params


def parse_query_params_table(body: str):
    """Parse query parameters from table format."""
    params = []
    # Find ## Query Parameters or ### Query Parameters or ## Parameters section with table
    qp_match = re.search(r'(?:##|###)\s+(?:Query\s+)?Parameters?\s*\n(.*?)(?=##\s+Request|##\s+Response|##\s+Code|$)', body, re.DOTALL)
    if not qp_match:
        return params

    qp_section = qp_match.group(1)

    # If there's a ### Query Parameters subsection, use that
    sub_match = re.search(r'###\s+Query\s+Parameters?\s*\n(.*?)(?=###|##|$)', qp_section, re.DOTALL)
    if sub_match:
        qp_section = sub_match.group(1)

    row_pattern = r'\|\s*`?(\w+)`?\s*\|\s*(\w+)\s*\|\s*(Yes|No)\s*\|\s*(.*?)\s*\|'
    for m in re.finditer(row_pattern, qp_section):
        name = m.group(1)
        if name.lower() in ("parameter", "---", "-----"):
            continue
        ptype = m.group(2).strip()
        required = m.group(3) == "Yes"
        desc = m.group(4).strip()
        params.append({
            "name": name,
            "type": ptype,
            "required": required,
            "description": desc,
        })
    return params


def detect_auth_type(body: str):
    """Detect whether authentication is Bearer token or X-Api-Key style."""
    if "X-Api-Key" in body or "X-Secret-Key" in body:
        return "apikey"
    return "bearer"


def build_auth_section(auth_type: str):
    """Build the authentication ApiSection."""
    if auth_type == "apikey":
        return """<ApiSection title="Authentication">
  <ParamField name="X-Api-Key" type="API Key" required>
    Include your API key in the `X-Api-Key` header. Retrieve your API Key from the [Dashboard](https://app.futureagi.com).
  </ParamField>
  <ParamField name="X-Secret-Key" type="Secret Key" required>
    Include your secret key in the `X-Secret-Key` header.
  </ParamField>
</ApiSection>"""
    else:
        return """<ApiSection title="Authentication">
  <ParamField name="Authorization" type="Bearer" required>
    Include your API key in the `Authorization` header as `Bearer <token>`. Retrieve your API Key from the [Dashboard](https://app.futureagi.com).
  </ParamField>
</ApiSection>"""


def build_param_field(name: str, ptype: str, required: bool, description: str,
                      location: str = "body", enum_vals: str = None,
                      indent: int = 1):
    """Build a single <ParamField> component string."""
    req_str = "required" if required else "optional"
    loc_attr = f'{location}="{name}"' if location in ("body", "query", "path") else f'name="{name}"'

    extra = ""
    if enum_vals:
        # enum must be a JSX array expression, not a string
        vals = [v.strip() for v in enum_vals.split(",")]
        vals_str = ", ".join(f'"{v}"' for v in vals)
        extra += ' enum={[' + vals_str + ']}'

    desc_clean = description.strip()
    if not desc_clean:
        desc_clean = f"The {name} parameter."

    prefix = "  " * indent
    return f'{prefix}<ParamField {loc_attr} type="{ptype}" {req_str}{extra}>\n{prefix}  {desc_clean}\n{prefix}</ParamField>'


def build_param_tree(params):
    """Build a tree structure from flat params with dotted/bracket names.

    Params like 'records[].observation_span_id' are grouped as children
    of the 'records' param, enabling nested rendering with ApiCollapsible.
    """
    import re as _re

    tree = []
    children_map = {}  # parent_name -> [child_params]

    for p in params:
        name = p["name"]
        # Normalise bracket notation: records[].foo -> records.foo
        norm = _re.sub(r'\[\]', '', name)
        if "." in norm:
            parent, child_name = norm.split(".", 1)
            if parent not in children_map:
                children_map[parent] = []
            child_p = dict(p)
            child_p["name"] = child_name
            children_map[parent].append(child_p)
        else:
            tree.append(dict(p))

    # Attach children to their parent nodes
    for p in tree:
        name = p["name"]
        if name in children_map:
            p["children"] = children_map[name]
            # Upgrade type: array -> array of objects when it has children
            ptype = p.get("type", "")
            if ptype.lower().startswith("array") and "object" not in ptype.lower():
                p["type"] = "array of objects"

    # Recurse: children may themselves have nested children
    for p in tree:
        if "children" in p:
            p["children"] = build_param_tree(p["children"])

    return tree


def build_nested_param_fields(params, location="body", indent=1):
    """Render a param tree as nested <ParamField> + <ApiCollapsible> components."""
    tree = build_param_tree(params)
    return _render_param_tree(tree, location, indent)


def _render_param_tree(tree, location, indent):
    """Recursively render a param tree."""
    lines = []
    prefix = "  " * indent

    for p in tree:
        lines.append(build_param_field(
            p["name"], p.get("type", "string"), p.get("required", False),
            p.get("description", ""), location=location,
            enum_vals=p.get("enum"), indent=indent,
        ))

        if "children" in p:
            children = p["children"]
            count = len(children)
            word = "property" if count == 1 else "properties"
            lines.append(f'{prefix}<ApiCollapsible title="Show {count} {word}">')
            child_lines = _render_param_tree(children, location, indent + 1)
            lines.extend(child_lines)
            lines.append(f'{prefix}</ApiCollapsible>')

    return lines


def build_response_field(name: str, rtype: str, description: str, required: bool = False):
    """Build a single <ResponseField> component string."""
    req_str = " required" if required else ""
    desc_clean = description.strip()
    if not desc_clean:
        desc_clean = f"The {name} field."
    return f'  <ResponseField name="{name}" type="{rtype}"{req_str}>\n    {desc_clean}\n  </ResponseField>'


def update_playground_with_response(playground: str, response_json: str,
                                     response_status: int, response_status_text: str):
    """Add responseExample, responseStatus, responseStatusText to ApiPlayground."""
    if not response_json:
        return playground

    # Check if already has these props
    if "responseExample=" in playground:
        return playground

    # Find the closing /> and insert before it
    # Build the new props
    new_props = f'\n  responseExample={{{response_json}}}\n  responseStatus={{{response_status}}}\n  responseStatusText="{response_status_text}"'

    # Insert before the closing />
    playground = playground.rstrip()
    if playground.endswith("/>"):
        playground = playground[:-2].rstrip() + new_props + "\n/>"
    return playground


def has_existing_param_fields_in_request(body: str):
    """Check if the Request Body section already uses <ParamField> components."""
    rb_match = re.search(r'##\s+Request\s+Body\s*\n(.*?)(?=##\s+(?!#)|$)', body, re.DOTALL)
    if not rb_match:
        return False
    return "<ParamField" in rb_match.group(1)


def has_existing_response_fields(body: str):
    """Check if the Response section already uses <ResponseField> components."""
    resp_match = re.search(r'##\s+Responses?\s*\n(.*?)(?=##\s+Code|##\s+$|$)', body, re.DOTALL)
    if not resp_match:
        return False
    return "<ResponseField" in resp_match.group(1)


def extract_existing_components_section(body: str, section_name: str):
    """Extract content from a section that already has components."""
    pattern = rf'##\s+{re.escape(section_name)}\s*\n(.*?)(?=##\s+(?!#)|$)'
    m = re.search(pattern, body, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def extract_extra_content_from_request_body(body: str):
    """Extract non-param content from Request Body section (like ### Settings tables)."""
    rb_match = re.search(r'##\s+Request\s+Body\s*\n(.*?)(?=##\s+(?!#)|$)', body, re.DOTALL)
    if not rb_match:
        return None
    rb_section = rb_match.group(1)

    # Look for ### subsections that aren't "Example"
    extra_parts = []
    sub_pattern = r'(###\s+(?!Example).*?\n(?:.*?)(?=###|$))'
    for m in re.finditer(sub_pattern, rb_section, re.DOTALL):
        content = m.group(1).strip()
        # Skip if it's just param table stuff
        if not content.startswith("### Path") and not content.startswith("### Query"):
            extra_parts.append(content)

    return "\n\n".join(extra_parts) if extra_parts else None


def extract_notes_and_special(body: str):
    """Extract <Note>, <Warning>, <Tip>, and similar components from body."""
    components = []
    for pattern_str in [r'(<Note>.*?</Note>)', r'(<Warning>.*?</Warning>)',
                        r'(<Tip>.*?</Tip>)', r'(<Callout.*?</Callout>)']:
        for m in re.finditer(pattern_str, body, re.DOTALL):
            # Only extract if it's NOT inside the Request Body or Response section
            # that we're already handling
            components.append(m.group(1))
    return components


def convert_page(filepath: Path):
    """Convert a single API MDX page from old format to new format."""
    content = filepath.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)

    if not fm.get("title"):
        print(f"  WARNING: No title in frontmatter for {filepath}, skipping")
        return False

    # Extract the ApiPlayground block
    playground, body_without_pg = extract_api_playground(body)
    if playground is None:
        print(f"  WARNING: No ApiPlayground found in {filepath}, skipping")
        return False

    pg_props = extract_playground_props(playground)

    # Remove the duplicate heading
    body_clean = remove_heading(body_without_pg, fm)

    # Detect auth type
    auth_type = detect_auth_type(body_clean)

    # Parse parameters from playground
    params_from_pg = []
    if pg_props.get("parameters_raw"):
        params_from_pg = parse_parameters_from_playground(pg_props["parameters_raw"])

    # Separate path params and query params from playground parameters
    path_params_pg = [p for p in params_from_pg if p.get("in") == "path"]
    query_params_pg = [p for p in params_from_pg if p.get("in") != "path"]
    # For params without "in" field, check if they have "required: true" and the endpoint has {name}
    endpoint = pg_props.get("endpoint", "")
    for p in params_from_pg:
        if "in" not in p:
            if f'{{{p["name"]}}}' in endpoint:
                if p not in path_params_pg:
                    path_params_pg.append(p)
                    if p in query_params_pg:
                        query_params_pg.remove(p)

    # Parse path params from table in body
    path_params_table = parse_path_params_table(body_clean)
    # Parse query params from table in body
    query_params_table = parse_query_params_table(body_clean)

    # Merge path params: prefer table (richer descriptions), fall back to playground
    path_params = path_params_table if path_params_table else path_params_pg
    # Merge query params: prefer table, fall back to playground
    query_params = query_params_table if query_params_table else query_params_pg

    # Parse request body
    has_existing_pf = has_existing_param_fields_in_request(body_clean)
    existing_rb_content = None
    request_body_params = []
    extra_rb_content = None

    if has_existing_pf:
        # Extract existing <ParamField> components from Request Body section
        existing_rb_content = extract_existing_components_section(body_clean, "Request Body")
        extra_rb_content = extract_extra_content_from_request_body(body_clean)
    else:
        rb_result = parse_request_body_bullets(body_clean)
        if rb_result == "ALREADY_COMPONENTS":
            existing_rb_content = extract_existing_components_section(body_clean, "Request Body")
        elif isinstance(rb_result, list):
            request_body_params = rb_result
        extra_rb_content = extract_extra_content_from_request_body(body_clean)

    # Parse response section
    response_json, response_status, response_status_text = find_response_json(body_clean)
    has_existing_rf = has_existing_response_fields(body_clean)
    existing_resp_content = None
    response_fields = []

    if has_existing_rf:
        existing_resp_content = extract_existing_components_section(body_clean, "Response")
        if not existing_resp_content:
            existing_resp_content = extract_existing_components_section(body_clean, "Responses")
    else:
        response_fields = find_response_fields_from_section(body_clean)

    # Parse error codes
    error_codes = find_error_codes(body_clean)

    # Extract any <Note> etc. components
    special_components = extract_notes_and_special(body_clean)

    # Set default status if not found
    if response_status is None:
        method = pg_props.get("method", "GET")
        if method == "POST":
            response_status = 201
            response_status_text = "Created"
        elif method == "DELETE":
            response_status = 204
            response_status_text = "No Content"
        elif method == "PUT" or method == "PATCH":
            response_status = 200
            response_status_text = "OK"
        else:
            response_status = 200
            response_status_text = "OK"

    # Update playground with response example
    updated_playground = update_playground_with_response(
        playground, response_json, response_status, response_status_text
    )

    # Now build the new page
    output_parts = []

    # Frontmatter
    output_parts.append(f'---\ntitle: "{fm["title"]}"\ndescription: "{fm.get("description", "")}"\n---\n')

    # ApiPlayground
    output_parts.append(updated_playground)

    # Authentication
    output_parts.append("")
    output_parts.append(build_auth_section(auth_type))

    # Path parameters
    if path_params:
        lines = ['', '<ApiSection title="Path parameters">']
        for p in path_params:
            desc = p.get("description", f"The {p['name']} parameter.")
            lines.append(build_param_field(
                p["name"], p.get("type", "string"), p.get("required", True),
                desc, location="path"
            ))
        lines.append('</ApiSection>')
        output_parts.append("\n".join(lines))

    # Query parameters
    if query_params:
        lines = ['', '<ApiSection title="Query parameters">']
        for p in query_params:
            desc = p.get("description", f"The {p['name']} parameter.")
            lines.append(build_param_field(
                p["name"], p.get("type", "string"), p.get("required", False),
                desc, location="query"
            ))
        lines.append('</ApiSection>')
        output_parts.append("\n".join(lines))

    # Request body
    if existing_rb_content:
        # Already has <ParamField> components, wrap in ApiSection
        # Strip any leading text that isn't a component
        rb_lines = existing_rb_content.split("\n")
        component_start = 0
        for i, line in enumerate(rb_lines):
            if line.strip().startswith("<ParamField") or line.strip().startswith("<ApiCollapsible"):
                component_start = i
                break
        preamble = "\n".join(rb_lines[:component_start]).strip()
        components = "\n".join(rb_lines[component_start:]).strip()

        section = ['\n<ApiSection title="Request body">']
        if preamble and not preamble.startswith("|"):
            # Only keep text preamble, not tables
            if not re.match(r'\|', preamble):
                pass  # Skip preamble text for clean output
        section.append(f'  {components}')
        section.append('</ApiSection>')
        output_parts.append("\n".join(section))

        if extra_rb_content:
            output_parts.append(f"\n{extra_rb_content}")
    elif request_body_params:
        lines = ['', '<ApiSection title="Request body">']
        lines.extend(build_nested_param_fields(request_body_params, location="body"))
        lines.append('</ApiSection>')
        output_parts.append("\n".join(lines))

        if extra_rb_content:
            output_parts.append(f"\n{extra_rb_content}")

    # Response section
    if existing_resp_content:
        # Already has <ResponseField> components
        # Extract just the component lines
        resp_lines = existing_resp_content.split("\n")
        component_lines = []
        text_lines = []
        in_components = False
        for line in resp_lines:
            if "<ResponseField" in line or "<ParamField" in line or in_components:
                component_lines.append(line)
                in_components = True
                if ("</ResponseField>" in line or "</ParamField>" in line) and \
                   line.strip().endswith(">"):
                    in_components = False
            else:
                if line.strip() and not line.strip().startswith("###"):
                    text_lines.append(line)

        section = [f'\n<ApiSection title="Response" status={{{response_status}}} statusText="{response_status_text}">']
        if component_lines:
            section.append("\n".join(component_lines))
        section.append('</ApiSection>')
        output_parts.append("\n".join(section))
    elif response_fields:
        lines = [f'\n<ApiSection title="Response" status={{{response_status}}} statusText="{response_status_text}">']
        for f in response_fields:
            lines.append(build_response_field(
                f["name"], f.get("type", "string"),
                f.get("description", ""), f.get("required", False)
            ))
        lines.append('</ApiSection>')
        output_parts.append("\n".join(lines))
    else:
        # No response fields parsed but we have a status - add a minimal response section
        # Check if there's descriptive text for the response
        resp_match = re.search(r'##\s+Responses?\s*\n(.*?)(?=##\s+Code|##\s+$|$)', body_clean, re.DOTALL)
        if resp_match:
            resp_text = resp_match.group(1).strip()
            # Find text for the success status
            success_pattern = rf'###\s+{response_status}\s*\n\s*(.*?)(?=###\s+\d{{3}}|$)'
            sm = re.search(success_pattern, resp_text, re.DOTALL)
            if sm:
                desc_text = sm.group(1).strip()
                # Remove json blocks
                desc_text = re.sub(r'```json\s*\n.*?\n```', '', desc_text, flags=re.DOTALL).strip()
                # Remove bullet points (already handled)
                desc_text_lines = []
                for line in desc_text.split("\n"):
                    if not line.strip().startswith("-"):
                        desc_text_lines.append(line)
                    else:
                        break
                desc_text = "\n".join(desc_text_lines).strip()

    # Errors section
    if error_codes:
        lines = ['', '<ApiSection title="Errors">']
        for e in error_codes:
            lines.append(f'  <ParamField name="{e["code"]}" type="{e["status_text"]}">')
            lines.append(f'    {e["description"]}')
            lines.append('  </ParamField>')
        lines.append('</ApiSection>')
        output_parts.append("\n".join(lines))

    # Special components (Note, Warning, etc.)
    for comp in special_components:
        output_parts.append(f"\n{comp}")

    # Join and clean up
    result = "\n\n".join(output_parts)
    # Clean up multiple blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)
    # Ensure file ends with newline
    result = result.rstrip() + "\n"

    return result


def main():
    files = find_mdx_files(API_DIR)
    print(f"Found {len(files)} MDX files to convert")

    converted = 0
    skipped = 0
    errors = 0

    for filepath in files:
        relpath = filepath.relative_to(API_DIR)
        print(f"Converting: {relpath}")

        try:
            result = convert_page(filepath)
            if result is False:
                skipped += 1
                continue
            filepath.write_text(result, encoding="utf-8")
            converted += 1
        except Exception as e:
            print(f"  ERROR converting {relpath}: {e}")
            import traceback
            traceback.print_exc()
            errors += 1

    print(f"\nDone! Converted: {converted}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()
