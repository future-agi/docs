# frozen_string_literal: true

# Default (content off) behaviour of futureagi_tracing.rb with the model stood in by WebMock.
require "helper"

EXPORTER = install_tracing(capture_content: false)

class RecipeTest < Minitest::Test
  def setup
    EXPORTER.reset
  end

  def finished
    OpenTelemetry.tracer_provider.force_flush
    EXPORTER.finished_spans
  end

  def test_chat_is_one_llm_span_with_model_and_usage
    FakeOpenAI.stub_chat(FakeOpenAI.completion(content: "PROMPTREPLY-MARKER"))
    new_chat.ask("PROMPT-MARKER")
    spans = finished
    assert_equal 1, spans.size
    span = spans.first
    assert_equal "chat fake-model", span.name
    assert_equal "chat", span.attributes["gen_ai.operation.name"]
    assert_equal "openai", span.attributes["gen_ai.provider.name"]
    assert_equal "fake-model", span.attributes["gen_ai.request.model"]
    assert_equal 11, span.attributes["gen_ai.usage.input_tokens"]
    assert_equal 7, span.attributes["gen_ai.usage.output_tokens"]
  end

  def test_resource_carries_project_name_and_type
    FakeOpenAI.stub_chat(FakeOpenAI.completion(content: "ok"))
    new_chat.ask("hi")
    res = finished.first.resource.attribute_enumerator.to_h
    assert_equal "ruby-llm-test", res["project_name"]
    assert_equal "observe", res["project_type"]
  end

  def test_content_is_not_exported
    FakeOpenAI.stub_chat(FakeOpenAI.completion(content: "PROMPTREPLY-MARKER"))
    chat = new_chat.with_instructions("SYSTEM-MARKER")
    chat.ask("PROMPT-MARKER")
    text = all_text(finished)
    %w[PROMPT-MARKER PROMPTREPLY-MARKER SYSTEM-MARKER].each { |m| refute_includes text, m }
  end

  def test_stream_is_one_span_not_one_per_chunk
    FakeOpenAI.stub_stream(%w[one two three four])
    chunks = []
    new_chat.ask("count") { |c| chunks << c }
    assert_operator chunks.size, :>=, 4
    spans = finished
    assert_equal 1, spans.size
    assert_equal true, spans.first.attributes["gen_ai.request.stream"]
    assert_equal 7, spans.first.attributes["gen_ai.usage.output_tokens"]
  end

  def test_tool_call_gets_a_child_tool_span_without_arguments_or_result
    FakeOpenAI.stub_chat(
      FakeOpenAI.completion(tool_calls: FakeOpenAI.tool_call(name: "lookup", arguments: { customer_id: "TOOLARG-MARKER" })),
      FakeOpenAI.completion(content: "done")
    )
    new_chat.with_tool(LookupTool).ask("find")
    spans = finished
    tool = spans.find { |s| s.name == "execute_tool lookup" }
    refute_nil tool, "no execute_tool span: #{spans.map(&:name)}"
    assert_equal "lookup", tool.attributes["gen_ai.tool.name"]
    chat_span_ids = spans.select { |s| s.name.start_with?("chat ") }.map(&:span_id)
    assert_includes chat_span_ids, tool.parent_span_id
    text = all_text(spans)
    %w[TOOLARG-MARKER TOOLRESULT-MARKER].each { |m| refute_includes text, m }
    refute tool.attributes.key?("gen_ai.tool.description")
  end

  def test_provider_error_is_error_status_without_text_events_or_key
    FakeOpenAI.stub_error
    assert_raises(RubyLLM::Error) { new_chat.ask("PROMPT-MARKER") }
    span = finished.first
    assert_equal OpenTelemetry::Trace::Status::ERROR, span.status.code
    assert_equal "RubyLLM::UnauthorizedError", span.attributes["error.type"]
    assert_equal "", span.status.description.to_s
    assert_nil span.events
    text = all_text([span])
    ["SECRETKEY123", "Incorrect API key", "PROMPT-MARKER", __dir__].each { |m| refute_includes text, m }
  end

  def test_session_and_user_ids_ride_on_the_chat_span
    FakeOpenAI.stub_chat(FakeOpenAI.completion(content: "ok"))
    new_chat.with_otel_attributes("session.id" => "s-1", "user.id" => "u-1").ask("hi")
    attrs = finished.first.attributes
    assert_equal "s-1", attrs["session.id"]
    assert_equal "u-1", attrs["user.id"]
  end

  def test_unlisted_attributes_are_dropped_by_default
    FakeOpenAI.stub_chat(FakeOpenAI.completion(content: "ok"))
    new_chat.with_otel_attributes("user.id" => "u-1", "user.email" => "a@example.test", "custom.note" => "CUSTOM-MARKER").ask("hi")
    attrs = finished.first.attributes
    assert_equal "u-1", attrs["user.id"]
    refute attrs.key?("user.email")
    refute attrs.key?("custom.note")
  end

  def test_no_credentials_or_paths_on_any_span
    FakeOpenAI.stub_chat(FakeOpenAI.completion(content: "ok"))
    new_chat.ask("hi")
    text = all_text(finished)
    ["SECRETKEY123", Dir.home, Etc.getlogin.to_s, Socket.gethostname].reject(&:empty?).each { |m| refute_includes text, m }
  end

end
