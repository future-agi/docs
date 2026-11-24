# AgentCore Runtime tracing

Run the [AgentCore guide](https://docs.futureagi.com/docs/integrations/traceai/bedrock-agentcore) with released packages, without a copied exporter or tracing bridge.

- `agent_langchain.py`: LangChain instrumentation from `traceAI-langchain`, a session scope and an invocation span from `fi-instrumentation-otel`.
- `agent_strands.py`: Strands' native OTLP exporter and per-agent session attributes.
- `deploy.py`: pinned starter-toolkit deployment, with ADOT disabled. It creates billable AWS resources; use an authorized AWS account.
- `Dockerfile`: application image without `opentelemetry-instrument`. Build for `linux/arm64` for AgentCore.

Install `requirements.txt`, load your model and Future AGI keys from your secret store, then follow the guide's environment configuration. Set `FI_HIDE_INPUTS=true`, `FI_HIDE_OUTPUTS=true` and `FI_HIDE_ERROR_DETAILS=true` for the LangChain example before startup. The packages capture content without those settings. Strands' content redaction does **not** remove exception messages or stack traces; `FI_HIDE_*` does not apply to native Strands spans.

Run `python agent_langchain.py` (or `python agent_strands.py`) to serve `/invocations` and `/ping` on port 8080. Both examples return JSON, start a new trace per request and flush before returning. They do not join incoming caller traces. Use opaque session identifiers and keep secrets out of span names, custom attributes and application logs.

For deployment, install `requirements-deploy.txt` and run `python deploy.py`. The script defaults to LangChain; select Strands with `AGENT_ENTRYPOINT=agent_strands.py`. AWS recommends the newer AgentCore CLI for new deployments; the included script specifically uses the pinned starter toolkit's Python API.

## Contract tests

Run tests in an isolated test environment with synthetic credentials:

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q tests/test_deploy_contract.py tests/test_native.py
```

The historical regression suite under `tests/legacy` has its own dependency pins. Run it in a **separate** environment:

```bash
python -m pip install -r tests/legacy/requirements-test.txt
python -m pytest -q tests/legacy/tests
```

Historical fixtures preserve tests for the old exporter and streaming behavior. They are not application examples: never copy their helper or import it into a current agent. Current releases retain the exporter without that workaround; adding it produces duplicate exports.
