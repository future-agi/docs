"""Contract tests against a real Temporal dev server and the real temporalio SDK.

Needs the Temporal CLI (`temporal server start-dev` is started for you on a free port) and
RUN_TEMPORAL_TESTS=1. The model is a local OpenAI-compatible stub; spans go to an in-memory exporter.
No Future AGI and no network. R-01 .. R-08 of the PRD map to the tests named below.
"""
import asyncio
import uuid

from temporalio.client import Client, WorkflowFailureError
from temporalio.contrib.opentelemetry import OpenTelemetryPlugin
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

import activities
import tracing
from conftest import FIXTURE_FI_API_KEY, FIXTURE_FI_SECRET_KEY, FIXTURE_MODEL_KEY, needs_temporal, reset_otel, temporal_cli
from helpers import MockModel, RecordingExporter, StartCounter, dump
from workflows import AgentRequest, WeatherAgentWorkflow

pytestmark = needs_temporal
ACTIVITIES = [activities.llm_plan, activities.get_weather, activities.llm_answer]
MARKER = "mk7d41"
ERROR_TEXT = "card ending 4242 of alice@example.com was declined"


def names(spans):
    return [s.name for s in spans]


def by_name(spans):
    out = {}
    for s in spans:
        out.setdefault(s.name, []).append(s)
    return out


class Run:
    """One Temporal dev server, one tracer provider with an in-memory exporter, one mock model."""

    def __init__(self, monkeypatch, *, model: MockModel, keep_error_text=False):
        self.monkeypatch, self.model = monkeypatch, model
        self.exporter, self.starts = RecordingExporter(), StartCounter()
        if keep_error_text:
            monkeypatch.setenv("KEEP_TEMPORAL_ERROR_TEXT", "true")
        monkeypatch.setattr(activities, "client", model.client())
        self.provider = tracing.setup_tracing(exporter=self.exporter)
        self.provider.add_span_processor(self.starts)

    def plugin(self):
        return OpenTelemetryPlugin(add_temporal_spans=True)

    async def execute(self, env: WorkflowEnvironment, request: AgentRequest, *, worker_plugin=True, client_plugin=True, **worker_args):
        address = env.client.service_client.config.target_host
        with_plugin = await Client.connect(address, plugins=[self.plugin()])
        without_plugin = await Client.connect(address)
        starter_client = with_plugin if client_plugin else without_plugin
        worker_client = with_plugin if worker_plugin else without_plugin
        queue = f"q-{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf-{uuid.uuid4().hex[:8]}"
        async with Worker(worker_client, task_queue=queue, workflows=[WeatherAgentWorkflow], activities=ACTIVITIES, **worker_args):
            try:
                result = await starter_client.execute_workflow(WeatherAgentWorkflow.run, request, id=workflow_id, task_queue=queue)
            except WorkflowFailureError:
                result = None
        self.provider.force_flush()
        return workflow_id, result, starter_client


def run_scenario(monkeypatch, fresh_otel, scenario, *, model=None, keep_error_text=False):
    model = model or MockModel(marker=MARKER)
    reset_otel()

    async def main():
        env = await WorkflowEnvironment.start_local(dev_server_existing_path=temporal_cli())
        try:
            run = Run(monkeypatch, model=model, keep_error_text=keep_error_text)
            await scenario(run, env)
            return run
        finally:
            await env.shutdown()

    try:
        return asyncio.run(main())
    finally:
        model.close()
        reset_otel()


def test_hierarchy_one_trace_and_model_fields(monkeypatch, fresh_otel):
    """R-02 / AC-02: StartWorkflow > RunWorkflow > StartActivity > RunActivity > model or tool span, one trace."""
    out = {}

    async def scenario(run, env):
        out["id"], out["result"], _ = await run.execute(env, AgentRequest(question="What is the weather in Lisbon?"))

    run = run_scenario(monkeypatch, fresh_otel, scenario)
    spans = run.exporter.spans
    assert out["result"] == f"It is sunny in Lisbon{MARKER}."
    assert sorted(names(spans)) == sorted([
        "StartWorkflow:WeatherAgentWorkflow", "RunWorkflow:WeatherAgentWorkflow",
        "StartActivity:llm_plan", "RunActivity:llm_plan", "ChatCompletion",
        "StartActivity:get_weather", "RunActivity:get_weather", "get_weather",
        "StartActivity:llm_answer", "RunActivity:llm_answer", "ChatCompletion",
    ])
    assert len({s.context.trace_id for s in spans}) == 1
    by_id = {s.context.span_id: s for s in spans}

    def parent(span):
        return by_id[span.parent.span_id].name

    groups = by_name(spans)
    assert groups["StartWorkflow:WeatherAgentWorkflow"][0].parent is None
    assert parent(groups["RunWorkflow:WeatherAgentWorkflow"][0]) == "StartWorkflow:WeatherAgentWorkflow"
    assert {parent(s) for s in groups["StartActivity:llm_plan"] + groups["StartActivity:get_weather"]} == {"RunWorkflow:WeatherAgentWorkflow"}
    assert parent(groups["RunActivity:llm_plan"][0]) == "StartActivity:llm_plan"
    assert {parent(s) for s in groups["ChatCompletion"]} == {"RunActivity:llm_plan", "RunActivity:llm_answer"}
    assert parent(groups["get_weather"][0]) == "RunActivity:get_weather"
    for model_span in groups["ChatCompletion"]:
        assert model_span.attributes["gen_ai.span.kind"] == "LLM"
        assert model_span.attributes["gen_ai.request.model"] == "gpt-6-luna"
        assert (model_span.attributes["gen_ai.usage.input_tokens"], model_span.attributes["gen_ai.usage.output_tokens"]) == (11, 7)
    assert groups["get_weather"][0].attributes["gen_ai.span.kind"] == "TOOL"
    # the session is the workflow id on every span, and the project is a resource attribute
    assert {s.attributes["session.id"] for s in spans} == {out["id"]}
    assert {s.resource.attributes["project_name"] for s in spans} == {"temporal-test"}


