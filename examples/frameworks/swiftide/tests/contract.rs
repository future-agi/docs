//! Contract tests: a real Swiftide agent against a mock OpenAI-compatible server, spans captured
//! in memory through the same layer, filter and `ContentFilter` the example ships. No network
//! beyond 127.0.0.1, no Future AGI, no model provider.

use opentelemetry::trace::{SpanId, Status};
use opentelemetry_sdk::trace::{InMemorySpanExporter, SdkTracerProvider, SpanData};
use serde_json::json;
use swiftide::agents::Agent;
use swiftide::chat_completion::ToolOutput;
use swiftide::chat_completion::errors::ToolError;
use swiftide::integrations::openai::{OpenAI, OpenAIConfig};
use swiftide::traits::AgentContext;
use swiftide_futureagi_tracing::{
    DEFAULT_ALLOWED_ATTRIBUTES, REDACTED_ERROR, Settings, otel_layer, strip_backtrace,
    tracer_provider,
};
use tracing_subscriber::layer::SubscriberExt as _;
use wiremock::matchers::{body_partial_json, method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

const MARKER: &str = "MRK-7f3a9c-swiftide";
const FIXTURE_KEY: &str = "sk-fixture-4b1d-DO-NOT-EXPORT";

#[swiftide::tool(
    description = "Get the current weather for a city",
    param(name = "city", description = "The city name")
)]
async fn get_weather(_context: &dyn AgentContext, city: &str) -> Result<ToolOutput, ToolError> {
    if city.starts_with("Paris") {
        Ok(format!("{city}: 18C light rain {MARKER}-tool-result").into())
    } else {
        tracing::error!("weather lookup failed");
        Err(ToolError::Unknown(anyhow::anyhow!(
            "no weather data for {city}"
        )))
    }
}

fn settings(capture_content: bool) -> Settings {
    Settings {
        endpoint: "http://127.0.0.1:9/unused".into(),
        api_key: "fi-api-fixture".into(),
        secret_key: "fi-secret-fixture".into(),
        project_name: "contract-test".into(),
        service_name: "contract-test".into(),
        capture_content,
    }
}

fn completion(message: serde_json::Value, finish: &str) -> serde_json::Value {
    json!({
        "id": "chatcmpl-fixture", "object": "chat.completion", "created": 1, "model": "mock-model",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 21, "completion_tokens": 7, "total_tokens": 28}
    })
}

fn tool_call(city: &str) -> serde_json::Value {
    completion(
        json!({"role": "assistant", "content": null, "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": "get_weather", "arguments": json!({"city": city}).to_string()}
        }]}),
        "tool_calls",
    )
}

async fn mock_openai(city: &str) -> MockServer {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/chat/completions"))
        .and(body_partial_json(json!({"model": "broken-model"})))
        .respond_with(ResponseTemplate::new(400).set_body_json(json!({"error": {
            "message": format!("unknown model {MARKER}-provider-error"),
            "type": "invalid_request_error", "param": "model", "code": "model_not_found"
        }})))
        .mount(&server)
        .await;
    Mock::given(method("POST"))
        .and(path("/chat/completions"))
        .respond_with(ResponseTemplate::new(200).set_body_json(tool_call(city)))
        .up_to_n_times(1)
        .mount(&server)
        .await;
    Mock::given(method("POST"))
        .and(path("/chat/completions"))
        .respond_with(ResponseTemplate::new(200).set_body_json(completion(
            json!({"role": "assistant", "content": format!("It is 18C in Paris. {MARKER}-answer")}),
            "stop",
        )))
        .mount(&server)
        .await;
    server
}

struct Run {
    spans: Vec<SpanData>,
    ok: bool,
}

/// Runs one agent query on a current-thread runtime (so tool tasks stay on this thread and the
/// scoped subscriber applies to them), then flushes the provider.
fn run(capture_content: bool, model: &str, city: &str) -> Run {
    let exporter = InMemorySpanExporter::default();
    let provider: SdkTracerProvider = tracer_provider(&settings(capture_content), exporter.clone());
    let subscriber = tracing_subscriber::registry().with(otel_layer(&provider, capture_content));
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let ok = tracing::subscriber::with_default(subscriber, || {
        rt.block_on(async {
            let server = mock_openai(city).await;
            let client = async_openai::Client::with_config(
                OpenAIConfig::new()
                    .with_api_base(server.uri())
                    .with_api_key(FIXTURE_KEY),
            );
            let openai = OpenAI::builder()
                .client(client)
                .default_prompt_model(model)
                .build()
                .unwrap();
            let mut agent = Agent::builder()
                .llm(&openai)
                .tools(vec![get_weather()])
                .limit(3)
                .build()
                .unwrap();
            agent
                .query(format!("{MARKER}-question: what is the weather in {city}?"))
                .await
                .is_ok()
        })
    });
    provider.force_flush().unwrap();
    let spans = exporter.get_finished_spans().unwrap();
    provider.shutdown().unwrap();
    Run { spans, ok }
}

fn by_name<'a>(spans: &'a [SpanData], name: &str) -> Vec<&'a SpanData> {
    spans.iter().filter(|s| s.name == name).collect()
}

fn dump(spans: &[SpanData]) -> String {
    format!("{spans:?}")
}

