# frozen_string_literal: true

# FI_CAPTURE_CONTENT=1 / capture_content: true turns content on, and still never exports
# stack traces, span events or the API key.
require "helper"

EXPORTER = install_tracing(capture_content: true)

class OptInTest < Minitest::Test
  def setup
    EXPORTER.reset
  end

  def finished
    OpenTelemetry.tracer_provider.force_flush
    EXPORTER.finished_spans
  end

  def test_messages_and_tool_io_are_exported
    FakeOpenAI.stub_chat(
      FakeOpenAI.completion(tool_calls: FakeOpenAI.tool_call(name: "lookup", arguments: { customer_id: "TOOLARG-MARKER" })),
      FakeOpenAI.completion(content: "PROMPTREPLY-MARKER")
    )
    new_chat.with_instructions("SYSTEM-MARKER").with_tool(LookupTool).ask("PROMPT-MARKER")
    text = all_text(finished)
    %w[PROMPT-MARKER PROMPTREPLY-MARKER SYSTEM-MARKER TOOLARG-MARKER TOOLRESULT-MARKER].each { |m| assert_includes text, m }
  end

  def test_custom_attributes_are_kept_on_opt_in
    FakeOpenAI.stub_chat(FakeOpenAI.completion(content: "ok"))
    new_chat.with_otel_attributes("custom.note" => "CUSTOM-MARKER").ask("hi")
    assert_equal "CUSTOM-MARKER", finished.first.attributes["custom.note"]
  end

  def test_error_status_is_kept_but_events_and_stack_traces_are_not
    FakeOpenAI.stub_error(message: "boom-visible")
    assert_raises(RubyLLM::Error) { new_chat.ask("hi") }
    span = finished.first
    assert_equal OpenTelemetry::Trace::Status::ERROR, span.status.code
    assert_nil span.events
    refute_includes all_text([span]), __dir__
  end
end