def test_forced_replay_exports_every_span_once(monkeypatch, fresh_otel):
    """R-03 / AC-03: with no workflow cache every workflow task replays the history; the span count is unchanged."""

    async def baseline(run, env):
        run.baseline_id, *_ = await run.execute(env, AgentRequest(question="q"))

    async def replayed(run, env):
        run.replay_id, run.result, run.client = await run.execute(env, AgentRequest(question="q"), max_cached_workflows=0)
        run.started_before_replayer = sum(run.starts.started.values())
        run.exported_before_replayer = len(run.exporter.spans)
        history = await run.client.get_workflow_handle(run.replay_id).fetch_history()
        await Replayer(workflows=[WeatherAgentWorkflow], plugins=[run.plugin()]).replay_workflow(history)
        run.provider.force_flush()

    base = run_scenario(monkeypatch, fresh_otel, baseline)
    base_names = sorted(names(base.exporter.spans))
    run = run_scenario(monkeypatch, fresh_otel, replayed)
    assert sorted(names(run.exporter.spans)) == base_names  # same spans as without replay
    ids = [(s.context.trace_id, s.context.span_id) for s in run.exporter.spans]
    assert len(ids) == len(set(ids)), "a span was exported twice"
    # the replays really happened: the workflow span was started once per workflow task
    assert run.starts.started["RunWorkflow:WeatherAgentWorkflow"] >= 4
    assert run.starts.started["StartActivity:llm_plan"] >= 4
    assert len(by_name(run.exporter.spans)["RunWorkflow:WeatherAgentWorkflow"]) == 1
    # a Replayer over the stored history starts spans again and exports none
    assert sum(run.starts.started.values()) > run.started_before_replayer
    assert len(run.exporter.spans) == run.exported_before_replayer


def test_retried_activity_keeps_every_attempt(monkeypatch, fresh_otel):
    """R-04 / AC-04: both attempts of a retried activity are exported; the failed one is ERROR."""

    async def scenario(run, env):
        run.id, run.result, _ = await run.execute(env, AgentRequest(question="q", flaky=True))

    run = run_scenario(monkeypatch, fresh_otel, scenario)
    groups = by_name(run.exporter.spans)
    assert run.result is not None
    assert len(groups["StartActivity:get_weather"]) == 1
    attempts = sorted(groups["RunActivity:get_weather"], key=lambda s: s.start_time)
    assert [s.status.status_code.name for s in attempts][0] == "ERROR"
    assert len(attempts) == 2 and attempts[1].status.status_code.name != "ERROR"
    tools = sorted(groups["get_weather"], key=lambda s: s.start_time)
    assert len(tools) == 2 and tools[0].status.status_code.name == "ERROR"
    assert {s.parent.span_id for s in tools} == {s.context.span_id for s in attempts}
    assert groups["RunWorkflow:WeatherAgentWorkflow"][0].status.status_code.name != "ERROR"


def test_failed_model_call_is_error_on_every_span_and_exports_no_error_text(monkeypatch, fresh_otel):
    """Errors are ERROR spans; the model's error text and the stack trace do not leave the process."""
    bad = "no-such-model"

    async def scenario(run, env):
        run.id, run.result, _ = await run.execute(env, AgentRequest(question="q", model=bad))

    run = run_scenario(monkeypatch, fresh_otel, scenario, model=MockModel(fail_for_model=bad, error_text=ERROR_TEXT))
    groups = by_name(run.exporter.spans)
    assert run.result is None
    assert [s.status.status_code.name for s in groups["ChatCompletion"]] == ["ERROR", "ERROR"]
    assert [s.status.status_code.name for s in groups["RunActivity:llm_plan"]] == ["ERROR", "ERROR"]
    assert groups["RunWorkflow:WeatherAgentWorkflow"][0].status.status_code.name == "ERROR"
    text = dump(run.exporter.spans)
    assert ERROR_TEXT not in text and "Traceback" not in text and "exception.stacktrace" not in text
    assert "NotFoundError" in text  # the exception type is kept


