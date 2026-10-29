# frozen_string_literal: true

# The real OTLP exporter against a WebMock stand-in for Future AGI: URL, both auth headers,
# no gzip, protobuf body with the project resource attributes.
require "helper"
require "opentelemetry/proto/collector/trace/v1/trace_service_pb"

ENV["FI_API_KEY"] = "key-123"
ENV["FI_SECRET_KEY"] = "secret-456"
ENV["FI_BASE_URL"] = "https://fi.example.test"
FutureAGITracing.setup(project_name: "wire-project", capture_content: false, batch: true, flush_at_exit: false) # batch: spans leave only on flush/shutdown

class WireTest < Minitest::Test
  def test_export_request_shape
    stub = WebMock.stub_request(:post, "https://fi.example.test/tracer/v1/traces").to_return(status: 200, body: "")
    FakeOpenAI.stub_chat(FakeOpenAI.completion(content: "WIREREPLY-MARKER"))
    new_chat.ask("WIREPROMPT-MARKER")
    FutureAGITracing.shutdown
    FutureAGITracing.shutdown # second call is a no-op
    assert_requested stub, times: 1
    req = nil
    assert_requested(:post, "https://fi.example.test/tracer/v1/traces") { |r| req = r }
    assert_equal "key-123", req.headers["X-Api-Key"]
    assert_equal "secret-456", req.headers["X-Secret-Key"]
    assert_nil req.headers["Content-Encoding"], "body must not be gzipped"
    assert_match %r{application/x-protobuf}, req.headers["Content-Type"]
    decoded = Opentelemetry::Proto::Collector::Trace::V1::ExportTraceServiceRequest.decode(req.body)
    resource = decoded.resource_spans.first.resource.attributes.to_h { |kv| [kv.key, kv.value.string_value] }
    assert_equal "wire-project", resource["project_name"]
    assert_equal "observe", resource["project_type"]
    span = decoded.resource_spans.first.scope_spans.first.spans.first
    assert_equal "chat fake-model", span.name
    refute_includes req.body, "WIREPROMPT-MARKER"
    refute_includes req.body, "WIREREPLY-MARKER"
  end
end
