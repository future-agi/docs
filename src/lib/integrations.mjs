// @ts-check
/**
 * Published integration discovery. Cards and the Integrations sidebar both use
 * this catalog. Add a guide only after its route exists on the deployment branch.
 * A method describes the connection path, not a support or testing badge.
 * Run `npm run test:integrations` when changing this file.
 *
 * @typedef {'providers'|'frameworks'|'coding'|'gateways'|'voice'|'java'|'apps'|'import'|'export'} IntegrationCategory
 * @typedef {{id: string, name: string, href: string, category: IntegrationCategory,
 * summary: string, method: string, logo: string, aliases?: string[], sharedGuide?: boolean}} Integration
 * @typedef {{id: IntegrationCategory, name: string, description: string}} Category
 */

/** @type {ReadonlyArray<Category>} */
export const integrationCategories = [
  { id: 'providers', name: 'Model providers', description: 'Trace model calls from your application.' },
  { id: 'frameworks', name: 'Frameworks & agents', description: 'Connect the steps, tools and model calls in your application.' },
  { id: 'coding', name: 'Coding agents', description: 'Connect coding-agent sessions, turns and tools.' },
  { id: 'gateways', name: 'Gateways', description: 'Trace proxied requests, using the connection method in each guide.' },
  { id: 'voice', name: 'Voice & realtime', description: 'Follow conversations across your voice stack.' },
  { id: 'java', name: 'Java', description: 'Set up JVM tracing with client wrappers or native OpenTelemetry.' },
  { id: 'apps', name: 'Apps & workflows', description: 'Connect chat applications and visual workflows.' },
  { id: 'import', name: 'Import traces', description: 'Bring existing traces into Future AGI.' },
  { id: 'export', name: 'Export & alerts', description: 'Send Future AGI data to the tools your team already uses.' },
];

