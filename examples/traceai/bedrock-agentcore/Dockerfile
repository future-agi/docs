# Same shape as the Dockerfile that `agentcore configure --entrypoint agent_langchain.py --disable-otel`
# writes (bedrock-agentcore-starter-toolkit 0.3.14, Python 3.12): no aws-opentelemetry-distro and
# no `opentelemetry-instrument` wrapper, because traces go to Future AGI, not to CloudWatch.
# Used here to run the example in the runtime's container shape (arm64, port 8080, uid 1000).
# Future AGI keys are passed at run time (`docker run -e ...`, or `agentcore launch --env ...`),
# never baked into the image.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1

COPY requirements.txt requirements.txt
RUN uv pip install -r requirements.txt

RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 8080

COPY agentcore_tracing.py agent_langchain.py agent_strands.py ./

CMD ["python", "-m", "agent_langchain"]
