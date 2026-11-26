# NVIDIA NeMo Agent Toolkit → Future AGI

Development fixtures for the source-fork proposal. This is not a released or supported customer setup. See the status page
[NVIDIA NeMo Agent Toolkit tracing](https://docs.futureagi.com/docs/integrations/frameworks/nvidia-nemo-agent-toolkit).

The `futureagi` trace exporter is part of the toolkit's `nvidia-nat-opentelemetry` package on the
`feat/futureagi-tracing-exporter` branch of
[future-agi/NeMo-Agent-Toolkit](https://github.com/future-agi/NeMo-Agent-Toolkit/pull/1) (not yet in an NVIDIA release).
This folder holds no exporter code, only a workflow config and an end-to-end script.

| File | What it is |
| --- | --- |
| `config-futureagi.yml` | The toolkit's calculator `react_agent` workflow with the `futureagi` exporter. The model endpoint comes from `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` (default: NVIDIA-hosted NIM). |
| `run_e2e.sh` | Clones the branch (or uses `NAT_SRC`), installs it with uv, runs the exporter's tests, then runs the workflow four times: HTTP, gRPC, with `FI_HIDE_INPUTS`/`FI_HIDE_OUTPUTS`, and with a wrong secret key. |



Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and [Git LFS](https://git-lfs.com/). The script prints what to
check in Observe for each project. The exporter's unit and receiver tests live in the toolkit fork
(`packages/nvidia_nat_opentelemetry/tests/observability/test_futureagi_*.py`).

Tested 2026-10-16 against a self-hosted Future AGI with the branch's exporter commits on NAT `v1.9.0`, NAT `develop`
`c7e1162` (the branch base) and NAT `develop` `26410de`.
