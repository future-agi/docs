"""R-06: workflow code does not import the exporter or the model SDK, and the workflow sandbox loads it."""
import ast
import asyncio
import os

from temporalio import workflow
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

import workflows

ALLOWED_TOP_LEVEL = {"dataclasses", "datetime", "temporalio"}
FORBIDDEN = {"opentelemetry", "fi_instrumentation", "traceai_openai", "openai", "httpx", "requests", "tracing", "activities", "os", "socket"}


def imported_modules(path: str) -> set[str]:
    tree = ast.parse(open(path).read())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_workflow_module_imports_only_temporal_and_the_standard_library():
    modules = imported_modules(workflows.__file__)
    assert modules <= ALLOWED_TOP_LEVEL, modules - ALLOWED_TOP_LEVEL
    assert not modules & FORBIDDEN


def test_the_activities_are_referenced_by_name_not_imported():
    source = open(workflows.__file__).read()
    assert '"llm_plan"' in source and '"get_weather"' in source and '"llm_answer"' in source
    assert "activities" not in imported_modules(workflows.__file__)


def test_the_workflow_sandbox_loads_the_workflow_module():
    # Worker(...) does exactly this for every workflow; it raises "Failed validating workflow" otherwise.
    definition = workflow._Definition.must_from_class(workflows.WeatherAgentWorkflow)

    async def prepare() -> None:
        SandboxedWorkflowRunner().prepare_workflow(definition)

    asyncio.run(prepare())


def test_tracing_is_not_importable_from_the_workflow_file_path():
    here = os.path.dirname(workflows.__file__)
    assert os.path.exists(os.path.join(here, "tracing.py"))
    assert "tracing" not in imported_modules(workflows.__file__)
