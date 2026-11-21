"""Refresh the catalog region from a v1.59.1 product checkout, without checking it out.

python3 scripts/generate-platform-mcp-catalog.py /path/to/future-agi
"""

import argparse
import ast
import html
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

RELEASE = "v1.59.1"
PAGE = (Path(__file__).resolve().parents[1] / "src/pages/docs/falcon-ai/reference/platform-mcp-tools.mdx")
SOURCE = "futureagi/mcp_server/catalog/tools.generated.json"
BEGIN = "{/* BEGIN GENERATED PLATFORM MCP CATALOG */}"
END = "{/* END GENERATED PLATFORM MCP CATALOG */}"
GROUPS = {
    "context": ("Context", "Identify the caller and workspace"),
    "observability": ("Observability", "Find traces and spans, manage online evaluations, or run project SQL"),
    "error_feed": ("Error Feed", "Read clusters, patterns and example traces"),
    "datasets": ("Datasets", "Work with datasets, cells, evaluations, prompts and knowledge bases"),
    "evaluations": ("Evaluations", "Inspect, configure and test evaluation templates"),
    "annotations": ("Annotations", "Inspect queues and submit or complete an item"),
    "prompts": ("Prompts", "Manage workbench templates, versions and runs"),
    "experiments": ("Experiments", "Inspect experiments or start a new one"),
    "optimization": ("Optimization", "Inspect or start dataset optimization runs"),
    "agents": ("Agents", "Inspect agents, scenarios and executions, or start a saved test"),
    "simulation": ("Simulation", "Manage agent versions, scenarios and saved test configurations"),
    "dashboards": ("Dashboards", "Manage dashboards and widgets or query metrics"),
    "gateway": ("Gateway", "Inspect gateway configuration, sessions, logs and analytics"),
    "usage": ("Usage", "Inspect organization usage and cost"),
}

# Keyed to the actual v1.59.1 API checks. A readOnlyHint is not an RBAC rule.
READ_POSTS_EXEMPT_FROM_WRITE_GATE = {"run_sql", "cancel_sql", "list_eval_templates"}
QUEUE_GATES = {
    "submit_annotation": "Access; queue annotator or manager (including manager-equivalent admins)",
    "complete_annotation_item": "Access; you must already have submitted annotations for this item",
}
# Keep the generated public summaries focused on what a caller needs to do.
SUMMARIES = {
    "add_dataset_rows": "Append rows. Each row takes a `cells` array of `column_name` and `value` pairs. Create writable columns first. An unknown or duplicate column rejects the batch; a flat column-to-value dictionary is not a row.",
    "list_trace_properties": "Discover filters for `search_traces` (`source=traces`) or `list_spans` (`source=spans`). Set `cursor_mode=true`, `per_eval_config=true`, and `project_ids` when known. Use the returned `name` as `column_id`; preserve `property_id` and `source` for typed attributes. For `filter_config.col_type`, map `system_metric` to `SYSTEM_METRIC`, `custom_attribute` to `SPAN_ATTRIBUTE`, `eval_metric` to `EVAL_METRIC`, and `annotation_metric` to `ANNOTATION`. In cursor mode, omit `page` and `exclude_custom_attributes`; use `next_cursor` as `cursor` while `has_more` is true.",
    "list_alert_rules": "List configured alert monitors, their thresholds and projects. Compare with `list_fired_alerts` to see which monitors have fired.",
    "delete_dashboard": "Delete a dashboard and its widgets.",
    "delete_datasets": "Soft-delete one or more datasets using `dataset_ids`. Deletion also affects their rows, columns and attached evaluations.",
    "get_sql_result": "Poll your job. MCP returns up to 100 rows by default, within a byte limit. While `result.has_more` is true, pass `result.next_offset` as `offset`. If `result.previewed` is true, download the full cells using authenticated `GET /tracer/sql-query/{id}/download/` with `project_id` and `file_format` (`csv` or `parquet`). Results expire after 24 hours. You need project access on every read.",
    "get_trace": "Return a trace by ID. Pass at most one run scope: `test_execution_id` or `call_execution_id`.",
    "get_span": "Read a span by ID, optionally pinned with `project_id`. Pass at most one run scope: `test_execution_id` or `call_execution_id`. For a physical lookup, supply the entire reference: `project_id`, `trace_id`, `start_hour`, `observation_type`, `service_name`, `expected_start_time` and `expected_version`. Use timezone-qualified timestamps (at most six fractional digits); `start_hour` is the UTC hour containing `expected_start_time`, aligned to the hour. Send the version as a canonical unsigned 64-bit decimal string.",
    "submit_annotation": "Submit label values matching the settings from `get_annotation_item_detail`. Submission moves a pending item to `in_progress`; call `complete_annotation_item` when you finish your annotations.",
    "complete_annotation_item": "Finish your annotation pass and get the next item, if any. A `completed_item_id` receipt does not guarantee the item is complete: it stays `in_progress` until the required labels and annotator count are covered. If review is required, `status` stays `in_progress` and `review_status` becomes `pending_review`.",
    "list_guardrail_rules": "Read guardrail trigger counts by rule. Request logs show whether a guardrail triggered, not which rule triggered it.",
    "update_eval_task": "Pause the running task before editing it. `edit_rerun` keeps existing results; `fresh_run` deletes them and starts again. Reruns may incur evaluation charges.",
    "create_experiment": "Create and start an experiment. Read `experiment_id` from the result message and pass it to `get_experiment` to follow the run.",
    "get_error_cluster": "Read an issue and its stored root-cause analysis, when available. MCP omits `rca.trace` (the investigation trail); it keeps the synthesis, recommended fix, confidence and evidence trace IDs. Use `get_trace` to inspect the evidence.",
    "get_error_cluster_overview": "Read a cluster's pattern summary, daily counts and representative traces. Start with `rep_limit=3`. If even one representative trace exceeds the response limit, use `list_error_cluster_traces` for paged evidence without the pattern summary.",
}