/** @type {ReadonlyArray<Integration>} */
export const integrations = [
  { id: 'a2a-go', name: 'A2A Go', href: '/docs/integrations/traceai/go/a2a', category: 'frameworks', summary: 'Trace Go agent-to-agent calls on clients and servers.', method: 'traceAI SDK', logo: 'generic-framework' },
  { id: 'vitest', name: 'Vitest', href: '/docs/integrations/frameworks/vitest', category: 'frameworks', summary: 'Trace test runs and workers with native OpenTelemetry.', method: 'Native OTLP', logo: 'generic-framework', aliases: ['Vitest tests'] },
  { id: 'helicone', name: 'Helicone', href: '/docs/integrations/gateways/helicone', category: 'gateways', summary: 'Trace OpenAI-client calls through a self-hosted Helicone gateway.', method: 'OpenAI client', logo: 'generic-framework' },
  {"id": "cloudflare-agents", "name": "Cloudflare Agents", "href": "/docs/integrations/frameworks/cloudflare-agents", "category": "frameworks", "summary": "Trace awaited HTTP generateText turns through a collector.", "method": "Workers OTLP", "logo": "generic-framework"},
  { id: 'quarkus-langchain4j', name: 'Quarkus LangChain4j', href: '/docs/integrations/traceai/java/quarkus-langchain4j', category: 'java', summary: 'Export synchronous JVM AI-service spans to a self-hosted collector.', method: 'Native OTLP', logo: 'generic-framework' },
  {"id": "cloudflare-ai-chat", "name": "Cloudflare AI Chat", "href": "/docs/integrations/frameworks/cloudflare-ai-chat", "category": "frameworks", "summary": "Trace deployed AIChatAgent chat turns through a collector.", "method": "Workers OTLP", "logo": "generic-framework"},
  { id: 'arconia', name: 'Arconia', href: '/docs/integrations/traceai/java/arconia', category: 'java', summary: 'Export JVM HTTP server spans with an explicit error-detail filter.', method: 'Native OTLP', logo: 'generic-framework' },
  { id: 'azure-apim', name: 'Azure API Management', href: '/docs/integrations/gateways/azure-apim', category: 'gateways', summary: 'Forward application spans through a Consumption-tier egress policy.', method: 'APIM OTLP egress', logo: 'generic-cloud' },
  { id: 'openai-csharp', name: 'OpenAI C#', href: '/docs/integrations/providers/openai-csharp', category: 'providers', summary: 'Trace non-streaming OpenAI .NET chat calls.', method: 'Native OTLP', logo: 'openai', aliases: ['OpenAI .NET', 'OpenAI CSharp'] },
  { id: 'azure-openai-csharp', name: 'Azure OpenAI C#', href: '/docs/integrations/providers/azure-openai-csharp', category: 'providers', summary: 'Trace non-streaming .NET chat calls to the Azure v1 endpoint.', method: 'Native OTLP', logo: 'generic-cloud', aliases: ['Azure OpenAI .NET', 'CSharp'] },
  { id: 'openrouter-agent', name: 'OpenRouter Agent', href: '/docs/integrations/frameworks/openrouter-agent', category: 'frameworks', summary: 'Trace non-streaming agent loops and tools through lifecycle hooks.', method: 'Hook-to-OTLP', logo: 'generic-framework' },
  { id: 'hermes-agent', name: 'Hermes Agent CLI', href: '/docs/integrations/coding-agents/hermes-agent', category: 'coding', summary: 'Trace prompts, model calls, tools and sessions with one-command setup and content capture on by default.', method: 'traceAI plugin', logo: 'generic-framework' },
  { id: 'github-copilot', name: 'GitHub Copilot CLI', href: '/docs/integrations/coding-agents/github-copilot', category: 'coding', summary: 'Trace CLI prompts, model usage, and tools with one-command setup.', method: 'traceAI launcher', logo: 'generic-framework' },
  { id: 'goose', name: 'Goose', href: '/docs/integrations/coding-agents/goose', category: 'coding', summary: 'Trace CLI prompts, model generations and tools with one setup command.', method: 'traceAI plugin', logo: 'generic-framework' },
  { id: 'truefoundry', name: 'TrueFoundry', href: '/docs/integrations/gateways/truefoundry', category: 'gateways', summary: 'Trace Python client calls, not native gateway exports.', method: 'OpenAI client', logo: 'generic-framework' },
  { id: 'google-antigravity', name: 'Antigravity CLI', href: '/docs/integrations/coding-agents/google-antigravity', category: 'coding', summary: 'Trace Linux CLI prompts, model responses, tokens, tools and subagents with one-command setup.', method: 'traceAI plugin', logo: 'generic-framework' },
  { id: 'cognee', name: 'Cognee', href: '/docs/integrations/traceai/cognee', category: 'frameworks', summary: 'Export native memory-operation spans with a privacy filter.', method: 'Native OTLP', logo: 'generic-framework' },
  { id: 'bedrock-agentcore', name: 'Bedrock AgentCore Runtime', href: '/docs/integrations/traceai/bedrock-agentcore', category: 'frameworks', summary: 'Trace hosted LangChain agents or export native Strands spans.', method: 'OTel + traceAI', logo: 'bedrock' },
  { id: 'cloudflare-think', name: 'Cloudflare Think', href: '/docs/integrations/frameworks/cloudflare-think', category: 'frameworks', summary: 'Forward native Worker agent spans through a privacy-filtering collector.', method: 'Native OTLP', logo: 'generic-framework' },
  { id: 'openrouter-broadcast', name: 'OpenRouter Broadcast', href: '/docs/integrations/gateways/openrouter-broadcast', category: 'gateways', summary: 'Forward native Broadcast traces through a privacy-filtering collector.', method: 'Native OTLP', logo: 'generic-framework' },
  { id: 'everos', name: 'EverOS', href: '/docs/integrations/traceai/everos', category: 'frameworks', summary: 'Export version-scoped memory-server spans to self-hosted Future AGI.', method: 'Native OTLP', logo: 'generic-framework' },
  { id: 'openinference', name: 'OpenInference', href: '/docs/integrations/import/openinference', category: 'frameworks', summary: 'Send native Python, TypeScript, Java and Go OpenInference spans over OTLP.', method: 'OpenInference SDK', logo: 'generic-framework' },
  { id: 'oh-my-pi', name: 'Oh My Pi', href: '/docs/integrations/coding-agents/oh-my-pi', category: 'coding', summary: 'Trace omp sessions with the version-scoped local hook.', method: 'omp hook', logo: 'generic-framework' },
  { id: 'claude-code', name: 'Claude Code', href: '/docs/integrations/coding-agents/claude-code', category: 'coding', summary: 'Trace prompts, model generations, tools and subagents with one setup command.', method: 'traceAI plugin', logo: 'generic-framework' },
  { id: 'pi', name: 'Pi', href: '/docs/integrations/coding-agents/pi', category: 'coding', summary: 'Trace upstream Pi sessions through a local extension.', method: 'Pi extension', logo: 'generic-framework' },
  { id: 'pi-sdk', name: 'Pi Coding Agent SDK', href: '/docs/integrations/coding-agents/pi-sdk', category: 'coding', summary: 'Trace embedded Pi sessions, model calls, tools and compaction.', method: 'traceAI SDK', logo: 'generic-framework' },
  { id: 'openclaw', name: 'OpenClaw', href: '/docs/integrations/coding-agents/openclaw', category: 'coding', summary: 'Trace local prompts, model calls and tools with one-command setup.', method: 'traceAI plugin', logo: 'generic-framework' },
  { id: 'opencode', name: 'OpenCode', href: '/docs/integrations/coding-agents/opencode', category: 'coding', summary: 'Set up V1 or V2 tracing for prompts, model calls, tools and subagents.', method: 'OpenCode plugin', logo: 'generic-framework' },
  { id: 'azure-ai-foundry', name: 'Azure AI Foundry', href: '/docs/integrations/frameworks/azure-ai-foundry', category: 'frameworks', summary: 'Trace Python project and Responses calls with native instrumentation.', method: 'Native OpenTelemetry', logo: 'generic-framework', aliases: ['Microsoft Foundry', 'Azure agents'] },
  { id: 'openllmetry', name: 'OpenLLMetry', href: '/docs/integrations/otel/openllmetry', category: 'frameworks', summary: 'Forward Traceloop SDK traces with OTLP/HTTP.', method: 'Native OTLP', logo: 'generic-framework', aliases: ['Traceloop'] },
  {"id": "openlit", "name": "OpenLIT", "href": "/docs/integrations/traceai/openlit", "category": "frameworks", "summary": "Export synchronous Python OpenAI spans with OpenLIT.", "method": "Native OTLP", "logo": "generic-framework"},
  { id: 'gradio', name: 'Gradio', href: '/docs/integrations/traceai/gradio', category: 'frameworks', summary: 'Trace synchronous chat callbacks through their model client.', method: 'OpenAI client', logo: 'generic-framework' },
  { id: 'z-ai', name: 'Z.ai', href: '/docs/integrations/providers/z-ai', category: 'providers', summary: 'Trace Python chat completions on the general-platform endpoint.', method: 'OpenAI client', logo: 'generic-model' },
  { id: 'voyage-ai', name: 'Voyage AI', href: '/docs/integrations/traceai/voyage', category: 'providers', summary: 'Trace embedding and rerank calls from the Python client.', method: 'traceAI SDK', logo: 'generic-model', aliases: ['Voyage', 'voyageai', 'rerank'] },
  { id: 'cursor', name: 'Cursor IDE and CLI', href: '/docs/integrations/coding-agents/cursor', category: 'coding', summary: 'Trace prompts, model generations, token usage and tools with one shared setup.', method: 'Cursor plugin', logo: 'generic-framework', aliases: ['Cursor Agent', 'cursor-agent'] },
  { id: 'codex', name: 'OpenAI Codex CLI', href: '/docs/integrations/coding-agents/codex', category: 'coding', summary: 'Connect Codex with one setup command and inspect turns, model attempts and tools.', method: 'Native plugin', logo: 'openai' },
  { id: 'codex-sdk', name: 'OpenAI Codex SDK', href: '/docs/integrations/coding-agents/codex-sdk', category: 'coding', summary: 'Trace SDK turns, tools and token usage with private content hidden by default.', method: 'traceAI SDK', logo: 'openai' },
  { id: 'cursor-sdk', name: 'Cursor SDK', href: '/docs/integrations/coding-agents/cursor-sdk', category: 'coding', summary: 'Trace local Node.js agent runs, tools and usage with the Cursor SDK.', method: 'traceAI SDK', logo: 'generic-framework' },
  { id: 'grok-build', name: 'Grok Build', href: '/docs/integrations/coding-agents/grok-build', category: 'coding', summary: 'Set up CLI prompt, model response, tool and subagent tracing with one command.', method: 'Native plugin', logo: 'generic-framework', aliases: ['xAI Grok CLI'] },
  { id: 'augment-code', name: 'Augment Code (Auggie CLI)', href: '/docs/integrations/coding-agents/augment-code', category: 'coding', summary: 'Trace new macOS CLI sessions and stop causes with lifecycle hooks.', method: 'Hook-to-OTLP', logo: 'generic-framework', aliases: ['Auggie'] },
  { id: 'gemini-cli', name: 'Gemini CLI', href: '/docs/integrations/coding-agents/gemini-cli', category: 'coding', summary: 'Trace non-sandbox CLI sessions through a privacy-filtering collector.', method: 'Native OTLP', logo: 'google' },
  { id: 'kiro-cli', name: 'Kiro CLI', href: '/docs/integrations/coding-agents/kiro-cli', category: 'coding', summary: 'Trace macOS CLI sessions, turns and completed tools through hooks.', method: 'Hook-to-OTLP', logo: 'generic-framework' },
  { id: 'langsmith', name: 'LangSmith', href: '/docs/integrations/langsmith', category: 'frameworks', summary: 'Forward supported LangSmith SDK traces over OTLP.', method: 'Native OTLP', logo: 'generic-framework' },
  {"id": "mlflow", "name": "MLflow", "href": "/docs/integrations/mlflow", "category": "frameworks", "summary": "Export current MLflow traces with OTLP/HTTP.", "method": "Native OTLP", "logo": "generic-framework"},
  { id: 'openai', name: 'OpenAI', href: '/docs/integrations/traceai/openai', category: 'providers', summary: 'Instrument OpenAI client calls in your application.', method: 'traceAI SDK', logo: 'openai' },
  { id: 'openai-go', name: 'OpenAI Go', href: '/docs/integrations/traceai/go/openai', category: 'providers', summary: 'Trace Chat Completions from the official Go SDK.', method: 'traceAI SDK', logo: 'openai' },
  { id: 'anthropic', name: 'Anthropic', href: '/docs/integrations/traceai/anthropic', category: 'providers', summary: 'Capture Claude calls, token usage and latency.', method: 'OpenTelemetry', logo: 'anthropic', aliases: ['Claude'] },
  { id: 'bedrock', name: 'AWS Bedrock', href: '/docs/integrations/traceai/bedrock', category: 'providers', summary: 'Trace model calls through Amazon Bedrock.', method: 'traceAI SDK', logo: 'bedrock', aliases: ['Amazon'] },
  {"id": "aws-lambda-local", "name": "Lambda local lifecycle", "href": "/docs/integrations/runtimes/aws-lambda", "category": "frameworks", "summary": "Exercise handler reuse and bounded flush attempts locally.", "method": "Local OTLP example", "logo": "generic-framework"},
  { id: 'vertexai', name: 'Vertex AI', href: '/docs/integrations/traceai/vertexai', category: 'providers', summary: 'Instrument Gemini calls through Google Cloud.', method: 'traceAI SDK', logo: 'vertexai', aliases: ['Google', 'Gemini'] },
  { id: 'google-genai', name: 'Google GenAI', href: '/docs/integrations/traceai/google_genai', category: 'providers', summary: 'Trace Gemini requests with the Google GenAI SDK.', method: 'traceAI SDK', logo: 'google', aliases: ['Gemini'] },
  { id: 'gemini-go', name: 'Gemini Go', href: '/docs/integrations/traceai/go/gemini', category: 'providers', summary: 'Trace Gemini generation and embedding calls from the Go Gen AI SDK.', method: 'traceAI SDK', logo: 'google', aliases: ['Google GenAI Go', 'golang'] },
  { id: 'groq', name: 'Groq', href: '/docs/integrations/traceai/groq', category: 'providers', summary: 'Capture model calls made with the Groq SDK.', method: 'traceAI SDK', logo: 'groq' },
  { id: 'replicate', name: 'Replicate', href: '/docs/integrations/traceai/replicate', category: 'providers', summary: 'Trace Python predictions, streamed output and errors.', method: 'traceAI SDK', logo: 'generic-model' },
  { id: 'mistralai', name: 'Mistral AI', href: '/docs/integrations/traceai/mistralai', category: 'providers', summary: 'Instrument Mistral model requests and responses.', method: 'traceAI SDK', logo: 'mistral' },
  { id: 'togetherai', name: 'Together AI', href: '/docs/integrations/traceai/togetherai', category: 'providers', summary: 'Trace Together AI through its OpenAI-compatible API.', method: 'OpenAI client', logo: 'together' },
  { id: 'ollama', name: 'Ollama', href: '/docs/integrations/traceai/ollama', category: 'providers', summary: 'Trace local model calls through the OpenAI client.', method: 'OpenAI client', logo: 'ollama' },
  { id: 'cometapi', name: 'CometAPI', href: '/docs/integrations/providers/cometapi', category: 'providers', summary: 'Trace chat completions through the OpenAI client.', method: 'OpenAI client', logo: 'cometapi' },
  { id: 'typesafe', name: 'TypeSafe (Jev)', href: '/docs/integrations/traceai/typesafe', category: 'providers', summary: 'Trace System One decision calls from the Python client.', method: 'traceAI SDK', logo: 'generic-model', aliases: ['Jev', 'System One'] },
  { id: 'novita-ai', name: 'Novita AI', href: '/docs/integrations/providers/novita-ai', category: 'providers', summary: 'Trace Novita chat completions from your Python app.', method: 'OpenAI client', logo: 'novita' },
  { id: 'litellm-sdk', name: 'LiteLLM SDK', href: '/docs/integrations/traceai/litellm', category: 'frameworks', summary: 'Instrument LiteLLM calls in your Python application.', method: 'traceAI SDK', logo: 'litellm', aliases: ['traceAI-litellm', 'client'] },

  { id: 'cloudwego-eino', name: 'CloudWeGo Eino', href: '/docs/integrations/traceai/go/eino', category: 'frameworks', summary: 'Trace Eino graphs, agents, model calls and tools in Go.', method: 'traceAI SDK', logo: 'generic-framework' },
  { id: 'tavily', name: 'Tavily', href: '/docs/integrations/traceai/tavily', category: 'frameworks', summary: 'Trace Python search, extraction, mapping, crawling and research calls.', method: 'traceAI SDK', logo: 'generic-framework' },
  { id: 'parallel', name: 'Parallel', href: '/docs/integrations/traceai/parallel', category: 'frameworks', summary: 'Trace Python Search and Extract calls, result counts and errors.', method: 'traceAI SDK', logo: 'generic-framework' },
  { id: 'langchain', name: 'LangChain', href: '/docs/integrations/traceai/langchain', category: 'frameworks', summary: 'Trace chains, retrievers, tools and model calls.', method: 'traceAI SDK', logo: 'langchain' },
  { id: 'langgraph', name: 'LangGraph', href: '/docs/integrations/traceai/langgraph', category: 'frameworks', summary: 'Follow agent graph execution and tool calls.', method: 'traceAI SDK', logo: 'langgraph' },
  { id: 'langchain-deep-agents', name: 'LangChain Deep Agents', href: '/docs/integrations/traceai/langchain-deep-agents', category: 'frameworks', summary: 'Trace model calls, filesystem tools, task subagents and sessions.', method: 'traceAI SDK', logo: 'langchain' },
  { id: 'llamaindex', name: 'LlamaIndex', href: '/docs/integrations/traceai/llamaindex', category: 'frameworks', summary: 'Trace retrieval and generation in RAG applications.', method: 'traceAI SDK', logo: 'llamaindex', aliases: ['RAG'] },
  { id: 'llamaindex-workflows', name: 'LlamaIndex Workflows', href: '/docs/integrations/traceai/llamaindex-workflows', category: 'frameworks', summary: 'Capture steps in event-driven agent workflows.', method: 'traceAI SDK', logo: 'llamaindex' },
  { id: 'openai-agents', name: 'OpenAI Agents SDK', href: '/docs/integrations/traceai/openai_agents', category: 'frameworks', summary: 'Trace agent runs, handoffs and tools.', method: 'traceAI SDK', logo: 'openai' },
  { id: 'claude-agent-sdk-typescript', name: 'Claude Agent SDK (TypeScript)', href: '/docs/integrations/traceai/claude-agent-sdk-typescript', category: 'frameworks', summary: 'Trace Node.js agent conversations, tools and subagents.', method: 'traceAI SDK', logo: 'anthropic' },
  { id: 'google-adk', name: 'Google ADK', href: '/docs/integrations/traceai/google_adk', category: 'frameworks', summary: 'Instrument agents built with Google ADK for Python.', method: 'traceAI SDK', logo: 'google', aliases: ['Agent Development Kit'] },
  { id: 'google-discovery-engine', name: 'Google Discovery Engine', href: '/docs/integrations/traceai/google-discovery-engine', category: 'frameworks', summary: 'Trace Vertex AI Search queries and grounded-answer requests.', method: 'traceAI SDK', logo: 'google', aliases: ['Vertex AI Search', 'Agent Search'] },
  { id: 'crewai', name: 'CrewAI', href: '/docs/integrations/traceai/crewai', category: 'frameworks', summary: 'Trace crews, standalone agents, Flows and model calls.', method: 'Native OTLP', logo: 'crewai' },
  { id: 'autogen', name: 'AutoGen', href: '/docs/integrations/traceai/autogen', category: 'frameworks', summary: 'Trace conversations between AutoGen agents.', method: 'traceAI SDK', logo: 'autogen' },
  { id: 'microsoft-agent-framework', name: 'Microsoft Agent Framework', href: '/docs/integrations/traceai/microsoft-agent-framework', category: 'frameworks', summary: 'Map native Python agent, model, tool and workflow spans.', method: 'OTel + traceAI', logo: 'generic-framework', aliases: ['Agent Framework', 'MAF', 'agent-framework'] },
  { id: 'ag2', name: 'AG2', href: '/docs/integrations/traceai/ag2', category: 'frameworks', summary: 'Trace agent turns, model calls and tools with AG2 native middleware.', method: 'OTel + traceAI', logo: 'generic-framework' },
  { id: 'ag2-classic', name: 'AG2 Classic', href: '/docs/integrations/traceai/ag2-classic', category: 'frameworks', summary: 'Trace native autogen 0.14.x conversations, model calls and tools.', method: 'OTel + traceAI', logo: 'autogen', aliases: ['autogen 0.14', 'traceAI-ag2-classic'] },
  { id: 'semantic-kernel-python', name: 'Semantic Kernel (Python)', href: '/docs/integrations/traceai/semantic-kernel', category: 'frameworks', summary: 'Trace native Python agent, tool and model spans.', method: 'Native OTel + traceAI', logo: 'generic-framework', aliases: ['Microsoft Semantic Kernel', 'traceAI-semantic-kernel'] },
  { id: 'haystack', name: 'Haystack', href: '/docs/integrations/traceai/haystack', category: 'frameworks', summary: 'Trace component execution in Haystack pipelines.', method: 'traceAI SDK', logo: 'haystack' },
  { id: 'dspy', name: 'DSPy', href: '/docs/integrations/traceai/dspy', category: 'frameworks', summary: 'Capture DSPy module and language model calls.', method: 'traceAI SDK', logo: 'dspy' },
  { id: 'smol-agents', name: 'Hugging Face smolagents', href: '/docs/integrations/traceai/smol_agents', category: 'frameworks', summary: 'Trace agent execution and tool calls in smolagents.', method: 'traceAI SDK', logo: 'huggingface' },
  { id: 'instructor', name: 'Instructor', href: '/docs/integrations/traceai/instructor', category: 'frameworks', summary: 'Trace structured-output requests and validation.', method: 'traceAI SDK', logo: 'instructor' },
  { id: 'promptflow', name: 'Prompt Flow', href: '/docs/integrations/traceai/promptflow', category: 'frameworks', summary: 'Trace OpenAI calls inside Prompt Flow pipelines.', method: 'OpenAI client', logo: 'promptflow', aliases: ['PromptFlow'] },
  { id: 'guardrails', name: 'Guardrails AI', href: '/docs/integrations/traceai/guardrails', category: 'frameworks', summary: 'Capture validation and guard execution spans.', method: 'traceAI SDK', logo: 'guardrails' },
  { id: 'exa', name: 'Exa', href: '/docs/integrations/traceai/exa', category: 'frameworks', summary: 'Trace search, contents and answer calls from the Python client.', method: 'traceAI SDK', logo: 'generic-framework', aliases: ['Exa search', 'exa-py', 'traceAI-exa'] },
  { id: 'fastmcp-python', name: 'FastMCP Python', href: '/docs/integrations/frameworks/fastmcp', category: 'frameworks', summary: 'Export native Python MCP client and server spans.', method: 'Native OTLP', logo: 'mcp' },
  { id: 'mcp-python', name: 'MCP for Python', href: '/docs/integrations/traceai/mcp-python', category: 'frameworks', summary: 'Export native MCP 2.x client requests and server tool spans.', method: 'Native OTLP', logo: 'mcp', aliases: ['Model Context Protocol Python'] },
  { id: 'mcp', name: 'Model Context Protocol', href: '/docs/integrations/traceai/mcp', category: 'frameworks', summary: 'Propagate context with TypeScript and existing Python MCP integrations.', method: 'traceAI SDK', logo: 'mcp', aliases: ['MCP'] },
  { id: 'firecrawl', name: 'Firecrawl', href: '/docs/integrations/traceai/firecrawl', category: 'frameworks', summary: 'Trace Python web scraping, search, crawl and browser operations.', method: 'traceAI SDK', logo: 'generic-framework' },
  { id: 'genkit', name: 'Firebase Genkit', href: '/docs/integrations/traceai/genkit', category: 'frameworks', summary: 'Trace native Genkit flow, model and tool spans with a maintained processor.', method: 'traceAI SDK', logo: 'generic-framework' },
  { id: 'mcp-use', name: 'mcp-use', href: '/docs/integrations/traceai/mcp-use', category: 'frameworks', summary: 'Trace Python agent runs, model calls and MCP tools.', method: 'traceAI callback', logo: 'mcp' },
  { id: 'mastra', name: 'Mastra', href: '/docs/integrations/traceai/mastra', category: 'frameworks', summary: 'Trace TypeScript agents and workflows in Mastra.', method: 'traceAI SDK', logo: 'mastra' },
  { id: 'voltagent', name: 'VoltAgent', href: '/docs/integrations/traceai/voltagent', category: 'frameworks', summary: 'Map native agent, model, tool and memory spans to Future AGI.', method: 'traceAI SDK', logo: 'generic-framework' },
  { id: 'vercel-ai-sdk', name: 'Vercel AI SDK', href: '/docs/integrations/traceai/vercel', category: 'frameworks', summary: 'Capture model and tool calls from the Vercel AI SDK.', method: 'traceAI SDK', logo: 'vercel' },
  { id: 'vercel-ai-sdk-python', name: 'AI SDK for Python', href: '/docs/integrations/frameworks/vercel-ai-sdk-python', category: 'frameworks', summary: 'Export native Python AI SDK generation, agent and tool spans.', method: 'OpenTelemetry', logo: 'vercel', aliases: ['Vercel Python', 'Vercel AI SDK Python'] },
  { id: 'vercel-platform', name: 'Vercel / Next.js', href: '/docs/integrations/runtimes/vercel', category: 'frameworks', summary: 'Export native Next.js request spans directly over OTLP/HTTP.', method: 'Native OTLP', logo: 'vercel', aliases: ['Vercel platform', 'Next.js', '@vercel/otel'] },
  { id: 'scalekit', name: 'Scalekit', href: '/docs/integrations/frameworks/scalekit', category: 'frameworks', summary: 'Trace Node.js executeTool calls as privacy-conscious tool spans.', method: 'OpenTelemetry', logo: 'generic-framework' },
  { id: 'tanstack-ai', name: 'TanStack AI', href: '/docs/integrations/frameworks/tanstack-ai', category: 'frameworks', summary: 'Send otelMiddleware chat, model-call and tool spans from Node.js.', method: 'OpenTelemetry', logo: 'generic-framework', aliases: ['TanStack'] },
  { id: 'beeai', name: 'BeeAI', href: '/docs/integrations/frameworks/beeai', category: 'frameworks', summary: 'Trace Python tools and model calls with OpenInference.', method: 'OpenTelemetry', logo: 'generic-framework', aliases: ['IBM BeeAI', 'traceai-beeai'] },
  { id: 'agentscope', name: 'AgentScope', href: '/docs/integrations/frameworks/agentscope', category: 'frameworks', summary: 'Export native agent, model and tool spans.', method: 'OpenTelemetry', logo: 'agentscope' },
  { id: 'apollo-graphql', name: 'Apollo Server', href: '/docs/integrations/frameworks/apollo-graphql', category: 'frameworks', summary: 'Trace GraphQL operations and resolvers in Server 4.', method: 'OpenTelemetry', logo: 'apollo', aliases: ['Apollo GraphQL'] },
  { id: 'apollo-router', name: 'Apollo Router', href: '/docs/integrations/frameworks/apollo-router', category: 'frameworks', summary: 'Export native federated GraphQL gateway spans over OTLP/HTTP.', method: 'OpenTelemetry', logo: 'apollo', aliases: ['GraphOS Router', 'Federation'] },
  { id: 'embabel', name: 'Embabel', href: '/docs/integrations/frameworks/embabel', category: 'frameworks', summary: 'Export JVM agent spans with the observability starter.', method: 'OpenTelemetry', logo: 'embabel', aliases: ['Spring Boot', 'Java', 'Kotlin'] },
  { id: 'eve', name: 'Eve', href: '/docs/integrations/frameworks/eve', category: 'frameworks', summary: 'Send agent-turn spans from Vercel’s Eve framework.', method: 'OpenTelemetry', logo: 'eve', aliases: ['Vercel eve'] },
  { id: 'flue', name: 'Flue', href: '/docs/integrations/frameworks/flue', category: 'frameworks', summary: 'Connect durable Node.js agents with Flue’s adapter.', method: 'OpenTelemetry', logo: 'flue', aliases: ['Astro'] },
  { id: 'graphite', name: 'Graphite (grafi)', href: '/docs/integrations/frameworks/graphite', category: 'frameworks', summary: 'Export Python agent spans through ExecutionServices.', method: 'OpenTelemetry', logo: 'graphite', aliases: ['grafi', 'Binome'] },
  { id: 'koog', name: 'Koog', href: '/docs/integrations/frameworks/koog', category: 'frameworks', summary: 'Export Kotlin JVM agent spans with Koog’s OTel feature.', method: 'OpenTelemetry', logo: 'koog', aliases: ['Kotlin', 'JVM'] },
  { id: 'mirascope', name: 'Mirascope', href: '/docs/integrations/frameworks/mirascope', category: 'frameworks', summary: 'Send Mirascope 2.x model spans with your own exporter.', method: 'OpenTelemetry', logo: 'mirascope' },
  { id: 'open-agent-spec', name: 'Open Agent Spec', href: '/docs/integrations/frameworks/open-agent-spec', category: 'frameworks', summary: 'Trace Agent Spec agents through the LangGraph adapter.', method: 'traceAI SDK', logo: 'open-agent-spec', aliases: ['Oracle', 'pyagentspec'] },
  { id: 'restate', name: 'Restate', href: '/docs/integrations/frameworks/restate', category: 'frameworks', summary: 'Connect durable invocation, attempt and model spans.', method: 'OTel + traceAI', logo: 'restate' },
  { id: 'ruby-llm', name: 'RubyLLM', href: '/docs/integrations/frameworks/ruby-llm', category: 'frameworks', summary: 'Trace RubyLLM calls with the third-party OTel gem.', method: 'OpenTelemetry', logo: 'ruby-llm', aliases: ['Ruby LLM', 'ruby_llm'] },
  { id: 'swiftide', name: 'Swiftide', href: '/docs/integrations/frameworks/swiftide', category: 'frameworks', summary: 'Send typed Rust agent, model and tool spans through an OpenTelemetry Collector.', method: 'OpenTelemetry', logo: 'swiftide', aliases: ['Rust'] },
  { id: 'temporal', name: 'Temporal', href: '/docs/integrations/frameworks/temporal', category: 'frameworks', summary: 'Follow Python workflows, activities and model calls.', method: 'OTel + traceAI', logo: 'temporal' },
  { id: 'temporal-typescript', name: 'Temporal TypeScript', href: '/docs/integrations/frameworks/temporal-typescript', category: 'frameworks', summary: 'Trace TypeScript workflows and activities with the native plugin.', method: 'OpenTelemetry', logo: 'temporal', aliases: ['Temporal JS', 'Temporal Node.js'] },
  { id: 'temporal-go', name: 'Temporal Go', href: '/docs/integrations/frameworks/temporal-go', category: 'frameworks', summary: 'Trace Go workflows and activities with the official OTel interceptor.', method: 'OpenTelemetry', logo: 'temporal', aliases: ['Go Temporal'] },
  { id: 'watsonx-orchestrate-adk', name: 'watsonx Orchestrate ADK', href: '/docs/integrations/frameworks/watsonx-orchestrate-adk', category: 'frameworks', summary: 'Forward Agentic SDK spans through a collector.', method: 'OTel collector', logo: 'watsonx', aliases: ['IBM', 'Agentic SDK'] },
  { id: 'langfuse-sdk', name: 'Langfuse SDK', href: '/docs/sdk/tracing/langfuse-integration', category: 'frameworks', summary: 'Send new traces with Langfuse SDK instrumentation.', method: 'SDK tracing', logo: 'langfuse', sharedGuide: true },

  { id: 'portkey', name: 'Portkey', href: '/docs/integrations/traceai/portkey', category: 'gateways', summary: 'Instrument Portkey client calls in your application.', method: 'traceAI SDK', logo: 'portkey' },
  { id: 'envoy-ai-gateway', name: 'Envoy AI Gateway', href: '/docs/integrations/gateways/envoy-ai-gateway', category: 'gateways', summary: 'Export the gateway’s OpenAI-endpoint spans over OTLP.', method: 'Gateway OTLP', logo: 'envoy' },
  { id: 'cloudflare-ai-gateway', name: 'Cloudflare AI Gateway', href: '/docs/integrations/gateways/cloudflare-ai-gateway', category: 'gateways', summary: 'Map gateway exports through a privacy-filtering collector.', method: 'Gateway OTLP', logo: 'generic-cloud' },
  { id: 'gravitee', name: 'Gravitee APIM', href: '/docs/integrations/gateways/gravitee', category: 'gateways', summary: 'Forward APIM request spans, not AI Gateway traces.', method: 'OTel collector', logo: 'gravitee', aliases: ['Gravitee Gateway'] },
  { id: 'kong-ai-gateway', name: 'Kong AI Gateway', href: '/docs/integrations/gateways/kong-ai-gateway', category: 'gateways', summary: 'Export GenAI spans with Kong’s OpenTelemetry plugin.', method: 'Gateway OTLP', logo: 'kong' },
  { id: 'litellm-proxy', name: 'LiteLLM Proxy', href: '/docs/integrations/gateways/litellm-proxy', category: 'gateways', summary: 'Export request spans from the proxy server’s callback.', method: 'Gateway OTLP', logo: 'litellm', aliases: ['server'] },
  { id: 'vercel-ai-gateway', name: 'Vercel AI Gateway', href: '/docs/integrations/gateways/vercel-ai-gateway', category: 'gateways', summary: 'Trace gateway calls from your app, not Trace Drains.', method: 'OpenAI client', logo: 'vercel' },

  { id: 'google-genai-live', name: 'Gemini Live', href: '/docs/integrations/traceai/google_genai_live', category: 'voice', summary: 'Trace Python Live sessions, conversation turns and tool calls.', method: 'traceAI SDK', logo: 'google', aliases: ['Google GenAI Live'] },
  { id: 'livekit', name: 'LiveKit', href: '/docs/integrations/traceai/livekit', category: 'voice', summary: 'Trace voice agent sessions and model interactions.', method: 'traceAI SDK', logo: 'livekit' },
  { id: 'pipecat', name: 'Pipecat', href: '/docs/integrations/traceai/pipecat', category: 'voice', summary: 'Capture spans from conversational voice pipelines.', method: 'traceAI SDK', logo: 'pipecat' },
  { id: 'elevenlabs-agents', name: 'ElevenLabs Agents', href: '/docs/integrations/traceai/elevenlabs-agents', category: 'voice', summary: 'Forward post-call conversation traces, turns and tool calls.', method: 'traceAI forwarder', logo: 'generic-framework' },
  { id: 'openai-realtime', name: 'OpenAI Realtime', href: '/docs/integrations/traceai/openai_realtime', category: 'voice', summary: 'Trace server-side OpenAI Realtime sessions from Python.', method: 'traceAI SDK', logo: 'openai' },
  { id: 'vapi', name: 'Vapi', href: '/docs/observe/concepts/voice-observability', category: 'voice', summary: 'Connect calls using the shared voice observability guide.', method: 'Voice guide', logo: 'vapi', sharedGuide: true },
  { id: 'retell', name: 'Retell', href: '/docs/observe/concepts/voice-observability', category: 'voice', summary: 'Connect calls using the shared voice observability guide.', method: 'Voice guide', logo: 'retell', sharedGuide: true },

  { id: 'spring-boot', name: 'Spring Boot & Spring AI', href: '/docs/integrations/traceai/spring-boot', category: 'java', summary: 'Set up tracing with the Spring Boot starter.', method: 'Java starter', logo: 'spring', aliases: ['JVM'] },
  { id: 'java-openai', name: 'OpenAI for Java', href: '/docs/integrations/traceai/java/openai', category: 'java', summary: 'Wrap the OpenAI Java client to capture requests.', method: 'Java wrapper', logo: 'openai' },
  { id: 'java-anthropic', name: 'Anthropic for Java', href: '/docs/integrations/traceai/java/anthropic', category: 'java', summary: 'Export native Claude SDK spans without wrapping the client.', method: 'OpenTelemetry', logo: 'anthropic' },
  { id: 'java-bedrock', name: 'AWS Bedrock for Java', href: '/docs/integrations/traceai/java/bedrock', category: 'java', summary: 'Wrap Bedrock clients to capture model requests.', method: 'Java wrapper', logo: 'bedrock' },
  { id: 'java-cohere', name: 'Cohere for Java', href: '/docs/integrations/traceai/java/cohere', category: 'java', summary: 'Trace Cohere requests from your Java client.', method: 'Java wrapper', logo: 'cohere' },
  { id: 'java-pinecone', name: 'Pinecone for Java', href: '/docs/integrations/traceai/java/pinecone', category: 'java', summary: 'Capture vector queries and upserts in Java.', method: 'Java wrapper', logo: 'pinecone' },
  { id: 'java-google-adk', name: 'Google ADK for Java', href: '/docs/integrations/traceai/java/google-adk', category: 'java', summary: 'Export ADK’s native spans without a new instrumentor.', method: 'OpenTelemetry', logo: 'google', aliases: ['Google ADK Java', 'Agent Development Kit', 'JVM'] },
  { id: 'java-llm-providers', name: 'More Java model providers', href: '/docs/integrations/traceai/java/llm-providers', category: 'java', summary: 'Set up GenAI, Vertex AI, Azure OpenAI and other clients.', method: 'Java wrappers', logo: 'generic-model', aliases: ['Ollama', 'Watsonx'] },
  { id: 'java-vector-databases', name: 'Java vector databases', href: '/docs/integrations/traceai/java/vector-databases', category: 'java', summary: 'Trace Qdrant, Milvus, ChromaDB and other vector stores.', method: 'Java wrappers', logo: 'generic-database', aliases: ['Weaviate', 'Redis', 'MongoDB'] },
  { id: 'java-frameworks', name: 'Java frameworks', href: '/docs/integrations/traceai/java/frameworks', category: 'java', summary: 'Connect LangChain4j and Semantic Kernel applications.', method: 'Java wrappers', logo: 'generic-framework', aliases: ['LangChain4j', 'Semantic Kernel'] },

  { id: 'n8n', name: 'n8n', href: '/docs/integrations/traceai/n8n', category: 'apps', summary: 'Use Future AGI prompts in visual n8n workflows.', method: 'Prompt API', logo: 'n8n' },
  { id: 'librechat', name: 'LibreChat', href: '/docs/integrations/no-code/librechat', category: 'apps', summary: 'Forward agent runs and backend spans from LibreChat.', method: 'OTel collector', logo: 'librechat' },
  { id: 'open-webui', name: 'Open WebUI', href: '/docs/integrations/no-code/open-webui', category: 'apps', summary: 'Trace self-hosted chat turns through the version-scoped filter Function.', method: 'Filter Function', logo: 'generic-framework' },
  { id: 'lobechat', name: 'LobeHub', href: '/docs/integrations/no-code/lobechat', category: 'apps', summary: 'Export server-side agent runs from self-hosted LobeHub.', method: 'OTel collector', logo: 'lobehub', aliases: ['LobeChat'] },

  { id: 'langfuse-import', name: 'Langfuse import', href: '/docs/integrations/import/langfuse', category: 'import', summary: 'Import existing traces and scores from your account.', method: 'Trace import', logo: 'langfuse' },
  { id: 'datadog', name: 'Datadog', href: '/docs/integrations/export/datadog', category: 'export', summary: 'Forward logs and metrics to your monitoring stack.', method: 'Data export', logo: 'datadog' },
  { id: 'posthog', name: 'PostHog', href: '/docs/integrations/export/posthog', category: 'export', summary: 'Send LLM usage events to product analytics.', method: 'Data export', logo: 'posthog' },
  { id: 'mixpanel', name: 'Mixpanel', href: '/docs/integrations/export/mixpanel', category: 'export', summary: 'Connect LLM usage events with product behavior.', method: 'Data export', logo: 'mixpanel' },
  { id: 'pagerduty', name: 'PagerDuty', href: '/docs/integrations/export/pagerduty', category: 'export', summary: 'Route Future AGI alerts to your on-call team.', method: 'Alerts', logo: 'pagerduty' },
  { id: 'cloud-storage', name: 'Cloud storage', href: '/docs/integrations/export/cloud-storage', category: 'export', summary: 'Archive trace data in S3, Azure Blob or Google Cloud.', method: 'Data export', logo: 'generic-cloud', aliases: ['AWS', 'S3', 'Azure', 'GCS'] },
  { id: 'message-queues', name: 'Message queues', href: '/docs/integrations/export/message-queues', category: 'export', summary: 'Stream events to Amazon SQS or Google Pub/Sub.', method: 'Data export', logo: 'generic-queue', aliases: ['AWS', 'SQS', 'PubSub', 'Pub/Sub'] },
];