#[test]
fn span_tree_matches_swiftide_0_33() {
    let run = run(false, "mock-model", "Paris");
    assert!(run.ok);
    let spans = &run.spans;
    let root = by_name(spans, "agent.query");
    assert_eq!(
        root.len(),
        1,
        "one agent.query span: {:?}",
        spans.iter().map(|s| &s.name).collect::<Vec<_>>()
    );
    let root = root[0];
    assert_eq!(
        root.parent_span_id,
        SpanId::INVALID,
        "agent.query is the root"
    );
    assert!(
        spans
            .iter()
            .all(|s| s.span_context.trace_id() == root.span_context.trace_id()),
        "one trace"
    );

    let steps = by_name(spans, "step");
    assert_eq!(steps.len(), 2, "tool-call turn + answer turn");
    assert!(
        steps
            .iter()
            .all(|s| s.parent_span_id == root.span_context.span_id())
    );
    let step_ids: Vec<_> = steps.iter().map(|s| s.span_context.span_id()).collect();

    let completes = by_name(spans, "complete");
    assert_eq!(completes.len(), 2, "one `complete` span per model call");
    assert!(
        completes
            .iter()
            .all(|s| step_ids.contains(&s.parent_span_id))
    );

    let tools = by_name(spans, "tool.get_weather");
    assert_eq!(tools.len(), 1);
    assert!(
        step_ids.contains(&tools[0].parent_span_id),
        "tool span is a child of its step"
    );
    assert!(
        spans.iter().all(|s| s.status == Status::Unset),
        "no errors on the happy path"
    );
}

#[test]
fn content_off_removes_text_attributes_events_and_error_text() {
    for (model, city) in [
        ("mock-model", "Paris"),
        ("mock-model", "Atlantis"),
        ("broken-model", "Paris"),
    ] {
        let run = run(false, model, city);
        let text = dump(&run.spans);
        assert!(
            !text.contains(MARKER),
            "marker exported with content off ({model}, {city})"
        );
        assert!(!text.contains(FIXTURE_KEY), "provider key exported");
        for span in &run.spans {
            assert!(
                span.events.is_empty(),
                "span events exported with content off: {}",
                span.name
            );
            for kv in &span.attributes {
                assert!(
                    DEFAULT_ALLOWED_ATTRIBUTES.contains(&kv.key.as_str()),
                    "unexpected attribute {} on {}",
                    kv.key,
                    span.name
                );
            }
            if let Status::Error { description } = &span.status {
                assert_eq!(description, REDACTED_ERROR);
            }
        }
    }
}

#[test]
fn failures_are_error_status() {
    let model_error = run(false, "broken-model", "Paris");
    assert!(!model_error.ok);
    for name in ["agent.query", "step", "complete"] {
        let span = by_name(&model_error.spans, name)[0];
        assert!(
            matches!(span.status, Status::Error { .. }),
            "{name} should be ERROR"
        );
    }
    let tool_error = run(false, "mock-model", "Atlantis");
    let tool = by_name(&tool_error.spans, "tool.get_weather")[0];
    assert!(
        matches!(tool.status, Status::Error { .. }),
        "tool span ERROR via the tool's error event"
    );
}

#[test]
fn content_on_keeps_text_but_never_the_provider_key() {
    let run = run(true, "mock-model", "Paris");
    let text = dump(&run.spans);
    assert!(
        text.contains(&format!("{MARKER}-question")),
        "prompt text kept with content on"
    );
    assert!(
        text.contains(&format!("{MARKER}-tool-result")),
        "tool result kept with content on"
    );
    assert!(
        text.contains(&format!("{MARKER}-answer")),
        "answer kept with content on"
    );
    assert!(
        !text.contains(FIXTURE_KEY),
        "provider key exported with content on"
    );

    let failed = run_content_on_failure();
    assert!(
        failed.contains(&format!("{MARKER}-provider-error")),
        "error text kept with content on"
    );
}

fn run_content_on_failure() -> String {
    dump(&run(true, "broken-model", "Paris").spans)
}

#[test]
fn langfuse_is_not_compiled_in() {
    let lock = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/Cargo.lock")).unwrap();
    assert!(
        !lock.contains("name = \"swiftide-langfuse\""),
        "swiftide-langfuse must not be in the build"
    );
    let manifest =
        std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/Cargo.toml")).unwrap();
    let deps = manifest.split("[dev-dependencies]").next().unwrap();
    assert!(
        !deps.contains("\"langfuse\""),
        "the langfuse feature must not be enabled"
    );
    for compression in ["gzip-http", "zstd-http", "grpc-tonic"] {
        assert!(
            !deps.contains(compression),
            "{compression} must not be enabled"
        );
    }
}

#[test]
fn backtraces_are_cut() {
    let text = "boom\n\nStack backtrace:\n   0: /Users/someone/.cargo/registry/src/x.rs:1";
    assert_eq!(strip_backtrace(text), "boom");
    assert_eq!(strip_backtrace("no backtrace here"), "no backtrace here");
}

#[test]
fn settings_debug_hides_keys() {
    let printed = format!("{:?}", settings(false));
    assert!(!printed.contains("fi-api-fixture") && !printed.contains("fi-secret-fixture"));
}

#[test]
fn endpoint_is_built_from_the_base_url() {
    assert_eq!(
        swiftide_futureagi_tracing::traces_endpoint("https://api.futureagi.com/"),
        "https://api.futureagi.com/tracer/v1/traces"
    );
}
