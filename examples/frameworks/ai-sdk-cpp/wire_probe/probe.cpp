// Wire probe for TH-8251. Runs the real `ai::langfuse` module of ClickHouse/ai-sdk-cpp against a LOOPBACK
// capture stub, with the model call going to a local OpenAI-compatible endpoint, to record what the module
// puts on the wire and how Trace::end() behaves. It is not an integration and it never talks to Future AGI:
// the program refuses any Langfuse host that is not loopback.
//
//   probe <mode>
//     run          one tool call + generate_text, end() called twice
//     fail         unknown model -> API error, trace still ended
//     noend        like run, but the process exits without end()
//     strict-down  Langfuse host unreachable, ErrorPolicy::kStrict
//     best-down    Langfuse host unreachable, ErrorPolicy::kBestEffort
//
//   env: PROBE_LF_HOST      capture stub, loopback only (default http://127.0.0.1:18251)
//        PROBE_OPENAI_BASE  OpenAI-compatible base URL without /v1 (default http://127.0.0.1:8317)
//        PROBE_API_KEY      key for that endpoint
//        PROBE_MODEL        model id (default gpt-6-luna)
//        PROBE_MARKER       string placed in the prompt and trace metadata
#include <cstdlib>
#include <iostream>
#include <string>

#include <ai/langfuse.h>
#include <ai/openai.h>
#include <ai/tools.h>

namespace {
std::string env(const char* k, const char* d = "") {
  const char* v = std::getenv(k);
  return (v && *v) ? v : d;
}

bool is_loopback(const std::string& url) {
  return url.rfind("http://127.0.0.1", 0) == 0 || url.rfind("http://localhost", 0) == 0;
}

ai::JsonValue get_weather(const ai::JsonValue& args, const ai::ToolExecutionContext&) {
  return ai::JsonValue{{"location", args.value("location", std::string{"unknown"})},
                       {"temperature_c", 21},
                       {"sky", "clear"}};
}
}  // namespace

int main(int argc, char** argv) {
  const std::string mode = argc > 1 ? argv[1] : "run";
  const std::string marker = env("PROBE_MARKER", "MARKER-NONE");

  std::string host = env("PROBE_LF_HOST", "http://127.0.0.1:18251");
  auto policy = ai::langfuse::Config::ErrorPolicy::kStrict;
  if (mode == "strict-down") host = "http://127.0.0.1:1";
  if (mode == "best-down") {
    host = "http://127.0.0.1:1";
    policy = ai::langfuse::Config::ErrorPolicy::kBestEffort;
  }
  if (!is_loopback(host)) {
    std::cerr << "refusing Langfuse host " << host << ": the probe only talks to a loopback capture stub\n";
    return 3;
  }

  // Fake keys on purpose: the stub accepts anything.
  ai::langfuse::Tracer tracer({
      .host = host,
      .public_key = "pk-lf-probe-fake",
      .secret_key = "sk-lf-probe-fake",
      .environment = "ai-sdk-cpp-probe",
      .error_policy = policy,
  });
  std::cout << "tracer.is_valid=" << tracer.is_valid() << "\n";

  auto client = ai::openai::create_client(env("PROBE_API_KEY"), env("PROBE_OPENAI_BASE", "http://127.0.0.1:8317"));
  if (!client.is_valid()) {
    std::cerr << "openai client invalid\n";
    return 1;
  }

  ai::ToolSet tools;
  tools["get_weather"] = ai::create_tool("Get the current weather for a location",
                                         ai::create_object_schema({{"location", "string"}}), get_weather);

  ai::GenerateOptions options;
  options.model = mode == "fail" ? "no-such-model-probe" : env("PROBE_MODEL", "gpt-6-luna");
  options.system = "You are a concise assistant. Always call get_weather before answering.";
  options.prompt = "What is the weather in Paris? Context tag: " + marker;
  options.tools = std::move(tools);
  options.max_steps = 4;
  options.temperature = 0.0;

  auto trace = tracer.start_trace("probe_" + mode);
  trace->set_input(options.prompt);
  trace->set_metadata({{"probe", mode}, {"marker", marker}});
  trace->set_session_id("probe-session");
  trace->set_user_id("probe-user");

  auto result = ai::langfuse::generate_text(client, std::move(options), *trace);
  if (result) {
    std::cout << "model_output=" << result.text << "\n";
    trace->set_output(result.text);
  } else {
    std::cout << "generation_failed=" << result.error_message() << "\n";
    trace->set_output(ai::JsonValue{{"error", result.error_message()}});
  }

  if (mode == "noend") {
    std::cout << "exiting without end() trace_id=" << trace->id() << "\n";
    return 0;
  }
  bool first = false;
  try {
    first = trace->end();
  } catch (const std::exception& e) {
    std::cout << "end() threw: " << e.what() << "\n";
  }
  const bool second = trace->end();
  std::cout << "end#1=" << first << " end#2=" << second << " trace_id=" << trace->id() << "\n";
  return 0;
}
