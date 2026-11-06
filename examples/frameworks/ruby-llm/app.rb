# frozen_string_literal: true

# Demo for the Ruby LLM recipe. Usage: bundle exec ruby app.rb <scenario>
# Scenarios: chat, stream, tool, agent, session, error
#
#   MODEL_ID          model name (default gpt-5.6-terra)
#   OPENAI_API_KEY    key for the OpenAI-compatible endpoint
#   OPENAI_API_BASE   endpoint, e.g. http://127.0.0.1:8317/v1 (default: OpenAI)
#   MARKER            text put into the prompt, the tool argument and the tool result so a
#                     privacy scan can look for it in Future AGI
require "json"
require_relative "futureagi_tracing"
require "ruby_llm"

FutureAGITracing.setup

RubyLLM.configure do |c|
  c.openai_api_key = ENV.fetch("OPENAI_API_KEY")
  c.openai_api_base = ENV["OPENAI_API_BASE"] if ENV["OPENAI_API_BASE"]
end

MODEL = ENV.fetch("MODEL_ID", "gpt-5.6-terra")
MARKER = ENV.fetch("MARKER", "no-marker")

# assume_model_exists: skip the model registry lookup, needed for a model name ruby_llm
# does not list (anything behind an OpenAI-compatible proxy).
def new_chat(model: MODEL)
  RubyLLM.chat(model: model, provider: :openai, assume_model_exists: true)
end

class Lookup < RubyLLM::Tool
  description "Look up a customer by id"
  param :customer_id, desc: "customer id"

  def execute(customer_id:)
    "customer #{customer_id} is #{MARKER}-result"
  end
end

class SupportAgent < RubyLLM::Agent
  model MODEL, provider: :openai, assume_model_exists: true
  tools Lookup
end

def result(ok:, **extra)
  puts "RESULT #{JSON.generate({ ok: ok }.merge(extra))}"
  ok
end

ok = case (scenario = ARGV.fetch(0))
     when "chat"
       reply = new_chat.ask("Reply with one short sentence about Ruby. #{MARKER}-prompt")
       result(ok: !reply.content.to_s.empty?, scenario: scenario, input_tokens: reply.input_tokens, output_tokens: reply.output_tokens)
     when "stream"
       chunks = 0
       reply = new_chat.ask("Count from 1 to 5, #{MARKER}-prompt") { |_chunk| chunks += 1 }
       result(ok: chunks > 1, scenario: scenario, chunks: chunks, output_tokens: reply.output_tokens)
     when "tool"
       chat = new_chat.with_tool(Lookup)
       reply = chat.ask("Use the lookup tool for customer id #{MARKER}-arg and tell me what it returns.")
       result(ok: reply.content.to_s.include?("#{MARKER}-result"), scenario: scenario)
     when "agent"
       reply = SupportAgent.new.ask("Use the lookup tool for customer id #{MARKER}-arg and tell me what it returns.")
       result(ok: !reply.content.to_s.empty?, scenario: scenario)
     when "session"
       chat = new_chat.with_otel_attributes("session.id" => "sess-e2e", "gen_ai.conversation.id" => "conv-e2e", "user.id" => "user-1")
       chat.ask("Say hi")
       chat.ask("Say bye")
       result(ok: true, scenario: scenario)
     when "error"
       begin
         new_chat(model: "no-such-model").ask("hello #{MARKER}-prompt")
         result(ok: true, scenario: scenario)
       rescue StandardError => e
         result(ok: false, scenario: scenario, error: e.class.name)
       end
     else
       abort "unknown scenario #{scenario}"
     end

FutureAGITracing.shutdown
exit(ok || scenario == "error" ? 0 : 1)
