"""Refresh the generated section of /docs/cli/api-reference from the release.

Usage: python3 scripts/sync-cli-api-reference.py /path/to/futureagi-cli
Pass a checkout of v0.2.2. The schema snapshot is checked against `fagi schema`
by the CLI's TestSchemaGolden. No API credentials, network or binaries needed.
"""
from collections import defaultdict
from html import escape
import json
from pathlib import Path
import sys


PAGE = Path(__file__).resolve().parents[1] / 'src/pages/docs/cli/api-reference.mdx'
START = '{/* BEGIN generated CLI operations */}'
END = '{/* END generated CLI operations */}'
VERSION = '0.2.2'

# Keep the command descriptions about the CLI, not the upstream MCP tool names.
PURPOSE = {
    'submit_annotation': 'Submitting annotations changes a pending item to `in_progress`; complete it separately with `annotations queues items complete`.',
    'get_annotation_item_detail': 'Read the source, queue instructions, label settings and existing annotations for an item. `--reserve` requests an editing reservation; it does not lock an item opened for review.',
    'delete_prompt_template': 'Mark the prompt template and its versions as deleted.',
    'create_dashboard': 'Create an empty dashboard. Add widgets with `dashboards widgets create`.',
    'create_dashboard_widget': 'Add a widget. Its `query_config` uses the same shape as `dashboards metrics query`.',
    'add_dataset_prompt': 'Create a prompt output column and schedule processing of dataset rows. This can incur model charges.',
    'run_dataset_prompts': 'Queue the specified prompts for a dataset. When `--selected-all-rows` is true, `row_ids` identifies rows to **exclude**.',
    'add_dataset_rows': 'Append rows. Each object in `rows` must contain a `cells` array with `column_name` and `value` for each cell; flat row objects are invalid.',
    'configure_dataset_evaluation': 'Attach a template with a lowercase name and column mappings in `config.mapping`. Set `--run=false` for setup only; `--run=true` can start paid work.',
    'create_dataset': 'Create an empty dataset. Add input columns with `datasets columns create` before you add rows.',
    'list_dataset_evaluations': 'Get the IDs of evaluations attached to a dataset with `--eval-type user`. Use these IDs, not template IDs, to run the evaluations.',
    'get_dataset_prompt_stats': 'Return prompt IDs and usage statistics. To inspect cell outputs, use `datasets get`.',
    'get_error_cluster': 'Get one error issue and its stored root-cause analysis, if one exists.',
    'get_error_cluster_overview': 'Get daily error counts, pattern statistics and representative traces for one issue.',
    'create_experiment': 'Create an experiment and request a run. Both `prompt_config` and `user_eval_metrics` must be nonempty. The `result` message contains `experiment_id=<uuid>`; use `experiments get` to check its status. Creation can succeed even if the workflow does not start.',
    'list_guardrail_rules': 'List guardrail rules and how often each rule triggered.',
    'list_gateway_session_requests': 'Read the newest 100 requests for a gateway session UUID. For older requests use `gateway request-logs list --session-id` with the session ID string.',
    'test_gateway_playground': 'Send a real chat completion through the gateway routing and guardrail rules. The request can incur model charges.',
    'list_alert_rules': 'List the configured alert monitors, including their projects and thresholds.',
    'create_eval_config': 'Create an evaluation configuration that an online evaluation task can use.',
    'list_eval_configs': 'List the configuration IDs accepted by `observability eval-tasks create`. These are not template IDs.',
    'create_eval_task': 'Start an online evaluation task. Use evaluation configuration IDs from the same project. Retrying after a timeout can duplicate the task and its charges.',
    'resume_eval_task': 'Resume a paused task and schedule the remaining evaluations. Charges can apply.',
    'update_eval_task': 'Update and rerun the task. Pause a running task before updating it. `edit_rerun` preserves results; `fresh_run` deletes earlier results. Either can incur charges.',
    'list_trace_properties': 'Discover properties for trace or span filters. In cursor mode, use `--source traces` for trace filters or `--source spans` for span filters.',
    'run_prompt': 'To execute a version, set the `is_run` body key to `"prompt"` and supply `--version`. Poll `prompts run get` with the same template ID and `--template-version` matching the submitted `--version`.',
    'get_prompt_run': 'Get status and outputs for a prompt run. Supply the submitted version as `--template-version` to avoid polling a different default version.',
}

# Exceptions that affect safe use even when a caller passes valid flags.
METRIC_PAGING = 'For cursor mode, pass `--cursor-mode` with `--page-size` (normally 1 to 50); omit `--page`, `--workflow` and `--exclude-custom-attributes`. Read `result.next_cursor` in JSON and pass it as `--cursor` for the next page. `--role` and `--source spans` require cursor mode.'