// Overview aids are links, not product-logo cards. Keep them in the same source.
export const integrationAids = [
  { name: 'DeepSeek Harness support status', href: '/docs/integrations/deepseek-harness', category: 'coding' },
  { name: 'Dify support status', href: '/docs/integrations/no-code/dify', category: 'apps' },
  { name: 'Flowise support status', href: '/docs/integrations/no-code/flowise', category: 'apps' },
  { name: 'NeMo Agent Toolkit support status', href: '/docs/integrations/frameworks/nvidia-nemo-agent-toolkit', category: 'frameworks' },
  { name: 'Langdock support status', href: '/docs/integrations/no-code/langdock', category: 'apps' },
  { name: 'Inferable support status', href: '/docs/integrations/inferable', category: 'frameworks' },
  { name: 'AI SDK C++ support status', href: '/docs/integrations/frameworks/ai-sdk-cpp', category: 'frameworks' },
  { name: 'Devin (hosted) support status', href: '/docs/integrations/coding-agents/devin', category: 'coding' },
  { name: 'Hook-to-OTLP emitter', href: '/docs/integrations/coding-agents/hook-to-otlp', category: 'coding' },
  { name: 'OpenAI Assistants retirement', href: '/docs/integrations/traceai/openai_assistants', category: 'providers' },
  { name: 'traceAI setup', href: '/docs/integrations/traceai' },
  { name: 'OpenTelemetry GenAI compatibility', href: '/docs/integrations/traceai/otel-genai-conformance' },
  { name: 'Trace privacy settings', href: '/docs/sdk/tracing/trace-config' },
  { name: 'Java SDK setup', href: '/docs/integrations/traceai/java', category: 'java' },
];