def text(value):
    """Escape prose for MDX/GFM; preserve intentional inline code spans."""
    def escape(segment):
        return (html.escape(segment, quote=False).replace("{", "&#123;").replace("}", "&#125;")
                .replace("|", "&#124;").replace("—", ", ").replace("\n", " "))
    return "".join(part if part.startswith("`") else escape(part)
                   for part in re.split(r"(`[^`]+`)", value))


def literal(value):
    return "`" + json.dumps(value, ensure_ascii=False).replace("|", r"\|") + "`"


def resolve(spec, defs):
    return defs[spec["$ref"].split("/")[-1]] if "$ref" in spec else spec


def type_label(spec, defs):
    spec = resolve(spec, defs)
    if "anyOf" in spec:
        return " or ".join(type_label(v, defs) for v in spec["anyOf"])
    if spec.get("type") == "array":
        item_type = type_label(spec.get("items", {}), defs)
        return f"array of ({item_type})" if " or " in item_type else f"array of {item_type}"
    return spec.get("type", "JSON value")


def constraints(spec, *, nullable=False):
    notes = []
    for lo, hi, unit in [("minimum", "maximum", ""), ("minLength", "maxLength", " chars"),
                         ("minItems", "maxItems", " items")]:
        if lo in spec and hi in spec:
            notes.append(f"{spec[lo]} to {spec[hi]}{unit}")
        elif lo in spec:
            notes.append(f"min {spec[lo]}{unit}")
        elif hi in spec:
            notes.append(f"max {spec[hi]}{unit}")
    if spec.get("uniqueItems"):
        notes.append("distinct items")
    if "enum" in spec:
        values = spec["enum"]
        if nullable and None not in values:
            values = [*values, None]
        notes.append("one of " + ", ".join(map(literal, values)))
    if "format" in spec:
        notes.append(f"format `{spec['format']}`")
    if "pattern" in spec:
        notes.append(f"pattern `{spec['pattern']}`")
    if "default" in spec:
        notes.append("default " + literal(spec["default"]))
    return notes


