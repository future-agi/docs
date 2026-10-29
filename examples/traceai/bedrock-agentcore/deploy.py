import os
from bedrock_agentcore_starter_toolkit import Runtime

# Read required secrets before creating any AWS resources.
api_key = os.environ["FI_API_KEY"]
secret_key = os.environ["FI_SECRET_KEY"]
model_key = os.environ["OPENAI_API_KEY"]
entrypoint = os.environ.get("AGENT_ENTRYPOINT", "agent_strands.py")
if entrypoint not in {"agent_strands.py", "agent_langchain.py"}:
    raise ValueError("Choose agent_strands.py or agent_langchain.py")
base_url = os.environ.get("FI_BASE_URL", "https://api.futureagi.com").rstrip("/")
project = os.environ.get("FI_PROJECT_NAME", "order-agent")
env_vars = {
    "DISABLE_ADOT_OBSERVABILITY": "true",
    "OPENAI_API_KEY": model_key,
    "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "AGENT_MODEL": os.environ.get("AGENT_MODEL", "gpt-4o-mini"),
}
if entrypoint == "agent_langchain.py":
    env_vars.update(FI_API_KEY=api_key, FI_SECRET_KEY=secret_key,
                    FI_BASE_URL=base_url, FI_PROJECT_NAME=project)
else:
    env_vars.update({
        "OTEL_EXPORTER_OTLP_ENDPOINT": base_url,
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": base_url + "/tracer/v1/traces",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_HEADERS": f"X-Api-Key={api_key},X-Secret-Key={secret_key}",
        "OTEL_RESOURCE_ATTRIBUTES": f"project_name={project},project_type=observe",
        "OTEL_SERVICE_NAME": "order-agent",
        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental,gen_ai_span_attributes_only,gen_ai_unredacted_attributes=",
    })

runtime = Runtime()
runtime.configure(
    entrypoint=entrypoint,
    agent_name="order_agent",
    requirements_file="requirements.txt",
    auto_create_execution_role=True,
    auto_create_ecr=True,
    region=os.environ.get("AWS_REGION", "us-west-2"),
    disable_otel=True,
)
runtime.launch(env_vars=env_vars)
