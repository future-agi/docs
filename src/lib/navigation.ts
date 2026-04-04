/**
 * Navigation Structure
 * Based on Future AGI documentation structure
 * Migrated from Mintlify docs.json
 *
 * Tab-based navigation: Each tab has its own sidebar groups
 */

export interface NavItem {
  title: string;
  href?: string;
  icon?: string;
  badge?: string;
  items?: NavItem[];  // For nested groups
}

export interface NavGroup {
  group: string;
  icon?: string;
  items: NavItem[];
}

export interface NavTab {
  tab: string;
  icon: string;
  href: string;  // Base path for this tab
  groups: NavGroup[];
}

// Main tab-based navigation structure
export const tabNavigation: NavTab[] = [
  {
    tab: 'Docs',
    icon: 'book',
    href: '/docs',
    groups: [
      {
        group: 'Get Started',
        icon: 'rocket',
        items: [
          { title: 'Introduction', href: '/docs' },
          { title: 'Self-Hosting', href: '/docs/self-hosting', badge: 'Soon' },
          {
            title: 'Quickstart',
            icon: 'rocket',
            href: '/docs',
            items: [
              { title: 'Setup Observability', href: '/docs/quickstart/setup-observability' },
              { title: 'Running Evals in Simulation', href: '/docs/quickstart/running-evals-in-simulation' },
              { title: 'Generate Synthetic Data', href: '/docs/quickstart/generate-synthetic-data' },
              { title: 'Create Prompts', href: '/docs/quickstart/prompts' },
              { title: 'Setup MCP Server', href: '/docs/quickstart/setup-mcp-server' },
              { title: 'Annotations Quickstart', href: '/docs/annotations/quickstart' },
              { title: 'Prism AI Gateway Quickstart', href: '/docs/prism/quickstart' },
            ]
          },
        ]
      },
      {
        group: 'Annotations',
        icon: 'pen',
        items: [
          { title: 'Overview', href: '/docs/annotations' },
          {
            title: 'Concepts',
            items: [
              { title: 'Scores', href: '/docs/annotations/concepts/scores' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Labels', href: '/docs/annotations/features/labels' },
              { title: 'Queues', href: '/docs/annotations/features/queues' },
              { title: 'Add Items to Queues', href: '/docs/annotations/features/add-items' },
              { title: 'Annotate Items', href: '/docs/annotations/features/annotate' },
              { title: 'Inline Annotations', href: '/docs/annotations/features/inline' },
              { title: 'Analytics & Agreement', href: '/docs/annotations/features/analytics' },
              { title: 'Export Annotations', href: '/docs/annotations/features/export' },
              { title: 'Automation Rules', href: '/docs/annotations/features/automation' },
            ]
          },
          {
            title: 'SDK',
            items: [
              { title: 'Python SDK', href: '/docs/annotations/sdk/python' },
              { title: 'JavaScript SDK', href: '/docs/annotations/sdk/javascript' },
            ]
          },
        ]
      },
      {
        group: 'Dataset',
        icon: 'table',
        items: [
          { title: 'Overview', href: '/docs/dataset' },
          {
            title: 'Concepts',
            items: [
              { title: 'Understanding Datasets', href: '/docs/dataset/concept/understanding-dataset' },
              { title: 'Static Columns', href: '/docs/dataset/concept/static-column' },
              { title: 'Dynamic Columns', href: '/docs/dataset/concept/dynamic-column' },
              { title: 'Synthetic Data', href: '/docs/dataset/concept/synthetic-data' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Create New Dataset', href: '/docs/dataset/features/create' },
              { title: 'Add Rows to Dataset', href: '/docs/dataset/features/add-rows' },
              { title: 'Add Columns to Dataset', href: '/docs/dataset/features/add-columns' },
              { title: 'Run Prompt in Dataset', href: '/docs/dataset/features/run-prompt' },
              { title: 'Experiments in Dataset', href: '/docs/dataset/features/experiments' },
              { title: 'Add Annotation', href: '/docs/dataset/features/annotate' },
            ]
          },
        ]
      },
      {
        group: 'Error Feed',
        icon: 'compass',
        items: [
          { title: 'Overview', href: '/docs/error-feed' },
          {
            title: 'Concepts',
            items: [
              { title: 'Error Taxonomy', href: '/docs/error-feed/concepts/taxonomy' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Using Error Feed', href: '/docs/error-feed/features/using-error-feed' },
            ]
          },
        ]
      },
      {
        group: 'Evaluation',
        icon: 'chart',
        items: [
          { title: 'Overview', href: '/docs/evaluation' },
          {
            title: 'Concepts',
            items: [
              { title: 'Understanding Evaluation', href: '/docs/evaluation/concepts/understanding-evaluation' },
              { title: 'Eval Types', href: '/docs/evaluation/concepts/eval-types' },
              { title: 'Eval Templates', href: '/docs/evaluation/concepts/eval-templates' },
              { title: 'Judge Models', href: '/docs/evaluation/concepts/judge-models' },
              { title: 'Eval Results', href: '/docs/evaluation/concepts/eval-results' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Built-in Evals', href: '/docs/evaluation/builtin' },
              { title: 'Evaluate via Platform & SDK', href: '/docs/evaluation/features/evaluate' },
              { title: 'Create Custom Evals', href: '/docs/evaluation/features/custom' },
              { title: 'Eval Groups', href: '/docs/evaluation/features/groups' },
              { title: 'Use Custom Models', href: '/docs/evaluation/features/custom-models' },
              { title: 'Future AGI Models', href: '/docs/evaluation/features/futureagi-models' },
              { title: 'Evaluate CI/CD Pipeline', href: '/docs/evaluation/features/cicd' },
            ]
          },
        ]
      },
      {
        group: 'Knowledge Base',
        icon: 'brain',
        items: [
          { title: 'Overview', href: '/docs/knowledge-base' },
          {
            title: 'Concepts',
            items: [
              { title: 'Understanding Knowledge Base', href: '/docs/knowledge-base/concepts/concept' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Create KB Using SDK', href: '/docs/knowledge-base/features/sdk' },
              { title: 'Create KB Using UI', href: '/docs/knowledge-base/features/ui' },
            ]
          },
        ]
      },
      {
        group: 'Observability',
        icon: 'eye',
        items: [
          { title: 'Overview', href: '/docs/observe' },
          {
            title: 'Features',
            items: [
              { title: 'Set Up Observability', href: '/docs/observe/features/quickstart' },
              { title: 'Run Evals on Traces', href: '/docs/observe/features/evals' },
              { title: 'Sessions', href: '/docs/observe/features/session' },
              { title: 'Users', href: '/docs/observe/features/users' },
              { title: 'Alerts & Monitors', href: '/docs/observe/features/alerts' },
              { title: 'Annotation Queue Using SDK', href: '/docs/observe/features/annotation-queue-using-sdk' },
            ]
          },
          {
            title: 'Voice Observability',
            items: [
              { title: 'Overview', href: '/docs/observe/voice' },
              { title: 'Set Up Voice Observability', href: '/docs/observe/voice/set-up' },
            ]
          },
          {
            title: 'Tracing',
            items: [
              { title: 'Overview', href: '/docs/tracing' },
              {
                title: 'Concept',
                items: [
                  { title: 'Understanding Observability', href: '/docs/tracing/concepts' },
                  { title: 'Components of Observability', href: '/docs/tracing/concepts/components' },
                  { title: 'What are Spans?', href: '/docs/tracing/concepts/spans' },
                  { title: 'What are Traces?', href: '/docs/tracing/concepts/traces' },
                  { title: 'What is OpenTelemetry?', href: '/docs/tracing/concepts/otel' },
                  { title: 'What is traceAI?', href: '/docs/tracing/concepts/traceai' },
                ]
              },
              {
                title: 'Manual Tracing',
                items: [
                  { title: 'Set Up Tracing', href: '/docs/tracing/manual/set-up-tracing' },
                  { title: 'Instrument with traceAI Helpers', href: '/docs/tracing/manual/instrument-with-traceai-helpers' },
                  { title: 'Get Current Tracer and Span', href: '/docs/tracing/manual/get-current-span-context' },
                  { title: 'Enriching Spans with Attributes, Metadata, and Tags', href: '/docs/tracing/manual/add-attributes-metadata-tags' },
                  { title: 'Logging Prompt Templates & Variables', href: '/docs/tracing/manual/log-prompt-templates' },
                  { title: 'Integrate Events, Exceptions, and Status into Spans', href: '/docs/tracing/manual/add-events-exceptions-status' },
                  { title: 'Set Session ID and User ID', href: '/docs/tracing/manual/set-session-user-id' },
                  { title: 'Tool Spans Creation', href: '/docs/tracing/manual/create-tool-spans' },
                  { title: 'Mask Span Attributes', href: '/docs/tracing/manual/mask-span-attributes' },
                  { title: 'Advanced Tracing (OTEL)', href: '/docs/tracing/manual/advanced-tracing-examples' },
                  { title: 'FI Semantic Conventions', href: '/docs/tracing/manual/semantic-conventions' },
                  { title: 'In-line Evaluations', href: '/docs/tracing/manual/in-line-evals' },
                  { title: 'Adding Annotations to your Spans', href: '/docs/tracing/manual/annotating-using-api' },
                  { title: 'Langfuse Integration', href: '/docs/tracing/manual/langfuse-integration' },
                ]
              },
            ]
          },
          {
            title: 'Integration',
            items: [
              { title: 'Overview', href: '/docs/tracing/auto' },
              {
                title: 'LLM Providers',
                items: [
                  { title: 'OpenAI', href: '/docs/tracing/auto/openai' },
                  { title: 'Anthropic', href: '/docs/tracing/auto/anthropic' },
                  { title: 'AWS Bedrock', href: '/docs/tracing/auto/bedrock' },
                  { title: 'Vertex AI', href: '/docs/tracing/auto/vertexai' },
                  { title: 'Google GenAI', href: '/docs/tracing/auto/google_genai' },
                  { title: 'Google ADK', href: '/docs/tracing/auto/google_adk' },
                  { title: 'Groq', href: '/docs/tracing/auto/groq' },
                  { title: 'MistralAI', href: '/docs/tracing/auto/mistralai' },
                  { title: 'Together AI', href: '/docs/tracing/auto/togetherai' },
                  { title: 'Ollama', href: '/docs/tracing/auto/ollama' },
                  { title: 'Portkey', href: '/docs/tracing/auto/portkey' },
                ]
              },
              {
                title: 'Frameworks & Agents',
                items: [
                  { title: 'LangChain', href: '/docs/tracing/auto/langchain' },
                  { title: 'LangGraph', href: '/docs/tracing/auto/langgraph' },
                  { title: 'LlamaIndex', href: '/docs/tracing/auto/llamaindex' },
                  { title: 'LlamaIndex Workflows', href: '/docs/tracing/auto/llamaindex-workflows' },
                  { title: 'LiteLLM', href: '/docs/tracing/auto/litellm' },
                  { title: 'CrewAI', href: '/docs/tracing/auto/crewai' },
                  { title: 'AutoGen', href: '/docs/tracing/auto/autogen' },
                  { title: 'Haystack', href: '/docs/tracing/auto/haystack' },
                  { title: 'DSPy', href: '/docs/tracing/auto/dspy' },
                  { title: 'OpenAI Agents', href: '/docs/tracing/auto/openai_agents' },
                  { title: 'Smol Agents', href: '/docs/tracing/auto/smol_agents' },
                  { title: 'Instructor', href: '/docs/tracing/auto/instructor' },
                  { title: 'PromptFlow', href: '/docs/tracing/auto/promptflow' },
                  { title: 'Guardrails', href: '/docs/tracing/auto/guardrails' },
                  { title: 'MCP', href: '/docs/tracing/auto/mcp' },
                  { title: 'Mastra', href: '/docs/tracing/auto/mastra' },
                  { title: 'Vercel AI SDK', href: '/docs/tracing/auto/vercel' },
                ]
              },
              {
                title: 'Voice & Realtime',
                items: [
                  { title: 'LiveKit', href: '/docs/tracing/auto/livekit' },
                  { title: 'Pipecat', href: '/docs/tracing/auto/pipecat' },
                ]
              },
              {
                title: 'Java',
                items: [
                  { title: 'Overview', href: '/docs/tracing/auto/java' },
                  { title: 'Spring Boot', href: '/docs/tracing/auto/spring-boot' },
                  { title: 'OpenAI', href: '/docs/tracing/auto/java/openai' },
                  { title: 'Anthropic', href: '/docs/tracing/auto/java/anthropic' },
                  { title: 'AWS Bedrock', href: '/docs/tracing/auto/java/bedrock' },
                  { title: 'Cohere', href: '/docs/tracing/auto/java/cohere' },
                  { title: 'Pinecone', href: '/docs/tracing/auto/java/pinecone' },
                  { title: 'LLM Providers', href: '/docs/tracing/auto/java/llm-providers' },
                  { title: 'Vector Databases', href: '/docs/tracing/auto/java/vector-databases' },
                  { title: 'Frameworks', href: '/docs/tracing/auto/java/frameworks' },
                ]
              },
              {
                title: 'Other',
                items: [
                  { title: 'n8n', href: '/docs/integrations/traceai/n8n' },
                ]
              },
            ]
          },
        ]
      },
      {
        group: 'Optimization',
        icon: 'gauge',
        items: [
          { title: 'Overview', href: '/docs/optimization' },
          {
            title: 'Concepts',
            items: [
              { title: 'Understanding Optimization', href: '/docs/optimization/concepts/concept' },
              { title: 'Bayesian Search', href: '/docs/optimization/optimizers/bayesian-search' },
              { title: 'Meta-Prompt', href: '/docs/optimization/optimizers/meta-prompt' },
              { title: 'ProTeGi', href: '/docs/optimization/optimizers/protegi' },
              { title: 'PromptWizard', href: '/docs/optimization/optimizers/promptwizard' },
              { title: 'GEPA', href: '/docs/optimization/optimizers/gepa' },
              { title: 'Random Search', href: '/docs/optimization/optimizers/random-search' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Using Python SDK', href: '/docs/optimization/features/using-python-sdk' },
              { title: 'Using Platform', href: '/docs/optimization/features/using-platform' },
            ]
          },
        ]
      },
      {
        group: 'Prism AI Gateway',
        icon: 'server',
        items: [
          { title: 'Overview', href: '/docs/prism' },
          {
            title: 'Concepts',
            items: [
              { title: 'Core Concepts', href: '/docs/prism/concepts/core' },
              { title: 'API Reference', href: '/docs/prism/concepts/api-reference' },
              { title: 'Configuration', href: '/docs/prism/concepts/configuration' },
              { title: 'Platform Integration', href: '/docs/prism/concepts/platform-integration' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Manage Providers', href: '/docs/prism/features/providers' },
              { title: 'Routing & Reliability', href: '/docs/prism/features/routing' },
              { title: 'Guardrails', href: '/docs/prism/features/guardrails' },
              { title: 'Caching', href: '/docs/prism/features/caching' },
              { title: 'Cost Tracking & Budgets', href: '/docs/prism/features/cost-tracking' },
              { title: 'Streaming', href: '/docs/prism/features/streaming' },
              { title: 'Shadow Experiments', href: '/docs/prism/features/shadow-experiments' },
              { title: 'Rate Limiting', href: '/docs/prism/features/rate-limiting' },
              { title: 'MCP & A2A', href: '/docs/prism/features/mcp-a2a' },
            ]
          },
          {
            title: 'Deployment',
            items: [
              { title: 'Self-Hosted', href: '/docs/prism/deployment/self-hosted' },
            ]
          },
        ]
      },
      {
        group: 'Prompt',
        icon: 'zap',
        items: [
          { title: 'Overview', href: '/docs/prompt' },
          {
            title: 'Concepts',
            items: [
              { title: 'Prompt Engineering', href: '/docs/prompt/concepts/prompt-engineering' },
              { title: 'Understanding Prompts', href: '/docs/prompt/concepts/understanding-prompts' },
              { title: 'Versions and Labels', href: '/docs/prompt/concepts/versions-and-labels' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Create Prompt from Scratch', href: '/docs/prompt/features/create-from-scratch' },
              { title: 'Create from Existing Template', href: '/docs/prompt/features/create-from-template' },
              { title: 'Create with AI', href: '/docs/prompt/features/create-with-ai' },
              { title: 'Prompt Workbench Using SDK', href: '/docs/prompt/features/sdk' },
              { title: 'Linked Traces', href: '/docs/prompt/features/linked-traces' },
              { title: 'Manage Folders', href: '/docs/prompt/features/folders' },
            ]
          },
        ]
      },
      {
        group: 'Protect',
        icon: 'shield',
        items: [
          { title: 'Overview', href: '/docs/protect' },
          {
            title: 'Concepts',
            items: [
              { title: 'Use Cases', href: '/docs/protect/concepts/concept' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Run Protect via SDK', href: '/docs/protect/features/run-protect' },
            ]
          },
        ]
      },
      {
        group: 'Agent Playground',
        icon: 'play-circle',
        items: [
          { title: 'Overview', href: '/docs/agent-playground' },
          {
            title: 'Concepts',
            items: [
              { title: 'Understanding Agent Playground', href: '/docs/agent-playground/concepts/understanding-agent-playground' },
              { title: 'Versions & Execution', href: '/docs/agent-playground/concepts/versions-and-execution' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Create a Graph', href: '/docs/agent-playground/features/create-graph' },
              { title: 'Build a Workflow', href: '/docs/agent-playground/features/build-workflow' },
              { title: 'Run & Monitor', href: '/docs/agent-playground/features/run-and-monitor' },
            ]
          },
        ]
      },
      {
        group: 'Prototype',
        icon: 'flask',
        items: [
          { title: 'Overview', href: '/docs/prototype' },
          {
            title: 'Concepts',
            items: [
              { title: 'Understanding Prototype', href: '/docs/prototype/concepts/understanding-prototype' },
              { title: 'Versions and Runs', href: '/docs/prototype/concepts/versions-and-runs' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Set Up Prototype', href: '/docs/prototype/features/set-up-prototype' },
              { title: 'Evals', href: '/docs/prototype/features/evals' },
              { title: 'Choose Winner', href: '/docs/prototype/features/choose-winner' },
            ]
          },
        ]
      },
      {
        group: 'Resources',
        icon: 'book',
        items: [
          { title: 'Admin & Settings', href: '/docs/admin-settings' },
          {
            title: 'Settings Pages',
            items: [
              { title: 'API Keys', href: '/docs/admin-settings/api-keys' },
              { title: 'Profile & Security', href: '/docs/admin-settings/profile-security' },
              { title: 'Organization Settings', href: '/docs/admin-settings/organization-settings' },
              { title: 'User Management', href: '/docs/admin-settings/user-management' },
              { title: 'Workspace Management', href: '/docs/admin-settings/workspace-management' },
              { title: 'AI Providers', href: '/docs/admin-settings/ai-providers' },
              { title: 'Integrations', href: '/docs/admin-settings/integrations' },
              { title: 'Usage Summary', href: '/docs/admin-settings/usage-summary' },
              { title: 'Billing & Pricing', href: '/docs/admin-settings/billing-pricing' },
            ]
          },
          { title: 'Roles & Permissions', href: '/docs/roles-and-permissions' },
          { title: 'Installation', href: '/docs/installation' },
          { title: 'FAQ', href: '/docs/faq' },
          { title: 'Release Notes', href: '/docs/release-notes' },
        ]
      },
      {
        group: 'Simulation',
        icon: 'play',
        items: [
          { title: 'Overview', href: '/docs/simulation' },
          {
            title: 'Concepts',
            items: [
              { title: 'Agent Definition', href: '/docs/simulation/concepts/agent-definition' },
              { title: 'Scenarios', href: '/docs/simulation/concepts/scenarios' },
              { title: 'Personas', href: '/docs/simulation/concepts/personas' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Run Voice Simulation', href: '/docs/simulation/features/run-simulation' },
              { title: 'Chat Simulation Using SDK', href: '/docs/simulation/features/simulation-using-sdk' },
              { title: 'Replay', href: '/docs/simulation/features/observe-to-simulate' },
              { title: 'Prompt Simulation', href: '/docs/simulation/features/prompt-simulation' },
              { title: 'Evaluate Tool Calling', href: '/docs/simulation/features/evaluate-tool-calling' },
              { title: 'View Results', href: '/docs/simulation/features/view-results' },
              { title: 'Fix My Agent', href: '/docs/simulation/features/fix-my-agent' },
            ]
          },
        ]
      },
    ]
  },
  {
    tab: 'Integrations',
    icon: 'plug',
    href: '/docs/integrations',
    groups: [
      {
        group: 'Integrations',
        items: [
          { title: 'Overview', href: '/docs/integrations' },
          {
            title: 'LLM Providers',
            items: [
              { title: 'OpenAI', href: '/docs/integrations/traceai/openai' },
              { title: 'Anthropic', href: '/docs/integrations/traceai/anthropic' },
              { title: 'AWS Bedrock', href: '/docs/integrations/traceai/bedrock' },
              { title: 'Vertex AI', href: '/docs/integrations/traceai/vertexai' },
              { title: 'Google GenAI', href: '/docs/integrations/traceai/google_genai' },
              { title: 'Google ADK', href: '/docs/integrations/traceai/google_adk' },
              { title: 'Groq', href: '/docs/integrations/traceai/groq' },
              { title: 'MistralAI', href: '/docs/integrations/traceai/mistralai' },
              { title: 'Together AI', href: '/docs/integrations/traceai/togetherai' },
              { title: 'Ollama', href: '/docs/integrations/traceai/ollama' },
              { title: 'Portkey', href: '/docs/integrations/traceai/portkey' },
            ]
          },
          {
            title: 'Frameworks & Agents',
            items: [
              { title: 'LangChain', href: '/docs/integrations/traceai/langchain' },
              { title: 'LangGraph', href: '/docs/integrations/traceai/langgraph' },
              { title: 'LlamaIndex', href: '/docs/integrations/traceai/llamaindex' },
              { title: 'LlamaIndex Workflows', href: '/docs/integrations/traceai/llamaindex-workflows' },
              { title: 'LiteLLM', href: '/docs/integrations/traceai/litellm' },
              { title: 'CrewAI', href: '/docs/integrations/traceai/crewai' },
              { title: 'AutoGen', href: '/docs/integrations/traceai/autogen' },
              { title: 'Haystack', href: '/docs/integrations/traceai/haystack' },
              { title: 'DSPy', href: '/docs/integrations/traceai/dspy' },
              { title: 'OpenAI Agents', href: '/docs/integrations/traceai/openai_agents' },
              { title: 'Smol Agents', href: '/docs/integrations/traceai/smol_agents' },
              { title: 'Instructor', href: '/docs/integrations/traceai/instructor' },
              { title: 'PromptFlow', href: '/docs/integrations/traceai/promptflow' },
              { title: 'Guardrails', href: '/docs/integrations/traceai/guardrails' },
              { title: 'MCP', href: '/docs/integrations/traceai/mcp' },
              { title: 'Mastra', href: '/docs/integrations/traceai/mastra' },
              { title: 'Vercel AI SDK', href: '/docs/integrations/traceai/vercel' },
            ]
          },
          {
            title: 'Voice & Realtime',
            items: [
              { title: 'LiveKit', href: '/docs/integrations/traceai/livekit' },
              { title: 'Pipecat', href: '/docs/integrations/traceai/pipecat' },
            ]
          },
          {
            title: 'Java',
            items: [
              { title: 'Overview', href: '/docs/integrations/traceai/java' },
              { title: 'Spring Boot', href: '/docs/integrations/traceai/spring-boot' },
              { title: 'OpenAI', href: '/docs/integrations/traceai/java/openai' },
              { title: 'Anthropic', href: '/docs/integrations/traceai/java/anthropic' },
              { title: 'AWS Bedrock', href: '/docs/integrations/traceai/java/bedrock' },
              { title: 'Cohere', href: '/docs/integrations/traceai/java/cohere' },
              { title: 'Pinecone', href: '/docs/integrations/traceai/java/pinecone' },
              { title: 'LLM Providers', href: '/docs/integrations/traceai/java/llm-providers' },
              { title: 'Vector Databases', href: '/docs/integrations/traceai/java/vector-databases' },
              { title: 'Frameworks', href: '/docs/integrations/traceai/java/frameworks' },
            ]
          },
          {
            title: 'Other',
            items: [
              { title: 'n8n', href: '/docs/integrations/traceai/n8n' },
            ]
          },
          {
            title: 'Import Traces',
            items: [
              { title: 'Langfuse', href: '/docs/integrations/import/langfuse' },
            ]
          },
          {
            title: 'Export & Alerts',
            items: [
              { title: 'Datadog', href: '/docs/integrations/export/datadog' },
              { title: 'PostHog', href: '/docs/integrations/export/posthog' },
              { title: 'Mixpanel', href: '/docs/integrations/export/mixpanel' },
              { title: 'PagerDuty', href: '/docs/integrations/export/pagerduty' },
              { title: 'Cloud Storage', href: '/docs/integrations/export/cloud-storage' },
              { title: 'Message Queues', href: '/docs/integrations/export/message-queues' },
            ]
          },
        ]
      }
    ]
  },
  {
    tab: 'Cookbooks',
    icon: 'book',
    href: '/docs/cookbook',
    groups: [
      {
        group: 'Cookbooks',
        items: [
          { title: 'Overview', href: '/docs/cookbook' },
          {
            title: 'Quickstart',
            icon: 'rocket',
            items: [
              {
                title: 'Evaluation',
                items: [
                  { title: 'Running Your First Eval', href: '/docs/cookbook/quickstart/first-eval' },
                  { title: 'Custom Eval Metrics: Write Your Own Evaluation Criteria', href: '/docs/cookbook/quickstart/custom-eval-metrics' },
                  { title: 'Hallucination Detection with Faithfulness & Groundedness', href: '/docs/cookbook/quickstart/hallucination-detection' },
                  { title: 'RAG Pipeline Evaluation: Debug Retrieval vs Generation', href: '/docs/cookbook/quickstart/rag-evaluation' },
                  { title: 'Multimodal Evaluation: Images, Audio, and PDF', href: '/docs/cookbook/quickstart/multimodal-eval' },
                  { title: 'Tone, Toxicity, and Bias Detection Evals', href: '/docs/cookbook/quickstart/tone-toxicity-bias-eval' },
                  { title: 'Evaluate Customer Agent Conversations', href: '/docs/cookbook/quickstart/conversation-eval' },
                  { title: 'Dataset SDK: Upload, Evaluate, and Download Results', href: '/docs/cookbook/quickstart/batch-eval' },
                  { title: 'Async Evaluations for Large-Scale Testing', href: '/docs/cookbook/quickstart/async-batch-eval' },
                  { title: 'Text-to-SQL Evaluation', href: '/docs/cookbook/quickstart/text-to-sql-eval' },
                ]
              },
              {
                title: 'Simulation',
                items: [
                  { title: 'Chat Simulation: Run Multi-Persona Conversations via SDK', href: '/docs/cookbook/quickstart/chat-simulation-personas' },
                  { title: 'Voice Simulation: Define Agents, Personas, and Run Call Tests', href: '/docs/cookbook/quickstart/voice-simulation' },
                  { title: 'Tool-Calling Agent Simulation with Tracing', href: '/docs/cookbook/quickstart/tool-calling-simulation' },
                  { title: 'Simulate from the Prompt Workbench', href: '/docs/cookbook/quickstart/prompt-workbench-simulation' },
                ]
              },
              {
                title: 'Dataset',
                items: [
                  { title: 'Create and Manage Datasets from the Dashboard', href: '/docs/cookbook/quickstart/dataset-management' },
                  { title: 'Synthetic Data Generation: Create Test Datasets from a Schema', href: '/docs/cookbook/quickstart/synthetic-data-generation' },
                  { title: 'Annotate Datasets with Human-in-the-Loop Workflows', href: '/docs/cookbook/quickstart/dataset-annotation' },
                  { title: 'Import Datasets from Hugging Face', href: '/docs/cookbook/quickstart/huggingface-dataset-import' },
                  { title: 'Dynamic Dataset Columns: Enrich Rows with AI-Generated Data', href: '/docs/cookbook/quickstart/dynamic-dataset-columns' },
                ]
              },
              {
                title: 'Prompt',
                items: [
                  { title: 'Prompt Versioning: Create, Label, and Serve Prompt Versions', href: '/docs/cookbook/quickstart/prompt-versioning' },
                  { title: 'Prototype and Iterate on LLM Applications', href: '/docs/cookbook/quickstart/prototype-llm-app' },
                ]
              },
              {
                title: 'Observability',
                items: [
                  { title: 'Manual Tracing: Add Custom Spans to Any Application', href: '/docs/cookbook/quickstart/manual-tracing' },
                  { title: 'Session-Based Observability for Multi-Turn Conversations', href: '/docs/cookbook/quickstart/session-observability' },
                  { title: 'Monitoring & Alerts: Track LLM Performance and Set Quality Thresholds', href: '/docs/cookbook/quickstart/monitoring-alerts' },
                  { title: 'Inline Evals in Tracing: Score Every Response as It\'s Generated', href: '/docs/cookbook/quickstart/inline-evals-tracing' },
                  { title: 'Distributed Tracing: Connect Spans Across Services', href: '/docs/cookbook/quickstart/distributed-tracing' },
                ]
              },
              {
                title: 'Optimization',
                items: [
                  { title: 'Prompt Optimization: Improve a Prompt Automatically', href: '/docs/cookbook/quickstart/prompt-optimization' },
                  { title: 'Compare Optimization Strategies: ProTeGi, GEPA, and PromptWizard', href: '/docs/cookbook/quickstart/compare-optimizers' },
                  { title: 'Dataset Optimization: Improve Prompts Directly in Your Dataset', href: '/docs/cookbook/quickstart/dataset-optimization' },
                ]
              },
              {
                title: 'Protect',
                items: [
                  { title: 'Protect: Add Safety Guardrails to LLM Outputs', href: '/docs/cookbook/quickstart/protect-guardrails' },
                ]
              },
              {
                title: 'Knowledge Base',
                items: [
                  { title: 'Knowledge Base: Upload Documents and Query with the SDK', href: '/docs/cookbook/quickstart/knowledge-base' },
                ]
              },
              {
                title: 'Experimentation',
                items: [
                  { title: 'Experimentation: Compare Prompts and Models on a Dataset', href: '/docs/cookbook/quickstart/experimentation-compare-prompts' },
                  { title: 'Evaluation-Driven Development: Score Every Prompt Change Before Shipping', href: '/docs/cookbook/quickstart/eval-driven-dev' },
                  { title: 'CI/CD Eval Pipeline: Automate Quality Gates in GitHub Actions', href: '/docs/cookbook/quickstart/cicd-eval-pipeline' },
                ]
              },
              {
                title: 'Agent Compass',
                items: [
                  { title: 'Agent Compass: Surface Agent Failures Automatically', href: '/docs/cookbook/quickstart/agent-compass-debug' },
                ]
              },
            ]
          },
          {
            title: 'Getting Started',
            icon: 'zap',
            items: [
              { title: 'Using FutureAGI Evals', href: '/docs/cookbook/using-futureagi-evals' },
              { title: 'Using FutureAGI Protect', href: '/docs/cookbook/using-futureagi-protect' },
              { title: 'Using FutureAGI Dataset', href: '/docs/cookbook/using-futureagi-dataset' },
              { title: 'Using FutureAGI KB', href: '/docs/cookbook/using-futureagi-kb' },
            ]
          },
          {
            title: 'Integrations',
            icon: 'plug',
            items: [
              { title: 'Portkey Integration', href: '/docs/cookbook/portkey-integration' },
              { title: 'LangChain/LangGraph', href: '/docs/cookbook/langchain-langgraph' },
              { title: 'LlamaIndex PDF RAG', href: '/docs/cookbook/llamaindex-pdf-rag' },
              { title: 'CrewAI Research Team', href: '/docs/cookbook/crewai-research-team' },
              { title: 'MongoDB', href: '/docs/cookbook/mongodb' },
            ]
          },
          {
            title: 'Evaluation',
            icon: 'chart',
            items: [
              { title: 'Meeting Summarization', href: '/docs/cookbook/meeting-summarization' },
              { title: 'AI SDR Evaluation', href: '/docs/cookbook/ai-sdr' },
              { title: 'AI Agents Evaluation', href: '/docs/cookbook/ai-agents' },
              { title: 'Image Evaluation', href: '/docs/cookbook/image-evaluation' },
            ]
          },
          {
            title: 'Observability',
            icon: 'eye',
            items: [
              { title: 'Implement Observability', href: '/docs/cookbook/observability' },
              { title: 'Text-to-SQL Evaluation', href: '/docs/cookbook/text-to-sql' },
            ]
          },
          {
            title: 'RAG',
            icon: 'search',
            items: [
              { title: 'RAG with LangChain', href: '/docs/cookbook/rag-langchain' },
              { title: 'Evaluate RAG Apps', href: '/docs/cookbook/evaluate-rag' },
              { title: 'Trustworthy RAG Chatbots', href: '/docs/cookbook/trustworthy-rag' },
              { title: 'Decrease RAG Hallucination', href: '/docs/cookbook/decrease-hallucination' },
            ]
          },
          {
            title: 'Optimization',
            icon: 'gauge',
            items: [
              { title: 'End-to-End Prompt Optimization', href: '/docs/cookbook/end-to-end-optimization' },
              { title: 'Basic Prompt Optimization', href: '/docs/cookbook/basic-optimization' },
              { title: 'GEPA Optimization', href: '/docs/cookbook/gepa-optimization' },
              { title: 'Eval Metrics for Optimization', href: '/docs/cookbook/eval-metrics-optimization' },
              { title: 'Compare Strategies', href: '/docs/cookbook/compare-optimization' },
              { title: 'Import Datasets', href: '/docs/cookbook/import-datasets' },
            ]
          },
          {
            title: 'Simulate',
            icon: 'play',
            items: [
              { title: 'Chat Simulation with Fix My Agent', href: '/docs/cookbook/chat-simulation-fix-agent' },
              { title: 'Simulate SDK Demo', href: '/docs/cookbook/simulate-sdk' },
            ]
          },
          {
            title: 'Error Feed',
            icon: 'compass',
            items: [
              { title: 'Error Feed with Google ADK', href: '/docs/cookbook/error-feed/google-adk-multi-agent' },
            ]
          },
        ]
      }
    ]
  },
  {
    tab: 'SDK',
    icon: 'code',
    href: '/docs/sdk',
    groups: [
      {
        group: 'SDK Reference',
        items: [
          { title: 'SDK Overview', href: '/docs/sdk' },
          {
            title: 'AI Evaluation',
            items: [
              { title: 'Overview', href: '/docs/sdk/evals' },
              { title: 'Running Evaluations', href: '/docs/sdk/evals/evaluate' },
              { title: 'Distributed Evaluator', href: '/docs/sdk/evals/distributed' },
              { title: 'AutoEval', href: '/docs/sdk/evals/autoeval' },
              { title: 'Guardrails', href: '/docs/sdk/evals/guardrails-module' },
              { title: 'Local & Hybrid', href: '/docs/sdk/evals/local' },
              { title: 'OpenTelemetry', href: '/docs/sdk/evals/otel' },
              { title: 'Code Security', href: '/docs/sdk/evals/code-security' },
              {
                title: 'Metrics Reference',
                items: [
                  { title: 'Overview', href: '/docs/sdk/evals/metrics' },
                  { title: 'String & Similarity', href: '/docs/sdk/evals/metrics/string' },
                  { title: 'JSON & Structured', href: '/docs/sdk/evals/metrics/json' },
                  { title: 'Hallucination', href: '/docs/sdk/evals/metrics/hallucination' },
                  { title: 'RAG', href: '/docs/sdk/evals/metrics/rag' },
                  { title: 'Agents & Functions', href: '/docs/sdk/evals/metrics/agents' },
                  { title: 'Guardrails', href: '/docs/sdk/evals/metrics/guardrails' },
                ]
              },
              { title: 'Cloud Evals', href: '/docs/sdk/evals/cloud-evals' },
              { title: 'LLM-as-Judge', href: '/docs/sdk/evals/llm-judge' },
              { title: 'Streaming', href: '/docs/sdk/evals/streaming' },
              { title: 'Feedback Loops', href: '/docs/sdk/evals/feedback' },
            ]
          },
          {
            title: 'Core SDK',
            items: [
              { title: 'Datasets', href: '/docs/sdk/datasets' },
              { title: 'Tracing', href: '/docs/sdk/tracing' },
              { title: 'Protect', href: '/docs/sdk/protect' },
              { title: 'Knowledge Base', href: '/docs/sdk/knowledgebase' },
              { title: 'Annotation Queues', href: '/docs/sdk/annotation-queues' },
              { title: 'Prompt Optimization', href: '/docs/sdk/optimization' },
              { title: 'Simulation Testing', href: '/docs/sdk/simulate' },
            ]
          },
        ]
      }
    ]
  },
  {
    tab: 'API',
    icon: 'webhook',
    href: '/docs/api',
    groups: [
      {
        group: 'API Reference',
        items: [
          { title: 'Introduction', href: '/docs/api' },
          {
            title: 'Health',
            items: [
              { title: 'Health Check', href: '/docs/api/health/healthcheck' },
            ]
          },
          {
            title: 'Evals',
            items: [
              { title: 'Get Evals List', href: '/docs/api/evals-list/getevalslist' },
            ]
          },
          {
            title: 'Eval Groups',
            items: [
              { title: 'Create Eval Group', href: '/docs/api/eval-groups/createevalgroup' },
              { title: 'List Eval Groups', href: '/docs/api/eval-groups/listevalgroups' },
              { title: 'Retrieve Eval Group', href: '/docs/api/eval-groups/retrieveevalgroup' },
              { title: 'Update Eval Group', href: '/docs/api/eval-groups/updateevalgroup' },
              { title: 'Delete Eval Group', href: '/docs/api/eval-groups/deleteevalgroup' },
              { title: 'Apply Eval Group', href: '/docs/api/eval-groups/applyevalgroup' },
              { title: 'Edit Eval List', href: '/docs/api/eval-groups/editevallist' },
            ]
          },
          {
            title: 'Eval Logs & Metrics',
            items: [
              { title: 'Get Eval Log Details', href: '/docs/api/eval-logs-metrics/getevallogdetails' },
            ]
          },
          {
            title: 'Scenarios',
            items: [
              { title: 'Create Scenario', href: '/docs/api/scenarios/createscenario' },
              { title: 'Edit Scenario', href: '/docs/api/scenarios/editscenario' },
              { title: 'Add Empty Rows', href: '/docs/api/scenarios/addemptyrowstodataset' },
              { title: 'Add Rows with AI', href: '/docs/api/scenarios/addscenariorowswithai' },
            ]
          },
          {
            title: 'Agent Definitions',
            items: [
              { title: 'Create Agent Definition', href: '/docs/api/agent-definitions/createagentdefinition' },
            ]
          },
          {
            title: 'Agent Versions',
            items: [
              { title: 'Create Agent Version', href: '/docs/api/agent-versions/createagentversion' },
            ]
          },
          {
            title: 'Run Tests',
            items: [
              { title: 'Create Run Test', href: '/docs/api/run-tests/createruntest' },
              { title: 'Execute Run Test', href: '/docs/api/run-tests/executeruntest' },
            ]
          },
          {
            title: 'Datasets',
            items: [
              { title: 'Create Dataset', href: '/docs/api/datasets/create-dataset' },
              { title: 'Upload Dataset from File', href: '/docs/api/datasets/upload-dataset' },
            ]
          },
          {
            title: 'Annotation Scores',
            items: [
              { title: 'Create Score', href: '/docs/api/annotations/scores/create-score' },
              { title: 'Bulk Create Scores', href: '/docs/api/annotations/scores/bulk-create-scores' },
              { title: 'Get Scores for Source', href: '/docs/api/annotations/scores/get-scores-for-source' },
              { title: 'List Scores', href: '/docs/api/annotations/scores/list-scores' },
              { title: 'Delete Score', href: '/docs/api/annotations/scores/delete-score' },
            ]
          },
          {
            title: 'Annotation Labels',
            items: [
              { title: 'Create Label', href: '/docs/api/annotations/labels/create-label' },
              { title: 'List Labels', href: '/docs/api/annotations/labels/list-labels' },
              { title: 'Get Label', href: '/docs/api/annotations/labels/get-label' },
              { title: 'Update Label', href: '/docs/api/annotations/labels/update-label' },
              { title: 'Delete Label', href: '/docs/api/annotations/labels/delete-label' },
              { title: 'Restore Label', href: '/docs/api/annotations/labels/restore-label' },
            ]
          },
          {
            title: 'Annotation Queues',
            items: [
              { title: 'Create Queue', href: '/docs/api/annotations/queues/create-queue' },
              { title: 'List Queues', href: '/docs/api/annotations/queues/list-queues' },
              { title: 'Get Queue', href: '/docs/api/annotations/queues/get-queue' },
              { title: 'Update Queue', href: '/docs/api/annotations/queues/update-queue' },
              { title: 'Delete Queue', href: '/docs/api/annotations/queues/delete-queue' },
              { title: 'Update Status', href: '/docs/api/annotations/queues/update-status' },
              { title: 'Get Progress', href: '/docs/api/annotations/queues/get-progress' },
              { title: 'Get Analytics', href: '/docs/api/annotations/queues/get-analytics' },
              { title: 'Get Agreement', href: '/docs/api/annotations/queues/get-agreement' },
              { title: 'Export', href: '/docs/api/annotations/queues/export' },
              { title: 'Export to Dataset', href: '/docs/api/annotations/queues/export-to-dataset' },
              { title: 'Add Label to Queue', href: '/docs/api/annotations/queues/add-label' },
              { title: 'Remove Label', href: '/docs/api/annotations/queues/remove-label' },
              { title: 'Get or Create Default', href: '/docs/api/annotations/queues/get-or-create-default' },
              { title: 'Find Queues for Source', href: '/docs/api/annotations/queues/find-queues-for-source' },
            ]
          },
          {
            title: 'Queue Items',
            items: [
              { title: 'List Items', href: '/docs/api/annotations/items/list-items' },
              { title: 'Add Items', href: '/docs/api/annotations/items/add-items' },
              { title: 'Bulk Remove Items', href: '/docs/api/annotations/items/bulk-remove-items' },
              { title: 'Get Annotate Detail', href: '/docs/api/annotations/items/get-annotate-detail' },
              { title: 'Get Next Item', href: '/docs/api/annotations/items/get-next-item' },
              { title: 'Submit Annotations', href: '/docs/api/annotations/items/submit-annotations' },
              { title: 'Complete Item', href: '/docs/api/annotations/items/complete-item' },
              { title: 'Skip Item', href: '/docs/api/annotations/items/skip-item' },
              { title: 'Get Item Annotations', href: '/docs/api/annotations/items/get-item-annotations' },
              { title: 'Assign Items', href: '/docs/api/annotations/items/assign-items' },
              { title: 'Release Item', href: '/docs/api/annotations/items/release-item' },
            ]
          },
          {
            title: 'Bulk Annotation',
            items: [
              { title: 'Bulk Annotate Spans', href: '/docs/api/annotations/bulk/bulk-annotate-spans' },
            ]
          },
        ]
      },
    ]
  },
];

// Top nav tabs (derived from tabNavigation)
export const topNav = tabNavigation.map(tab => ({
  title: tab.tab,
  href: tab.href,
  icon: tab.icon,
}));

// Helper function to get navigation for a specific tab based on current path
export function getActiveTab(currentPath: string): NavTab | undefined {
  // Check specific tabs first (integrations, cookbook, sdk, api)
  for (const tab of tabNavigation) {
    if (tab.href !== '/docs' && currentPath.startsWith(tab.href)) {
      return tab;
    }
  }
  // Default to Documentation tab for /docs paths
  if (currentPath.startsWith('/docs') || currentPath === '/') {
    return tabNavigation[0];
  }
  return tabNavigation[0];
}

// Recursively check if any item in a tree matches the current path
function matchesPath(items: NavItem[], normalizedPath: string): boolean {
  for (const item of items) {
    if (item.href) {
      const h = item.href.replace(/\/$/, '') || '/';
      if (h === normalizedPath) return true;
      if (h !== '/' && h !== '/docs' && normalizedPath.startsWith(h + '/')) return true;
    }
    if (item.items && matchesPath(item.items, normalizedPath)) return true;
  }
  return false;
}

// Find the active group within the Docs tab based on current path
export function getActiveGroup(currentPath: string): NavGroup | undefined {
  const docsTab = tabNavigation[0]; // Docs tab
  const normalizedPath = currentPath.replace(/\/$/, '') || '/';

  for (const group of docsTab.groups) {
    if (matchesPath(group.items, normalizedPath)) return group;
  }

  // Default to first group (Get Started)
  return docsTab.groups[0];
}

// Backwards compatibility exports
export const navigation = tabNavigation[0].groups.map(g => ({
  title: g.group,
  icon: g.icon,
  items: g.items.map(i => ({
    title: i.title,
    href: i.href,
    badge: i.badge,
  })),
}));

export const builtinEvals = tabNavigation[0].groups
  .find(g => g.group === 'Evaluation')?.items
  ?.find(i => i.title === 'Built-in Evals')?.items || [];

export const integrations = tabNavigation[1].groups[0].items;

export const cookbooks = tabNavigation[2].groups.flatMap(g => g.items);
