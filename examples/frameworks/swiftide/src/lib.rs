//! Send Swiftide's `tracing` spans to Future AGI over OTLP/HTTP.
//!
//! This is application code for the "Trace Swiftide" docs page, not a published crate.
//! Swiftide (0.33.0) instruments its agents with plain `tracing` spans (`agent.query`,
//! `step-N`, `complete`, `tool.<name>`, `add_message`). This file installs a
//! `tracing-opentelemetry` layer whose OTLP/HTTP exporter carries the Future AGI keys and
//! whose resource carries `project_name`. It does not use Swiftide's `langfuse` feature or
//! `LangfuseLayer`, which post to Langfuse's own API.
//!
//! Content capture is OFF by default: message text, tool arguments and results, log events
//! and error text are removed before export. Pass `capture_content: true` (the example binary
//! reads `TRACE_CONTENT=true`) to keep them.

use std::borrow::Cow;
use std::collections::HashMap;
use std::time::Duration;

use anyhow::{Context as _, Result};
use opentelemetry::trace::{Status, TracerProvider as _};
use opentelemetry::{Context, KeyValue, Value};
use opentelemetry_otlp::{Protocol, WithExportConfig, WithHttpConfig};
use opentelemetry_sdk::Resource;
use opentelemetry_sdk::error::OTelSdkResult;
use opentelemetry_sdk::trace::{
    BatchSpanProcessor, SdkTracerProvider, Span, SpanData, SpanEvents, SpanExporter, SpanProcessor,
};
use tracing::{Level, Metadata};
use tracing_subscriber::filter::{EnvFilter, FilterFn};
use tracing_subscriber::layer::SubscriberExt as _;
use tracing_subscriber::util::SubscriberInitExt as _;
use tracing_subscriber::{Layer as _, Registry};

/// Future AGI ingestion settings.
#[derive(Clone)]
pub struct Settings {
    /// Full OTLP/HTTP traces URL, for example `https://api.futureagi.com/tracer/v1/traces`.
    pub endpoint: String,
    pub api_key: String,
    pub secret_key: String,
    /// Observe project the spans land in (resource attribute `project_name`).
    pub project_name: String,
    /// `service.name` on the resource. Future AGI does not read it as a project name.
    pub service_name: String,
    /// Keep message text, tool arguments/results, log events and error text. Default: false.
    pub capture_content: bool,
}

impl std::fmt::Debug for Settings {
    // Never print the keys.
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Settings")
            .field("endpoint", &self.endpoint)
            .field("project_name", &self.project_name)
            .field("service_name", &self.service_name)
            .field("capture_content", &self.capture_content)
            .finish_non_exhaustive()
    }
}

impl Settings {
    /// Reads `FI_API_KEY`, `FI_SECRET_KEY`, `FI_PROJECT_NAME`, optional `FI_BASE_URL`
    /// (default `https://api.futureagi.com`) and optional `TRACE_CONTENT` (`true` to opt in).
    pub fn from_env() -> Result<Self> {
        let base =
            std::env::var("FI_BASE_URL").unwrap_or_else(|_| "https://api.futureagi.com".into());
        Ok(Self {
            endpoint: traces_endpoint(&base),
            api_key: std::env::var("FI_API_KEY").context("FI_API_KEY is not set")?,
            secret_key: std::env::var("FI_SECRET_KEY").context("FI_SECRET_KEY is not set")?,
            project_name: std::env::var("FI_PROJECT_NAME").context("FI_PROJECT_NAME is not set")?,
            service_name: std::env::var("OTEL_SERVICE_NAME")
                .unwrap_or_else(|_| "swiftide-agent".into()),
            capture_content: env_flag("TRACE_CONTENT"),
        })
    }
}

/// `https://api.futureagi.com` -> `https://api.futureagi.com/tracer/v1/traces`.
pub fn traces_endpoint(base_url: &str) -> String {
    format!("{}/tracer/v1/traces", base_url.trim_end_matches('/'))
}

fn env_flag(name: &str) -> bool {
    std::env::var(name).is_ok_and(|v| {
        matches!(
            v.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        )
    })
}

