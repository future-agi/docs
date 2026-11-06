# frozen_string_literal: true

# Retained legacy regression fixture, not a maintained installation path. See README.md.
# Configures the OpenTelemetry Ruby SDK and opentelemetry-instrumentation-ruby_llm.
# By default, restricts span attributes to an exact allowlist and removes events because
# the instrumentation exports tool arguments and results even when capture_content is off.
#
#   require_relative "futureagi_tracing"
#   FutureAGITracing.setup          # once, at boot
#   ...
#   FutureAGITracing.shutdown       # before the process exits (also registered with at_exit)
#
# Environment:
#   FI_API_KEY, FI_SECRET_KEY   required
#   FI_PROJECT_NAME             Observe project the traces land in (default "ruby-llm")
#   FI_BASE_URL                 self-hosted origin only; default https://api.futureagi.com
#   FI_CAPTURE_CONTENT=1        opt in to prompts, answers, tool arguments and tool results

require "opentelemetry/sdk"
require "opentelemetry/exporter/otlp"
require "opentelemetry-instrumentation-ruby_llm"

module FutureAGITracing
  # Exact span-attribute contract for the retained legacy regression fixture, not an
  # installable integration. Never trust entire gen_ai namespaces: custom attributes
  # can put prompts or credentials under otherwise plausible request/response keys.
  # Values of allowed attributes, span names and resource attributes remain caller-owned;
  # this is not a secret scanner. The instrumentation's capture switch alone leaves
  # tool arguments, results, descriptions and exception events enabled.
  METADATA_ATTRIBUTES = %w[
    gen_ai.operation.name
    gen_ai.provider.name
    gen_ai.request.model
    gen_ai.request.stream
    gen_ai.request.temperature
    gen_ai.response.model
    gen_ai.usage.input_tokens
    gen_ai.usage.output_tokens
    gen_ai.usage.cache_creation.input_tokens
    gen_ai.usage.cache_read.input_tokens
    gen_ai.tool.name
    gen_ai.tool.call.id
    gen_ai.tool.type
    gen_ai.agent.name
    gen_ai.conversation.id
    error.type
    session.id
    user.id
  ].freeze

  # Wraps an exporter. Always drops span events (the instrumentation records exception
  # messages and stack traces there, which contain local paths and raw provider text). Unless
  # content is opted in, also keeps only METADATA_ATTRIBUTES, and keeps the ERROR status
  # without its text.
  class SanitizingExporter
    def initialize(inner, keep_content:)
      @inner = inner
      @keep_content = keep_content
    end

    def export(span_datas, timeout: nil)
      @inner.export(span_datas.map { |sd| sanitize(sd) }, timeout: timeout)
    end

    def force_flush(timeout: nil) = @inner.force_flush(timeout: timeout)

    def shutdown(timeout: nil) = @inner.shutdown(timeout: timeout)

    private

    def metadata?(key)
      METADATA_ATTRIBUTES.include?(key)
    end

    def sanitize(span_data)
      copy = span_data.dup
      copy.events = nil
      copy.total_recorded_events = 0
      unless @keep_content
        copy.attributes = (span_data.attributes || {}).select { |key, _| metadata?(key) }
        status = span_data.status
        copy.status = OpenTelemetry::Trace::Status.error if status && status.code == OpenTelemetry::Trace::Status::ERROR
      end
      copy
    end
  end

  class << self
    # Configure the SDK. Pass exporter: to replace the OTLP exporter (tests do).
    def setup(project_name: ENV.fetch("FI_PROJECT_NAME", "ruby-llm"),
              capture_content: ENV["FI_CAPTURE_CONTENT"] == "1",
              exporter: nil, batch: true, flush_at_exit: true)
      exporter ||= otlp_exporter
      exporter = SanitizingExporter.new(exporter, keep_content: capture_content)
      processor = if batch
                    OpenTelemetry::SDK::Trace::Export::BatchSpanProcessor.new(exporter)
                  else
                    OpenTelemetry::SDK::Trace::Export::SimpleSpanProcessor.new(exporter)
                  end

      OpenTelemetry::SDK.configure do |c|
        c.service_name = ENV.fetch("OTEL_SERVICE_NAME", project_name)
        c.resource = OpenTelemetry::SDK::Resources::Resource.create(
          "project_name" => project_name,
          "project_type" => "observe"
        )
        c.add_span_processor(processor)
        c.use "OpenTelemetry::Instrumentation::RubyLLM", capture_content: capture_content
      end
      at_exit { shutdown } if flush_at_exit
      self
    end

    # Flush and stop. Safe to call twice.
    def shutdown
      return if @shut_down

      @shut_down = true
      OpenTelemetry.tracer_provider.shutdown
    end

    def endpoint
      "#{ENV.fetch('FI_BASE_URL', 'https://api.futureagi.com').chomp('/')}/tracer/v1/traces"
    end

    private

    def otlp_exporter
      OpenTelemetry::Exporter::OTLP::Exporter.new(
        endpoint: endpoint,
        headers: { "X-Api-Key" => ENV.fetch("FI_API_KEY"), "X-Secret-Key" => ENV.fetch("FI_SECRET_KEY") },
        compression: "none" # the exporter gzips by default; do not
      )
    end
  end
end