// Earlier published copies remain reachable; prefer their current traceAI guide
// in discovery rather than displaying the same integration twice.
export const integrationAliases = {
  '/docs/integrations/google-adk': '/docs/integrations/traceai/google_adk',
  '/docs/integrations/google-genai': '/docs/integrations/traceai/google_genai',
  '/docs/integrations/openai-agents': '/docs/integrations/traceai/openai_agents',
  '/docs/integrations/smol-agents': '/docs/integrations/traceai/smol_agents',
};

/** @param {ReadonlyArray<Integration>} entries */
export function validateIntegrations(entries = integrations) {
  const categories = new Set(integrationCategories.map(c => c.id));
  const ids = new Set();
  const routes = new Map();
  for (const entry of entries) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(entry.id) || ids.has(entry.id)) throw new Error(`Invalid or duplicate integration ID: ${entry.id}`);
    ids.add(entry.id);
    if (!categories.has(entry.category)) throw new Error(`Unknown category: ${entry.category}`);
    if (!/^\/docs\/[a-z0-9_/-]+$/.test(entry.href)) throw new Error(`Invalid integration route: ${entry.href}`);
    if (![entry.name, entry.summary, entry.method, entry.logo].every(value => typeof value === 'string' && value.trim())) throw new Error(`Incomplete integration: ${entry.id}`);
    if (/\b(?:not tested|alpha)\b/i.test([entry.name, entry.summary, entry.method].join(' '))) throw new Error(`Internal status in catalog: ${entry.id}`);
    if (routes.has(entry.href) && !(entry.sharedGuide && routes.get(entry.href).sharedGuide)) throw new Error(`Duplicate integration route: ${entry.href}`);
    routes.set(entry.href, entry);
  }
  return true;
}
validateIntegrations();