def test_error_text_opt_in_exports_the_message_but_not_the_stack_trace(monkeypatch, fresh_otel):
    bad = "no-such-model"

    async def scenario(run, env):
        await run.execute(env, AgentRequest(question="q", model=bad))

    run = run_scenario(monkeypatch, fresh_otel, scenario, model=MockModel(fail_for_model=bad, error_text=ERROR_TEXT), keep_error_text=True)
    text = dump(run.exporter.spans)
    assert ERROR_TEXT in text
    assert "Traceback" not in text and "exception.stacktrace" not in text


def test_plugin_only_on_the_client_leaves_the_activity_spans_disconnected(monkeypatch, fresh_otel):
    """R-01 / AC-01: the recipe's misconfiguration test. Without the plugin on the worker the model span has no parent."""

    async def scenario(run, env):
        run.id, *_ = await run.execute(env, AgentRequest(question="q"), worker_plugin=False)

    run = run_scenario(monkeypatch, fresh_otel, scenario)
    spans = run.exporter.spans
    groups = by_name(spans)
    assert "RunActivity:llm_plan" not in groups and "RunWorkflow:WeatherAgentWorkflow" not in groups
    start = groups["StartWorkflow:WeatherAgentWorkflow"][0]
    for model_span in groups["ChatCompletion"]:
        assert model_span.context.trace_id != start.context.trace_id
        assert model_span.parent is None


def test_plugin_only_on_the_worker_starts_the_trace_at_the_workflow(monkeypatch, fresh_otel):
    async def scenario(run, env):
        run.id, *_ = await run.execute(env, AgentRequest(question="q"), client_plugin=False)

    run = run_scenario(monkeypatch, fresh_otel, scenario)
    groups = by_name(run.exporter.spans)
    assert "StartWorkflow:WeatherAgentWorkflow" not in groups
    assert groups["RunWorkflow:WeatherAgentWorkflow"][0].parent is None
    assert len({s.context.trace_id for s in run.exporter.spans}) == 1


def test_content_defaults_on_and_the_hide_switches_remove_it(monkeypatch, fresh_otel):
    """Privacy: traceAI captures content by default; FI_HIDE_* removes it; the key values are never on a span."""

    async def scenario(run, env):
        await run.execute(env, AgentRequest(question=f"weather in Lisbon {MARKER}?"))

    on = run_scenario(monkeypatch, fresh_otel, scenario)
    text = dump(on.exporter.spans)
    assert MARKER in text
    for secret in (FIXTURE_FI_API_KEY, FIXTURE_FI_SECRET_KEY, FIXTURE_MODEL_KEY):  # R-08 / AC-08
        assert secret not in text

    for name in ("FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS", "FI_HIDE_INPUT_MESSAGES", "FI_HIDE_OUTPUT_MESSAGES", "FI_HIDE_LLM_INVOCATION_PARAMETERS"):
        monkeypatch.setenv(name, "true")
    off = run_scenario(monkeypatch, fresh_otel, scenario)
    text = dump(off.exporter.spans)
    assert MARKER not in text
    assert len(off.exporter.spans) == len(on.exporter.spans)


def test_the_workflow_id_is_the_only_thing_the_plugin_adds_about_the_application(monkeypatch, fresh_otel):
    """Temporal's own spans carry ids, not payloads: no workflow input, activity argument or result is on them."""

    async def scenario(run, env):
        await run.execute(env, AgentRequest(question=f"weather in Lisbon {MARKER}?"))

    run = run_scenario(monkeypatch, fresh_otel, scenario)
    for span in run.exporter.spans:
        if span.name.split(":")[0] in ("StartWorkflow", "RunWorkflow", "StartActivity", "RunActivity"):
            assert MARKER not in dump([span])
            assert set(span.attributes) <= {"temporalWorkflowID", "temporalRunID", "temporalActivityID", "temporalActivityType", "session.id"}


def test_sync_and_async_activities_both_nest_their_spans_under_run_activity(monkeypatch, fresh_otel):
    """Spans made inside a synchronous activity (run in a thread pool) are children of its RunActivity span too."""
    from concurrent.futures import ThreadPoolExecutor

    import sync_probe

    async def scenario(run, env):
        client = await Client.connect(env.client.service_client.config.target_host, plugins=[run.plugin()])
        queue = f"q-{uuid.uuid4().hex[:8]}"
        async with Worker(
            client, task_queue=queue, workflows=[sync_probe.ProbeWorkflow],
            activities=[sync_probe.sync_activity, sync_probe.async_activity], activity_executor=ThreadPoolExecutor(2),
        ):
            await client.execute_workflow(sync_probe.ProbeWorkflow.run, id=f"wf-{uuid.uuid4().hex[:8]}", task_queue=queue)
        run.provider.force_flush()

    run = run_scenario(monkeypatch, fresh_otel, scenario)
    by_id = {s.context.span_id: s for s in run.exporter.spans}
    parents = {s.name: by_id[s.parent.span_id].name for s in run.exporter.spans if s.parent}
    assert parents["inside-sync-activity"] == "RunActivity:sync_activity"
    assert parents["inside-async-activity"] == "RunActivity:async_activity"
    assert len({s.context.trace_id for s in run.exporter.spans}) == 1
