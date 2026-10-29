//! A Swiftide agent with one tool, traced to Future AGI.
//!
//!   FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=my-swiftide-app \
//!   OPENAI_API_KEY=... [OPENAI_BASE_URL=...] [MODEL=gpt-4o-mini] [TRACE_CONTENT=true] \
//!   cargo run -- "What is the weather in Paris?"
//!
//! Exit code 0 when the agent finished, 1 when it failed. Spans are flushed either way.

use anyhow::Result;
use swiftide::agents::Agent;
use swiftide::chat_completion::ToolOutput;
use swiftide::chat_completion::errors::ToolError;
use swiftide::integrations::openai::{OpenAI, OpenAIConfig};
use swiftide::traits::AgentContext;
use swiftide_futureagi_tracing::{Settings, init_tracing};

/// Cities the demo weather service knows. Anything else is a tool error.
const KNOWN: &[(&str, &str)] = &[
    ("paris", "18°C, light rain"),
    ("tokyo", "24°C, clear"),
    ("lisbon", "22°C, sunny"),
];

#[swiftide::tool(
    description = "Get the current weather for a city",
    param(name = "city", description = "The city name, for example Paris")
)]
async fn get_weather(_context: &dyn AgentContext, city: &str) -> Result<ToolOutput, ToolError> {
    match KNOWN
        .iter()
        .find(|(name, _)| city.trim().eq_ignore_ascii_case(name))
    {
        Some((_, weather)) => Ok(format!("{city}: {weather}").into()),
        None => {
            // Swiftide does not mark a failed tool's span as an error. An ERROR-level event inside
            // the tool does (the tool runs inside the `tool.get_weather` span).
            tracing::error!("weather lookup failed");
            Err(ToolError::Unknown(anyhow::anyhow!(
                "no weather data for {city}"
            )))
        }
    }
}

/// The model client. The endpoint is set explicitly: not every async-openai release reads
/// `OPENAI_BASE_URL` (0.30, used by swiftide 0.32, does not and falls back to api.openai.com).
fn model_client(model: String) -> Result<OpenAI> {
    let mut config = OpenAIConfig::new().with_api_key(std::env::var("OPENAI_API_KEY")?);
    if let Ok(base_url) = std::env::var("OPENAI_BASE_URL") {
        config = config.with_api_base(base_url);
    }
    Ok(OpenAI::builder()
        .client(async_openai::Client::with_config(config))
        .default_prompt_model(model)
        .build()?)
}

async fn run_agent(question: String, model: String) -> Result<()> {
    let openai = model_client(model)?;
    let mut agent = Agent::builder()
        .llm(&openai)
        .tools(vec![get_weather()])
        .limit(4)
        .build()?;
    agent.query(question).await?;
    if let Some(answer) = agent.history().await?.iter().rev().find_map(|m| match m {
        swiftide::chat_completion::ChatMessage::Assistant(Some(text), _) => Some(text.clone()),
        _ => None,
    }) {
        println!("{answer}");
    }
    Ok(())
}

fn main() -> Result<()> {
    let settings = Settings::from_env()?;
    let question = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "What is the weather in Paris right now?".to_string());
    let model = std::env::var("MODEL").unwrap_or_else(|_| "gpt-4o-mini".to_string());

    let provider = init_tracing(&settings)?;

    let runtime = tokio::runtime::Runtime::new()?;
    let outcome = runtime.block_on(run_agent(question, model));
    drop(runtime);

    // Flush the last batch. Without this the spans still in the batch are lost on exit.
    // (SKIP_SHUTDOWN=1 only exists for run_e2e.sh, to show that loss.)
    let skip_shutdown = std::env::var("SKIP_SHUTDOWN").as_deref() == Ok("1");
    if !skip_shutdown && let Err(err) = provider.shutdown() {
        eprintln!("tracer shutdown: {err}");
    }

    if let Err(err) = &outcome {
        eprintln!("agent failed: {err}");
        std::process::exit(1);
    }
    Ok(())
}