CAVEAT = {
    'submit_annotation': 'Supply at least one entry in `annotations`, with `label_id` and `value`. In CLI 0.2.2 the value must be a JSON object, so labels that require scalar or array values cannot be submitted with this command.',
    'create_eval_task': 'For a historical run without a sampling policy, set `--spans-limit`. For continuous runs the platform ignores that limit. Omit `--start-time`, `--end-time`, `--last-run` and `--status`: the platform manages these on creation.',
    'update_eval_task': 'Omit `--row-type`, which the server rejects on update, and `--status`, which it ignores. Changing the sampling population requires `fresh_run`.',
    'list_trace_properties': METRIC_PAGING,
    'get_annotation_queue': 'Use `annotations queues list --include-counts` for item counts.',
    'list_annotation_queues': 'Counts are populated only with `--include-counts`; a missing count does not mean zero.',
    'list_annotation_queue_items': 'Only `--assigned-to me` filters assignments.',
    'query_dashboard_metrics': 'An empty table can mean the query is still running. Inspect `result.query_status` in JSON; poll without `--refresh`.',
    'query_dashboard_widget': 'Inspect `result.query_status` in JSON before treating an empty result as zero metrics.',
    'list_dashboard_metrics': METRIC_PAGING + ' Outside cursor mode, `--workflow dataset` returns grouped data; use `--json` without `--fields`.',
    'create_dataset_column': 'Omit `--source` when creating a static input column.',
    'create_dataset': 'The platform ignores `--row`.',
    'complete_annotation_item': 'Read `result.next_item.id` in JSON for the next item.',
    'add_dataset_prompt': 'Supply both `config.model` and `config.messages` in the JSON body.',
    'configure_dataset_evaluation': 'The response does not include the attached ID. Read it with `datasets evaluations list --eval-type user`.',
    'list_dataset_evaluations': 'Supply at most one value each for `--eval-tags` and `--use-cases`.',
    'update_dataset_cell': 'For media cells, pass a data URI or HTTP(S) URL as a string. Omitting `new_value` or passing an empty string clears the cell.',
    'list_knowledge_bases': 'An out-of-range page can return HTTP 500. Check the requested position instead of retrying it.',
    'add_dataset_rows': 'Use existing writable column names. Unknown or duplicate names reject the batch. For media cells, read the stored value back: an upload failure can leave an empty string even when the request succeeds.',
    'test_evaluation': 'Use `--template-type Llm`, `Futureagi` or `Function`. Put input mappings in `config.mapping`. For `Llm`, set `config.model`; for `Function`, supply `eval_type_id`. A timeout does not cancel model work.',
    'create_eval_template': 'For a non-draft LLM or agent evaluator, supply instructions with a `{{variable}}`; for a code evaluator, supply the code.',
    'delete_datasets': 'Deletion cascades to rows, columns and attached evaluations. One missing ID rejects the whole request.',
    'run_dataset_evals': '`--failed-only` applies only with `--experiment-id`.',
    'get_dataset': 'When using `--column-config-only`, select `--json`: the response has no `result.table`.',
    'update_dataset_prompt': 'Send both `name` and a non-null `config`. An edit can trigger paid processing; use `datasets columns rename` for a rename only.',
    'create_prompt_template': 'To initialize its workbench draft, open the new template with `prompts get`.',
    'list_guardrail_rules': 'The platform ignores `--page` and `--limit` on this operation.',
    'get_gateway_config': 'The platform returns organization runtime configuration rather than filtering by `--id`.',
    'list_projects': 'The platform ignores `--filters` and `--tags` on this operation.',
    'list_alert_rules': 'Pass at most one value each for `--project-id`, `--status` and `--metric-type`.',
    'create_optimization_run': 'If startup fails, check existing runs before retrying: the run may already have been saved.',
    'list_prompt_templates': 'Use at most one `--modality` value. `--created-at` does not filter and `--version` can fail server-side.',
    'get_usage_overview': 'Cloud only. Totals cover the organization; a workspace selector does not guarantee workspace-only totals.',
}


def text(value):
    return escape(value, quote=False).replace('{', '&#123;').replace('}', '&#125;').replace('|', '&#124;')


