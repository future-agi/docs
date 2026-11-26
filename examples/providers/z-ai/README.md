# Z.ai tracing example

This example traces Z.ai general-platform chat completions using the OpenAI Python client and `traceAI-openai`. Follow the [Z.ai integration guide](../../../src/pages/docs/integrations/providers/z-ai.mdx) for the minimal setup, privacy settings, and result view. Python 3.10–3.13 is supported by the pinned instrumentor.

`app.py` also demonstrates streaming, tool calls, and errors. To run those scenarios, set `FI_API_KEY`, `FI_SECRET_KEY`, `ZAI_API_KEY`, and `ZAI_MODEL`, install `requirements.txt`, then run `python app.py --help` for options. Set `FI_BASE_URL` to your collector origin if self-hosted. Requests sent to Z.ai may incur charges.

The `tests/` directory uses a local Z.ai-shaped stand-in and a recording OTLP receiver. `run_e2e.sh` creates a virtual environment, runs the tests, and then runs the app against a collector; it uses the stand-in when `ZAI_API_KEY` is absent and calls Z.ai when that key is set. It defaults to a local collector at `http://localhost:4318`. A Coding Plan base URL is rejected by the example app; refer to Z.ai's Coding Plan documentation for its endpoint and quota rules.
