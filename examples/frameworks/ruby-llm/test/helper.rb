# frozen_string_literal: true

require "bundler/setup"
require "minitest/autorun"
require "webmock/minitest"
require "json"
require "ruby_llm"
require_relative "../futureagi_tracing"

WebMock.disable_net_connect!

# Stand-in for the model: WebMock answers what OpenAI's /v1/chat/completions answers.
# These are canned replies shaped like the documented API, NOT a real model.
module FakeOpenAI
  URL = "https://api.openai.com/v1/chat/completions"

  module_function

  def completion(content: nil, tool_calls: nil, usage: { prompt_tokens: 11, completion_tokens: 7, total_tokens: 18 })
    message = { role: "assistant", content: content }
    message[:tool_calls] = tool_calls if tool_calls
    {
      id: "chatcmpl-fake", object: "chat.completion", created: 1, model: "fake-model",
      choices: [{ index: 0, message: message, finish_reason: tool_calls ? "tool_calls" : "stop" }],
      usage: usage
    }
  end

  def tool_call(name:, arguments:)
    [{ id: "call_fake1", type: "function", function: { name: name, arguments: JSON.generate(arguments) } }]
  end

  def sse(chunks, usage: { prompt_tokens: 11, completion_tokens: 7, total_tokens: 18 })
    lines = chunks.map do |text|
      "data: #{JSON.generate({ id: 'c', object: 'chat.completion.chunk', model: 'fake-model', choices: [{ index: 0, delta: { content: text }, finish_reason: nil }] })}\n\n"
    end
    lines << "data: #{JSON.generate({ id: 'c', object: 'chat.completion.chunk', model: 'fake-model', choices: [{ index: 0, delta: {}, finish_reason: 'stop' }], usage: usage })}\n\n"
    lines << "data: [DONE]\n\n"
    lines.join
  end

  def stub_chat(*responses)
    WebMock.stub_request(:post, URL).to_return(*responses.map { |r| { status: 200, headers: { "Content-Type" => "application/json" }, body: JSON.generate(r) } })
  end

  def stub_stream(chunks)
    WebMock.stub_request(:post, URL).to_return(status: 200, headers: { "Content-Type" => "text/event-stream" }, body: sse(chunks))
  end

  def stub_error(status: 401, message: "Incorrect API key provided: sk-SECRETKEY123")
    WebMock.stub_request(:post, URL).to_return(status: status, headers: { "Content-Type" => "application/json" },
                                               body: JSON.generate({ error: { message: message, type: "invalid_request_error" } }))
  end
end

RubyLLM.configure { |c| c.openai_api_key = "sk-SECRETKEY123" }

def new_chat
  RubyLLM.chat(model: "fake-model", provider: :openai, assume_model_exists: true)
end

class LookupTool < RubyLLM::Tool
  description "Look up a customer by id"
  param :customer_id, desc: "customer id"

  def execute(customer_id:)
    "customer #{customer_id} is TOOLRESULT-MARKER"
  end
end

# Sets up tracing once for the process with an in-memory exporter and returns it.
def install_tracing(**opts)
  exporter = OpenTelemetry::SDK::Trace::Export::InMemorySpanExporter.new
  FutureAGITracing.setup(project_name: "ruby-llm-test", exporter: exporter, batch: false, flush_at_exit: false, **opts)
  exporter
end

def all_text(span_datas)
  span_datas.map { |sd| [sd.name, sd.attributes, sd.events, sd.status.description, sd.resource.attribute_enumerator.to_a].inspect }.join("\n")
end
