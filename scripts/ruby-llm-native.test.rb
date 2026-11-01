# frozen_string_literal: true

# Uses released gems and real RubyLLM HTTP calls, with synthetic loopback services.
# Install ruby_llm ($RUBY_LLM_VERSION), opentelemetry-sdk (1.10.0),
# opentelemetry-exporter-otlp (0.32.0), webrick (1.9.1), and minitest (5.25.5).
# Run: RUBY_LLM_VERSION=2.1.1 ruby scripts/ruby-llm-native.test.rb
require 'minitest/autorun'
require 'json'
require 'open3'
require 'tmpdir'
require 'webrick'
require 'zlib'
require 'stringio'
require 'net/http'
gem 'opentelemetry-sdk', '1.10.0'
require 'opentelemetry/sdk'
require 'opentelemetry/exporter/otlp'

class RubyLLMNativeTest < Minitest::Test
  VERSION = ENV.fetch('RUBY_LLM_VERSION', '2.1.1')
  PAGE = File.read(File.expand_path('../src/pages/docs/integrations/frameworks/ruby-llm.mdx', __dir__))
  REQUEST = Opentelemetry::Proto::Collector::Trace::V1::ExportTraceServiceRequest
  CANARY = 'SYNTHETIC_PRIVATE'

  def setup
    @wire = Queue.new
    @provider_requests = Queue.new
    @server = WEBrick::HTTPServer.new(Port: 0, BindAddress: '127.0.0.1',
                                     Logger: WEBrick::Log.new(File::NULL), AccessLog: [])
    @server.mount_proc('/tracer/v1/traces') do |req, res|
      body = req['content-encoding'] == 'gzip' ? Zlib::GzipReader.new(StringIO.new(req.body)).read : req.body
      decoded = if req['content-type'] == 'application/json'
                  REQUEST.decode_json(body)
                else
                  REQUEST.decode(body)
                end
      @wire << { request: decoded, headers: req.header, body: body }
      res['Content-Type'] = req['content-type']
      res.body = req['content-type'] == 'application/json' ? '{}' : ''.b
    end
    @server.mount_proc('/v1') { |req, res| provider_response(req, res) }
    @thread = Thread.new { @server.start }
    @origin = "http://127.0.0.1:#{@server.config[:Port]}"
  end

  def teardown
    @server.shutdown
    @thread.join
  end

  def snippet(name)
    PAGE.match(/```ruby title="#{Regexp.escape(name)}"\n(.*?)\n```/m)&.captures&.first ||
      flunk("Missing runnable #{name} block")
  end

  def run_app(program = snippet('chat.rb'), compression: 'none')
    Dir.mktmpdir('ruby-llm-native') do |dir|
      File.write(File.join(dir, 'tracing.rb'), snippet('tracing.rb').sub('compression: "none"', "compression: #{compression.inspect}"))
      File.write(File.join(dir, 'chat.rb'), program)
      File.write(File.join(dir, 'prelude.rb'), <<~RUBY)
        gem 'ruby_llm', #{VERSION.inspect}
        gem 'opentelemetry-sdk', '1.10.0'
        gem 'opentelemetry-exporter-otlp', '0.32.0'
        require 'ruby_llm'
        RubyLLM.configure do |config|
          config.openai_api_base = #{"#{@origin}/v1".inspect}
          config.openai_api_key = 'synthetic-openai-key'
          config.max_retries = 0
          config.request_timeout = 5
        end
      RUBY
      env = {
        'PATH' => ENV.fetch('PATH'), 'HOME' => dir,
        'GEM_HOME' => ENV['GEM_HOME'], 'GEM_PATH' => ENV['GEM_PATH'],
        'FI_BASE_URL' => "#{@origin}/", 'FI_PROJECT_NAME' => 'native-ruby-test',
        'FI_API_KEY' => 'synthetic-fi-key', 'FI_SECRET_KEY' => 'synthetic-fi-secret',
        'OPENAI_API_KEY' => 'synthetic-openai-key',
        'OTEL_BSP_SCHEDULE_DELAY' => '60000',
        # Legacy content switches must not change native privacy behavior.
        'FI_CAPTURE_CONTENT' => '1', 'OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT' => 'true'
      }
      stdout, stderr, status = Open3.capture3(env, RbConfig.ruby, '-r', File.join(dir, 'prelude.rb'),
                                            File.join(dir, 'chat.rb'), unsetenv_others: true)
      assert status.success?, "RubyLLM #{VERSION} failed:\n#{stdout}\n#{stderr}"
      refute_match(/ERROR|Failed to export|Unable to export/, stderr)
    end
    refute @wire.empty?, 'Documented shutdown must export spans'
    items = []
    items << @wire.pop until @wire.empty?
    items
  end

  def attributes(list)
    list.to_h { |kv| [kv.key, kv.value.public_send(kv.value.value)] }
  end

  def spans(items)
    items.flat_map { |item| item[:request].resource_spans.flat_map { |rs| rs.scope_spans.flat_map(&:spans) } }
  end

  def assert_envelope(items, compression)
    items.each do |item|
      assert_equal ['synthetic-fi-key'], item[:headers]['x-api-key']
      assert_equal ['synthetic-fi-secret'], item[:headers]['x-secret-key']
      assert_equal ['application/x-protobuf'], item[:headers]['content-type']
      assert_equal(compression == 'gzip' ? ['gzip'] : [], item[:headers]['content-encoding'])
      item[:request].resource_spans.each do |rs|
        resource = attributes(rs.resource.attributes)
        assert_equal 'native-ruby-test', resource['project_name']
        assert_equal 'observe', resource['project_type']
        assert_equal 'ruby-llm-app', resource['service.name']
        rs.scope_spans.select { |ss| ss.scope.name == 'ruby_llm' }.each do |ss|
          assert_equal VERSION, ss.scope.version
        end
      end
      refute_includes REQUEST.encode_json(item[:request]), CANARY
      refute_includes item[:body], 'synthetic-openai-key'
      refute_includes item[:body], 'synthetic-fi-secret'
    end
  end

  def test_exact_documented_chat_exports_plain_protobuf_at_exit
    items = run_app
    assert_envelope(items, 'none')
    assert_equal 1, spans(items).size
    chat = spans(items).first
    assert_equal 'chat gpt-4o-mini', chat.name
    assert_equal 'chat', attributes(chat.attributes)['gen_ai.operation.name']
    assert_equal 'openai', attributes(chat.attributes)['gen_ai.provider.name']
    assert_equal 10, attributes(chat.attributes)['gen_ai.usage.input_tokens']
    assert_equal 5, attributes(chat.attributes)['gen_ai.usage.output_tokens']
    assert_equal '/v1/responses', @provider_requests.pop[:path]
  end

  def test_tool_loop_keeps_context_and_per_request_usage_without_content_or_duplicate_spans
    items = run_app(<<~RUBY, compression: 'gzip')
      require_relative 'tracing'
      RubyLLM::OpenTelemetry.enable # Calling enable again must not duplicate spans.
      class Lookup < RubyLLM::Tool
        description 'SYNTHETIC_PRIVATE_DESCRIPTION'
        def execute(value:)
          raise 'unexpected arguments' unless value == 'SYNTHETIC_PRIVATE_ARGUMENT'
          'SYNTHETIC_PRIVATE_RESULT'
        end
      end
      OpenTelemetry.tracer_provider.tracer('test').in_span('application-request') do
        RubyLLM.chat(model: 'gpt-4o-mini').with_tools(Lookup).ask('SYNTHETIC_PRIVATE_PROMPT')
      end
    RUBY
    assert_envelope(items, 'gzip')
    all = spans(items)
    assert_equal 4, all.size # application root, two actual completions, one tool
    root = all.find { |span| span.name == 'application-request' }
    all.reject { |span| span == root }.each do |span|
      assert_equal root.trace_id, span.trace_id
      assert_equal root.span_id, span.parent_span_id
      assert_empty span.events
      assert_empty span.status.message
    end
    tool = all.find { |span| span.name == 'execute_tool lookup' }
    refute_nil tool
    assert_equal 'call_synthetic', attributes(tool.attributes)['gen_ai.tool.call.id']
    chats = all.select { |span| attributes(span.attributes)['gen_ai.operation.name'] == 'chat' }
    assert_equal [10, 20], chats.map { |span| attributes(span.attributes)['gen_ai.usage.input_tokens'] }.sort
    assert_equal [5, 6], chats.map { |span| attributes(span.attributes)['gen_ai.usage.output_tokens'] }.sort
    assert_equal 2, @provider_requests.size
  end

  def test_stream_and_error_metadata_remain_private
    items = run_app(<<~RUBY)
      require_relative 'tracing'
      text = +''
      RubyLLM.chat(model: 'gpt-4o-mini', protocol: :chat_completions).ask('SYNTHETIC_PRIVATE_STREAM') do |chunk|
        text << chunk.content.to_s
      end
      raise 'stream missing' unless text == 'SYNTHETIC_PRIVATE_ANSWER'
      begin
        RubyLLM.chat(model: 'gpt-4o-mini').ask('SYNTHETIC_PRIVATE_ERROR')
        raise 'provider error was swallowed'
      rescue RubyLLM::BadRequestError
        # The library must preserve application error behavior without exporting error text.
      end
    RUBY
    assert_envelope(items, 'none')
    assert_equal 2, spans(items).size
    stream = spans(items).find { |span| attributes(span.attributes)['gen_ai.request.stream'] }
    refute_nil stream
    assert_equal 10, attributes(stream.attributes)['gen_ai.usage.input_tokens']
    error = spans(items).find { |span| span.status.code == :STATUS_CODE_ERROR }
    refute_nil error
    assert_equal 'RubyLLM::BadRequestError', attributes(error.attributes)['error.type']
    assert_empty error.status.message
    assert_empty error.events
  end

  def test_exported_payload_round_trips_json_and_protobuf_plain_and_gzip
    # Ruby exports protobuf only. JSON is a wire-codec replay, not a claimed Ruby exporter mode.
    original = run_app.first[:request]
    %w[protobuf json].product(%w[none gzip]).each do |format, compression|
      body = format == 'json' ? REQUEST.encode_json(original) : REQUEST.encode(original)
      if compression == 'gzip'
        io = StringIO.new
        writer = Zlib::GzipWriter.new(io)
        writer.write(body)
        writer.close
        body = io.string
      end
      uri = URI("#{@origin}/tracer/v1/traces")
      request = Net::HTTP::Post.new(uri)
      request['Content-Type'] = format == 'json' ? 'application/json' : 'application/x-protobuf'
      request['Content-Encoding'] = 'gzip' if compression == 'gzip'
      request.body = body
      response = Net::HTTP.start(uri.host, uri.port, nil) { |http| http.request(request) }
      assert_equal '200', response.code
      assert_equal original, @wire.pop[:request]
    end
  end

  def provider_response(req, res)
    data = JSON.parse(req.body)
    @provider_requests << { path: req.path, data: data }
    res['Content-Type'] = 'application/json'
    if req.body.include?('SYNTHETIC_PRIVATE_ERROR')
      res.status = 400
      res.body = JSON.generate(error: { message: 'SYNTHETIC_PRIVATE_PROVIDER_ERROR', type: 'invalid_request_error' })
    elsif data['stream']
      res['Content-Type'] = 'text/event-stream'
      chunks = [
        { choices: [{ index: 0, delta: { role: 'assistant', content: 'SYNTHETIC_PRIVATE_ANSWER' }, finish_reason: nil }] },
        { choices: [{ index: 0, delta: {}, finish_reason: 'stop' }] },
        { choices: [], usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 } }
      ]
      res.body = chunks.map { |chunk| "data: #{JSON.generate(chunk.merge(id: 'synthetic-stream', object: 'chat.completion.chunk', model: 'gpt-4o-mini'))}\n\n" }.join + "data: [DONE]\n\n"
    else
      followup = Array(data['input']).any? { |entry| entry['type'] == 'function_call_output' }
      output = if data['tools']&.any? && !followup
                 [{ type: 'function_call', name: 'lookup', call_id: 'call_synthetic',
                    arguments: JSON.generate(value: 'SYNTHETIC_PRIVATE_ARGUMENT') }]
               else
                 [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text: 'SYNTHETIC_PRIVATE_ANSWER' }] }]
               end
      res.body = JSON.generate(id: 'synthetic-response', object: 'response', status: 'completed',
                               model: 'gpt-4o-mini', output: output,
                               usage: { input_tokens: followup ? 20 : 10, output_tokens: followup ? 6 : 5 })
    end
  end
end