/** @param {Integration} entry */
export function integrationSearchText(entry) {
  const category = integrationCategories.find(c => c.id === entry.category);
  return [entry.name, entry.summary, entry.method, category?.name, ...(entry.aliases || [])].join(' ').toLocaleLowerCase('en');
}

/** @param {IntegrationCategory} category */
export function integrationsInCategory(category) {
  return integrations.filter(entry => entry.category === category).sort((a, b) => a.name.localeCompare(b.name, 'en'));
}

// Machine-readable exports use the same catalog, not a second list in MDX.
export function integrationDirectoryMarkdown() {
  return [
    ...integrationCategories.flatMap(category => [
      `### ${category.name}`,
      '',
      category.description,
      '',
      ...integrationsInCategory(category.id).map(entry => `- [${entry.name}](${entry.href}) — ${entry.summary} Connection: ${entry.method}.`),
      '',
    ]),
    '### Getting started',
    '',
    ...integrationAids.map(aid => `- [${aid.name}](${aid.href})`),
  ].join('\n');
}

// The navigation tree is generated from the same entries as the directory.
export const integrationNavigation = [
  { title: 'All integrations', href: '/docs/integrations' },
  ...integrationAids.filter(a => !a.category).map(a => ({ title: a.name, href: a.href })),
  ...integrationCategories.map(category => ({
    title: category.name,
    collapsible: true,
    items: [
      ...integrationAids.filter(a => a.category === category.id).map(a => ({ title: a.name, href: a.href })),
      ...integrationsInCategory(category.id).map(i => ({ title: i.name, href: i.href })),
    ],
  })),
];
