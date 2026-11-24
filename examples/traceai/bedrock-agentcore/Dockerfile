# Build for linux/arm64 for AgentCore Runtime. No ADOT startup wrapper.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_SYSTEM_PYTHON=1 UV_COMPILE_BYTECODE=1 UV_NO_PROGRESS=1 PYTHONUNBUFFERED=1 DOCKER_CONTAINER=1
COPY requirements.txt requirements.txt
RUN uv pip install -r requirements.txt
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore
EXPOSE 8080
COPY agent_langchain.py agent_strands.py ./
CMD ["python", "-m", "agent_langchain"]
