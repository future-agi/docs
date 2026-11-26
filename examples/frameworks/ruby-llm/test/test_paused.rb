# frozen_string_literal: true

# Separate process: a restart must remove the old patch, not reinstall it.
require "bundler/setup"
require "minitest/autorun"
require "webmock/minitest"
require "json"
require "ruby_llm"
require "opentelemetry/sdk"

WebMock.disable_net_connect!

class PausedLegacyTest < Minitest::Test
  def test_documented_session_runs_without_the_instrumentation_or_exports
    page = File.read(File.expand_path("../../../../src/pages/docs/integrations/frameworks/ruby-llm.mdx", __dir__))
    snippet = page[/```ruby title="legacy-paused.rb"\n(.*?)```/m, 1]
    refute_nil snippet, "The pause procedure needs a runnable replacement for the old session chain"

    # A shared provider can remain active for unrelated integrations.
    exporter = OpenTelemetry::SDK::Trace::Export::InMemorySpanExporter.new
    OpenTelemetry::SDK.configure do |config|
      config.add_span_processor(OpenTelemetry::SDK::Trace::Export::SimpleSpanProcessor.new(exporter))
    end
    ENV["OPENAI_API_KEY"] = "synthetic-openai-key"
    requests = []
    stub_request(:post, "https://api.openai.com/v1/chat/completions").to_return do |request|
      requests << JSON.parse(request.body)
      {
        status: 200, headers: { "Content-Type" => "application/json" },
        body: JSON.generate(
          id: "chatcmpl-paused", object: "chat.completion", created: 1, model: "gpt-4o-mini",
          choices: [{ index: 0, message: { role: "assistant", content: "Hello" }, finish_reason: "stop" }],
          usage: { prompt_tokens: 3, completion_tokens: 1, total_tokens: 4 }
        )
      }
    end

    refute RubyLLM::Chat.method_defined?(:with_otel_attributes)
    eval(snippet, TOPLEVEL_BINDING, "legacy-paused.rb")
    assert_equal 2, requests.size
    assert_equal ["user"], requests.first.fetch("messages").map { |message| message.fetch("role") }
    assert_equal ["user", "assistant", "user"], requests.last.fetch("messages").map { |message| message.fetch("role") }
    OpenTelemetry.tracer_provider.force_flush
    assert_empty exporter.finished_spans, "Paused RubyLLM must not emit spans to the shared provider"
    refute defined?(FutureAGITracing), "The legacy helper must not be loaded"
    refute RubyLLM::Chat.method_defined?(:with_otel_attributes), "Do not restore the instrumentation patch"
    refute $LOADED_FEATURES.any? { |path| path.include?("opentelemetry-instrumentation-ruby_llm") }

    OpenTelemetry.tracer_provider.tracer("other-integration").in_span("unrelated") {}
    OpenTelemetry.tracer_provider.force_flush
    assert_equal ["unrelated"], exporter.finished_spans.map(&:name)
  ensure
    OpenTelemetry.tracer_provider.shutdown if exporter
    ENV.delete("OPENAI_API_KEY")
  end
end