/// OTLP/HTTP protobuf exporter with both Future AGI headers. Uncompressed: the crate is built
/// without the `gzip-http` / `zstd-http` features.
pub fn otlp_exporter(settings: &Settings) -> Result<opentelemetry_otlp::SpanExporter> {
    let headers = HashMap::from([
        ("X-Api-Key".to_string(), settings.api_key.clone()),
        ("X-Secret-Key".to_string(), settings.secret_key.clone()),
    ]);
    opentelemetry_otlp::SpanExporter::builder()
        .with_http()
        .with_protocol(Protocol::HttpBinary)
        .with_endpoint(settings.endpoint.as_str())
        .with_headers(headers)
        .with_timeout(Duration::from_secs(10))
        .build()
        .context("building the OTLP span exporter")
}

/// The resource every span is exported with. `project_name` is required by Future AGI.
pub fn resource(settings: &Settings) -> Resource {
    Resource::builder()
        .with_service_name(settings.service_name.clone())
        .with_attributes([
            KeyValue::new("project_name", settings.project_name.clone()),
            KeyValue::new("project_type", "observe"),
        ])
        .build()
}

/// Tracer provider: batch export through [`ContentFilter`]. Call `shutdown()` before exit.
pub fn tracer_provider<E: SpanExporter + 'static>(
    settings: &Settings,
    exporter: E,
) -> SdkTracerProvider {
    let batch = BatchSpanProcessor::builder(exporter).build();
    SdkTracerProvider::builder()
        .with_span_processor(ContentFilter::new(batch, settings.capture_content))
        .with_resource(resource(settings))
        .build()
}

/// Which `tracing` spans and events reach the OpenTelemetry layer.
///
/// Spans: INFO and above, from every crate (Swiftide's agent spans are INFO).
/// Nothing from the OpenTelemetry crates themselves (their export-error logs stay on the console).
/// Events: content OFF -> ERROR only (they mark the span status ERROR; their text is removed by
/// [`ContentFilter`]). Content ON -> DEBUG and above from Swiftide (tool arguments and results,
/// the messages sent to the model), INFO and above elsewhere. TRACE is never exported: at that
/// level Swiftide logs whole provider requests and responses.
pub fn otel_filter(capture_content: bool) -> FilterFn<impl Fn(&Metadata<'_>) -> bool + Clone> {
    FilterFn::new(move |meta: &Metadata<'_>| {
        // The OpenTelemetry SDK's own log lines (export errors) go to the console only.
        if meta.target().starts_with("opentelemetry") {
            return false;
        }
        let level = *meta.level();
        if meta.is_span() {
            return level <= Level::INFO;
        }
        if !capture_content {
            return level == Level::ERROR;
        }
        if meta.target().starts_with("swiftide") {
            level <= Level::DEBUG
        } else {
            level <= Level::INFO
        }
    })
}

/// The `tracing-opentelemetry` layer for Future AGI, with the filter above.
pub fn otel_layer<S>(
    provider: &SdkTracerProvider,
    capture_content: bool,
) -> impl tracing_subscriber::Layer<S>
where
    S: tracing::Subscriber + for<'span> tracing_subscriber::registry::LookupSpan<'span>,
{
    tracing_opentelemetry::layer()
        .with_tracer(provider.tracer("swiftide-agent"))
        // code.file.path would carry absolute paths (home directory, user name) of every crate.
        .with_location(false)
        .with_threads(false)
        .with_filter(otel_filter(capture_content))
}

/// Installs the global `tracing` subscriber: the OpenTelemetry layer for Future AGI plus a
/// console `fmt` layer on stderr controlled by `RUST_LOG` (default `warn`). Returns the
/// provider; call `provider.shutdown()` after your agent finishes or the last batch is lost.
/// (The global subscriber keeps a reference to the provider, so dropping it does not flush.)
pub fn init_tracing(settings: &Settings) -> Result<SdkTracerProvider> {
    let provider = tracer_provider(settings, otlp_exporter(settings)?);
    let console = tracing_subscriber::fmt::layer()
        .with_writer(std::io::stderr)
        .with_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("warn")));
    Registry::default()
        .with(otel_layer(&provider, settings.capture_content))
        .with(console)
        .try_init()
        .context("a global tracing subscriber is already installed")?;
    Ok(provider)
}

