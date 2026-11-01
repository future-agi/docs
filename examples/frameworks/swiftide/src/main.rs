//! A Swiftide agent using standard Rust OpenTelemetry setup and a loopback Collector.
//! Start collector.yaml first; the Collector owns Future AGI credentials and redaction.

use anyhow::Result;
use opentelemetry::trace::TracerProvider as _;
use opentelemetry_otlp::{Protocol, WithExportConfig};
use opentelemetry_sdk::{Resource, trace::SdkTracerProvider};
use swiftide::agents::Agent;
use swiftide::chat_completion::{ToolOutput, errors::ToolError};
use swiftide::integrations::openai::{OpenAI, OpenAIConfig};
use swiftide::traits::AgentContext;
use tracing_subscriber::{EnvFilter, layer::SubscriberExt as _, util::SubscriberInitExt as _};

#[swiftide::tool(
    description = "Get the current weather for a city",
    param(name = "city", description = "The city name, for example Paris")
)]
async fn get_weather(_context: &dyn AgentContext, city: &str) -> Result<ToolOutput, ToolError> {
    match city.to_lowercase().as_str() {
        "paris" => Ok("Paris: 18C, light rain".into()),
        "tokyo" => Ok("Tokyo: 24C, clear".into()),
        _ => {
            // Swiftide recovers from tool failures. Mark this tool span explicitly.
            tracing::error!("weather lookup failed");
            Err(ToolError::Unknown(anyhow::anyhow!("unknown city: {city}")))
        }
    }
}

async fn run_agent(question: String) -> Result<()> {
    let mut config = OpenAIConfig::new().with_api_key(std::env::var("OPENAI_API_KEY")?);
    if let Ok(base_url) = std::env::var("OPENAI_BASE_URL") {
        config = config.with_api_base(base_url);
    }
    let openai = OpenAI::builder()
        .client(async_openai::Client::with_config(config))
        .default_prompt_model(std::env::var("MODEL").unwrap_or_else(|_| "gpt-4o-mini".into()))
        .build()?;
    let mut agent = Agent::builder()
        .llm(&openai)
        .tools(vec![get_weather()])
        .limit(4)
        .build()?;
    agent.query(question).await?;
    Ok(())
}

fn main() -> Result<()> {
    // Raw fields go only to the local Collector, never directly to Future AGI.
    let exporter = opentelemetry_otlp::SpanExporter::builder()
        .with_http()
        .with_protocol(Protocol::HttpBinary)
        .with_endpoint("http://127.0.0.1:4318/v1/traces")
        .build()?;
    let provider = SdkTracerProvider::builder()
        .with_batch_exporter(exporter)
        .with_resource(
            Resource::builder()
                .with_service_name("swiftide-agent")
                .build(),
        )
        .build();
    tracing_subscriber::registry()
        .with(EnvFilter::new(
            "info,swiftide_agents=debug,swiftide_integrations=debug",
        ))
        .with(
            tracing_opentelemetry::layer()
                .with_tracer(provider.tracer("swiftide-agent"))
                .with_location(false)
                .with_threads(false),
        )
        .try_init()?;

    let question = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "What is the weather in Paris?".into());
    let runtime = tokio::runtime::Runtime::new()?;
    let outcome = runtime.block_on(run_agent(question));
    drop(runtime);
    // Flush even when the agent fails; keep shutdown outside the async runtime.
    if let Err(err) = provider.shutdown() {
        eprintln!("tracer shutdown: {err}");
    }
    outcome
}