def inputs(op):
    rows = []
    for f in op['flags'] + op['data_only_body_fields']:
        data_only = f in op['data_only_body_fields']
        name = f"`{f['data_key']}` (JSON key)" if data_only else f"`--{f['name']}`"
        if f.get('data_key') and not data_only:
            name += f" / `{f['data_key']}`"
        kind = 'any JSON value' if f.get('json_value') else f['type']
        if kind == 'array' and f.get('items_type'):
            kind += ' of ' + f['items_type'] + 's'
        desc = f['description'].replace('.;', ';').strip().strip(';')
        if op['tool'] == 'create_optimization_run' and f.get('data_key') == 'optimizer_config':
            desc = 'Algorithm-specific object. For random_search use num_variations; for gepa use max_metric_calls. Do not use num_trials.'
        if op['tool'] == 'update_dataset_cell' and f['name'] == 'new-value':
            desc = 'String value sent in JSON. This command does not upload multipart files.'
        if op['tool'] == 'create_dataset_column' and f['name'] == 'column-type':
            desc = 'One of `text`, `boolean`, `integer`, `float`, `json`, `array`, `image`, `images`, `datetime`, `audio`, `document`, `others`, `persona`.'
        if op['tool'] in ('create_dashboard_widget', 'update_dashboard_widget'):
            if f['name'] == 'width':
                desc = '1 to 12 columns.'
            elif f['name'] == 'height':
                desc = 'At least 1.'
        desc = text(desc).replace('CLI safety maximum', 'CLI maximum').replace(' (not a server bound; --allow-large-pages bypasses it)', '')
        if f.get('pattern') and desc.startswith('pattern '):
            desc = f"pattern `{f['pattern']}`"
        args = f"{f['location']}, {kind}" + (', required' if f['required'] else '')
        # Descriptions generated by fagi also include its constraints; required is already visible.
        parts = [part.strip() for part in desc.split(';') if part.strip() not in ('', 'required')]
        rows.append((name, args, '; '.join(parts)))
    if not rows:
        return []
    if not any(details for _, _, details in rows):
        return ['', '| Input | Location and type |', '| --- | --- |',
                *[f'| {name} | {kind} |' for name, kind, _ in rows]]
    return ['', '| Input | Location and type | Details |', '| --- | --- | --- |',
            *['| ' + ' | '.join(row) + ' |' for row in rows]]


def paging(op):
    flags = {f['name']: f for f in op['flags']}
    parts = []
    for pos in ('page', 'page-number', 'current-page-index', 'offset'):
        if pos in flags:
            base = flags[pos]['minimum']
            if op['tool'] in ('list_prompt_templates', 'list_knowledge_bases'):
                base = 1
            parts.append(f"`--{pos}`" + (f' (starts at {base})' if base is not None else ''))
    if 'cursor' in flags:
        parts.append('`--cursor-mode` with `--cursor`' if 'cursor-mode' in flags else '`--cursor`')
    if op['tool'] == 'list_guardrail_rules':
        return ''
    if not parts:
        return ''
    size = ', '.join('`--' + f + '`' for f in ('limit', 'page-size') if f in flags)
    return 'Pagination: ' + '; '.join(parts) + (f'. Page size: {size}' if size else '') + '.'


def render(op):
    cmd = op['path'].removeprefix('fagi api ')
    label = op['access']
    body = any(f['name'] == 'data-file' for f in op['control_flags'])
    fields = label == 'read' and op['rows'] and cmd.endswith((' list', ' search'))
    purpose = PURPOSE.get(op['tool']) or text(op['description'].split('. ')[0].rstrip('.') + '.')
    out = [f'<Accordion title="{cmd} ({label})">', '', purpose, '', f"`{op['method']} {op['http_path']}`"]
    if caveat := CAVEAT.get(op['tool']):
        out.extend(['', caveat])
    out.extend(inputs(op))
    controls = []
    if body:
        controls.append('`--data` or `--data-file` (`-` for stdin)')
    if fields:
        controls.append('`--fields`')
    if any(f['name'] == 'allow-large-pages' for f in op['control_flags']):
        controls.append('`--allow-large-pages`')
    if controls:
        out += ['', 'Local options: ' + '; '.join(controls) + '.']
    if page := paging(op):
        out += ['', page]
    cols = ', '.join('`' + col + '`' for col in op['columns'])
    path = f"`{op['rows']}`" if op['rows'] else 'the response root'
    out += ['', f'Table and JSONL select {path}.' + (f' Table columns: {cols}.' if cols else ''), '', '</Accordion>']
    return '\n'.join(out)


def main(root):
    if (root / 'VERSION').read_text().strip() != VERSION:
        raise SystemExit(f'Expected CLI {VERSION}. Review examples and caveats before changing versions.')
    schema = json.loads((root / 'internal/cli/testdata/schema.json').read_text())
    ops = [op for op in schema['commands'] if op.get('tool') and op['path'].startswith('fagi api ')]
    if len({op['tool'] for op in ops}) != 93 or len(ops) != 93:
        raise SystemExit('Expected the 93 generated API operations in 0.2.2')
    groups = defaultdict(list)
    for op in ops:
        groups[op['group']].append(render(op))
    catalog = '\n\n'.join('### ' + key.replace('_', ' ').capitalize() + '\n\n' + '\n\n'.join(groups[key]) for key in sorted(groups))
    before, region = PAGE.read_text().split(START)
    _, after = region.split(END)
    PAGE.write_text(before + START + '\n\n' + catalog + '\n\n' + END + after)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