def rows(path, spec, required, defs):
    spec = resolve(spec, defs)
    branches = [resolve(v, defs) for v in spec.get("anyOf", [spec])]
    notes = []
    nullable = any(branch.get("type") == "null" for branch in branches)
    for node in ([spec] if "anyOf" in spec else []) + branches:
        notes.extend(constraints(node, nullable=nullable and node is not spec))
        description = node.get("description", "")
        # Include non-obvious input semantics, not redundant serializer labels or
        # REST-only behavior (e.g. multipart uploads are not MCP arguments).
        if description.startswith("Which time-window preset"):
            description = "Records the chosen preset only. To filter the query, resolve it to explicit UTC bounds and send `date_range`."
        if description.startswith(("A UUID string identifying", "New cell value.", "Any valid JSON value.")):
            continue
        if description:
            notes.append(text(description))
    yield f"| `{path}` | {type_label(spec, defs)} | {required} | {'; '.join(notes)} |"
    for branch in branches:
        for key, value in branch.get("properties", {}).items():
            yield from rows(f"{path}.{key}", value, "Yes" if key in branch.get("required", []) else "No", defs)
        entry = branch.get("additionalProperties")
        if isinstance(entry, dict) and set(entry) - {"title", "description"}:
            yield from rows(path + ".*", entry, "Map value", defs)
        if "items" in branch:
            item = resolve(branch["items"], defs)
            if set(item) - {"type", "title", "description"}:
                yield from rows(path + "[]", item, "Element", defs)


def effect(tool):
    hints = tool["annotations"]
    if hints["destructiveHint"]:
        result = "Destructive"
    else:
        result = "Read" if hints["readOnlyHint"] else "Write"
    return result + (", external" if hints["openWorldHint"] else "")


def gate(tool):
    name = tool["name"]
    if name in QUEUE_GATES:
        return QUEUE_GATES[name]
    if tool["annotations"]["readOnlyHint"] and (
        tool["request"]["method"] == "GET" or name in READ_POSTS_EXEMPT_FROM_WRITE_GATE
    ):
        return "Access"
    return "Write"


def tool_lines(tool):
    name = tool["name"]
    request = tool["request"]
    schema = tool["inputSchema"]
    yield f"<details>\n<summary><code>{name}</code> · {effect(tool)}</summary>\n"
    yield text(SUMMARIES.get(name, tool["description"])) + "\n"
    hint = str(tool['annotations']['idempotentHint']).lower()
    yield f"REST: `{request['method']} {request['path']}`. Workspace gate: {gate(tool)}. Idempotent hint: `{hint}`.\n"
    if schema["properties"]:
        yield "| Argument | Type | Required | Details |"
        yield "| --- | --- | --- | --- |"
        for key, spec in schema["properties"].items():
            required = "Yes" if key in schema.get("required", []) else "No"
            yield from rows(key, spec, required, schema.get("definitions", {}))
    else:
        yield "No arguments."
    yield "\n</details>\n"


def catalog(manifest, scope_labels):
    groups = defaultdict(list)
    for tool in manifest["tools"]:
        groups[tool["group"]].append(tool)
    if set(groups) != set(GROUPS) or not (manifest["tool_count"] == len(manifest["tools"]) == 111):
        raise ValueError("Review groups and release counts before regenerating")
    yield "| Group (OAuth scope) | Tools | Use it to |"
    yield "| --- | ---: | --- |"
    for slug, (label, purpose) in GROUPS.items():
        anchor = label.lower().replace(" ", "-")
        yield f"| [{scope_labels[slug]}](#{anchor}) (`{slug}`) | {len(groups[slug])} | {purpose} |"
    for slug, (label, _) in GROUPS.items():
        yield f"\n### {label}\n"
        for tool in groups[slug]:
            yield from tool_lines(tool)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args()
    manifest = json.loads(subprocess.check_output(["git", "-C", str(args.repo), "show", f"{RELEASE}:{SOURCE}"]))
    constants = subprocess.check_output(["git", "-C", str(args.repo), "show", f"{RELEASE}:futureagi/mcp_server/constants.py"])
    declaration = next(stmt for stmt in ast.parse(constants).body if isinstance(stmt, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "TOOL_GROUPS" for t in stmt.targets))
    scope_labels = {slug: group["name"] for slug, group in ast.literal_eval(declaration.value).items()}
    head, tail = PAGE.read_text(encoding="utf-8").split(BEGIN)
    _, tail = tail.split(END)
    PAGE.write_text(head + BEGIN + "\n\n" + "\n".join(catalog(manifest, scope_labels)) + "\n" + END + tail, encoding="utf-8")
