//! The real OTLP/HTTP exporter against a local receiver: headers, encoding, resource, and the
//! flush-on-shutdown requirement (PRD AC-05). No Future AGI involved.

use std::time::Duration;

use opentelemetry_proto::tonic::collector::trace::v1::ExportTraceServiceRequest;
use opentelemetry_sdk::trace::SdkTracerProvider;
use prost::Message as _;
use swiftide_futureagi_tracing::{Settings, otel_layer, otlp_exporter, tracer_provider};
use tracing_subscriber::layer::SubscriberExt as _;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

struct Receiver {
    rt: tokio::runtime::Runtime,
    server: MockServer,
}

impl Receiver {
    fn start() -> Self {
        let rt = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(1)
            .enable_all()
            .build()
            .unwrap();
        let server = rt.block_on(async {
            let server = MockServer::start().await;
            Mock::given(method("POST"))
                .and(path("/tracer/v1/traces"))
                .respond_with(ResponseTemplate::new(200))
                .mount(&server)
                .await;
            server
        });
        Self { rt, server }
    }

    fn requests(&self) -> Vec<wiremock::Request> {
        self.rt
            .block_on(self.server.received_requests())
            .unwrap_or_default()
    }

    fn settings(&self) -> Settings {
        Settings {
            endpoint: format!("{}/tracer/v1/traces", self.server.uri()),
            api_key: "fi-api-fixture".into(),
            secret_key: "fi-secret-fixture".into(),
            project_name: "export-test".into(),
            service_name: "export-test".into(),
            capture_content: false,
        }
    }
}

fn emit_spans(provider: &SdkTracerProvider) {
    let subscriber = tracing_subscriber::registry().with(otel_layer(provider, false));
    tracing::subscriber::with_default(subscriber, || {
        let root = tracing::info_span!("agent.query");
        let _g = root.enter();
        tracing::info_span!("step", step_count = 0).in_scope(|| {});
    });
}

#[test]
fn shutdown_flushes_one_uncompressed_protobuf_request_with_both_headers() {
    let receiver = Receiver::start();
    let settings = receiver.settings();
    let provider = tracer_provider(&settings, otlp_exporter(&settings).unwrap());
    emit_spans(&provider);
    provider.shutdown().unwrap();

    let requests = receiver.requests();
    assert_eq!(requests.len(), 1, "one batch on shutdown");
    let req = &requests[0];
    let header = |name: &str| {
        req.headers
            .get(name)
            .map(|v| v.to_str().unwrap().to_string())
    };
    assert_eq!(header("x-api-key").as_deref(), Some("fi-api-fixture"));
    assert_eq!(header("x-secret-key").as_deref(), Some("fi-secret-fixture"));
    assert_eq!(
        header("content-type").as_deref(),
        Some("application/x-protobuf")
    );
    assert_eq!(
        header("content-encoding"),
        None,
        "the body must be uncompressed"
    );

    let body = ExportTraceServiceRequest::decode(req.body.as_slice()).expect("OTLP protobuf body");
    assert_eq!(body.resource_spans.len(), 1);
    let resource = body.resource_spans[0].resource.as_ref().unwrap();
    let attr = |key: &str| {
        resource
            .attributes
            .iter()
            .find(|kv| kv.key == key)
            .and_then(|kv| kv.value.as_ref())
            .map(|v| format!("{:?}", v.value))
    };
    assert!(attr("project_name").unwrap().contains("export-test"));
    assert!(attr("project_type").unwrap().contains("observe"));
    let names: Vec<_> = body.resource_spans[0]
        .scope_spans
        .iter()
        .flat_map(|s| s.spans.iter().map(|sp| sp.name.clone()))
        .collect();
    assert_eq!(names.len(), 2, "{names:?}");
    assert!(names.contains(&"agent.query".to_string()));
}

#[test]
fn without_shutdown_nothing_is_sent_before_the_batch_delay() {
    // PRD AC-05. The global subscriber holds a reference to the provider, so a program that
    // forgets `shutdown()` exits with the batch still in memory. Here: no request within 2 s
    // (the default batch delay is 5 s); `run_e2e.sh no-shutdown` shows the loss at process exit.
    let receiver = Receiver::start();
    let settings = receiver.settings();
    let provider = tracer_provider(&settings, otlp_exporter(&settings).unwrap());
    let kept_alive = provider.clone();
    emit_spans(&provider);
    std::thread::sleep(Duration::from_secs(2));
    assert!(
        receiver.requests().is_empty(),
        "nothing exported without shutdown"
    );
    kept_alive.shutdown().unwrap();
    assert_eq!(
        receiver.requests().len(),
        1,
        "shutdown exports the pending batch"
    );
}

#[test]
fn exporter_failure_does_not_panic() {
    // PRD J5: nothing listens on port 9; export fails, shutdown returns, no panic.
    let settings = Settings {
        endpoint: "http://127.0.0.1:9/tracer/v1/traces".into(),
        api_key: "a".into(),
        secret_key: "b".into(),
        project_name: "p".into(),
        service_name: "s".into(),
        capture_content: false,
    };
    let provider = tracer_provider(&settings, otlp_exporter(&settings).unwrap());
    emit_spans(&provider);
    let _ = provider.shutdown();
}