/// Span attributes kept when content capture is off: timing (`busy_ns`, `idle_ns`), Swiftide's
/// `step_count`, and `target` (the Rust module that opened the span, e.g.
/// `swiftide_agents::agent`). Everything else is removed, including Swiftide's `message` field
/// on `add_message` (full chat message text), the local executor's `cmd`, and any `exception.*`
/// text. Add your own non-content keys with [`ContentFilter::allow_attribute`].
pub const DEFAULT_ALLOWED_ATTRIBUTES: &[&str] = &["busy_ns", "idle_ns", "step_count", "target"];

/// Status description used for failed spans when content capture is off.
pub const REDACTED_ERROR: &str = "error";

/// A [`SpanProcessor`] in front of the batch processor that removes content before export.
///
/// Content OFF (default): keeps the span name, timing, parent/child links and ERROR status;
/// keeps only allow-listed attributes; drops every span event (Swiftide's log lines carry
/// message text, tool arguments and results); replaces the error description.
/// Content ON: keeps everything except Rust backtraces (`Stack backtrace:` and what follows),
/// which carry local file paths.
#[derive(Debug)]
pub struct ContentFilter<P> {
    next: P,
    capture_content: bool,
    allowed: Vec<Cow<'static, str>>,
}

impl<P: SpanProcessor> ContentFilter<P> {
    pub fn new(next: P, capture_content: bool) -> Self {
        Self {
            next,
            capture_content,
            allowed: DEFAULT_ALLOWED_ATTRIBUTES
                .iter()
                .map(|k| Cow::Borrowed(*k))
                .collect(),
        }
    }

    /// Keep one more attribute key when content capture is off (for example `session.id`).
    pub fn allow_attribute(mut self, key: impl Into<Cow<'static, str>>) -> Self {
        self.allowed.push(key.into());
        self
    }

    fn filter(&self, mut span: SpanData) -> SpanData {
        if self.capture_content {
            for kv in span.attributes.iter_mut() {
                strip_backtrace_value(&mut kv.value);
            }
            for event in span.events.events.iter_mut() {
                for kv in event.attributes.iter_mut() {
                    strip_backtrace_value(&mut kv.value);
                }
            }
            if let Status::Error { description } = &span.status
                && let Cow::Owned(clean) = strip_backtrace(description)
            {
                span.status = Status::error(clean);
            }
            return span;
        }
        span.attributes
            .retain(|kv| self.allowed.iter().any(|k| k.as_ref() == kv.key.as_str()));
        span.dropped_attributes_count = 0;
        span.events = SpanEvents::default();
        if matches!(span.status, Status::Error { .. }) {
            span.status = Status::error(REDACTED_ERROR);
        }
        span
    }
}

impl<P: SpanProcessor> SpanProcessor for ContentFilter<P> {
    fn on_start(&self, span: &mut Span, cx: &Context) {
        self.next.on_start(span, cx);
    }

    fn on_end(&self, span: SpanData) {
        self.next.on_end(self.filter(span));
    }

    fn force_flush(&self) -> OTelSdkResult {
        self.next.force_flush()
    }

    fn shutdown_with_timeout(&self, timeout: Duration) -> OTelSdkResult {
        self.next.shutdown_with_timeout(timeout)
    }

    fn set_resource(&mut self, resource: &Resource) {
        self.next.set_resource(resource);
    }
}

/// Cuts a Rust backtrace (`anyhow`'s `Stack backtrace:` section) off a string.
pub fn strip_backtrace(text: &str) -> Cow<'_, str> {
    match text.find("Stack backtrace:") {
        Some(at) => Cow::Owned(text[..at].trim_end().to_string()),
        None => Cow::Borrowed(text),
    }
}

fn strip_backtrace_value(value: &mut Value) {
    if let Value::String(s) = value
        && let Cow::Owned(clean) = strip_backtrace(s.as_str())
    {
        *value = Value::String(clean.into());
    }
}
