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
          { title: 'Installation', href: '/docs/installation' },
          {
            title: 'Quickstart',
            href: '/docs/quickstart',
            items: [
              { title: 'Overview', href: '/docs/quickstart' },
              { title: 'Setup Observability', href: '/docs/quickstart/observability' },
              { title: 'Generate Synthetic Data', href: '/docs/quickstart/synthetic-data' },
              { title: 'Create Prompts', href: '/docs/quickstart/prompts' },
              { title: 'Setup MCP Server', href: '/docs/quickstart/mcp-server' },
            ]
          },
        ]
      },
      {
        group: 'Dataset',
        icon: 'table',
        items: [
          { title: 'Overview', href: '/docs/dataset' },
          { title: 'Create New Dataset', href: '/docs/dataset/create' },
          { title: 'Add Rows', href: '/docs/dataset/add-rows' },
          { title: 'Quickstart', href: '/docs/dataset/quickstart' },
          { title: 'Run Prompt', href: '/docs/dataset/run-prompt' },
          { title: 'Experiments', href: '/docs/dataset/experiments' },
          { title: 'Annotations', href: '/docs/dataset/annotate' },
        ]
      },
      {
        group: 'Simulation',
        icon: 'play',
        items: [
          { title: 'Overview', href: '/docs/simulation' },
          { title: 'Agent Definition', href: '/docs/simulation/agent-definition' },
          { title: 'Scenarios', href: '/docs/simulation/scenarios' },
          { title: 'Personas', href: '/docs/simulation/personas' },
          { title: 'Run Tests', href: '/docs/simulation/run-tests' },
          { title: 'Tool Calling', href: '/docs/simulation/tool-calling' },
          { title: 'Voice', href: '/docs/simulation/voice' },
        ]
      },
      {
        group: 'Evaluation',
        icon: 'chart',
        items: [
          { title: 'Running Your First Eval', href: '/docs/evaluation' },
          { title: 'Custom Evals', href: '/docs/evaluation/custom' },
          { title: 'Eval Groups', href: '/docs/evaluation/groups' },
          { title: 'Custom Models', href: '/docs/evaluation/custom-models' },
          { title: 'Future AGI Models', href: '/docs/evaluation/futureagi-models' },
          { title: 'CI/CD Pipeline', href: '/docs/evaluation/cicd' },
          {
            title: 'Built-in Evals',
            href: '/docs/evaluation/builtin',
            items: [
              { title: 'Overview', href: '/docs/evaluation/builtin' },
              { title: 'Answer Refusal', href: '/docs/evaluation/builtin/answer-refusal' },
              { title: 'Audio Quality', href: '/docs/evaluation/builtin/audio-quality' },
              { title: 'Audio Transcription', href: '/docs/evaluation/builtin/audio-transcription' },
              { title: 'Bias Detection', href: '/docs/evaluation/builtin/bias-detection' },
              { title: 'BLEU', href: '/docs/evaluation/builtin/bleu' },
              { title: 'Caption Hallucination', href: '/docs/evaluation/builtin/caption-hallucination' },
              { title: 'Chunk Attribution', href: '/docs/evaluation/builtin/chunk-attribution' },
              { title: 'Chunk Utilization', href: '/docs/evaluation/builtin/chunk-utilization' },
              { title: 'Clinically Inappropriate Tone', href: '/docs/evaluation/builtin/clinically-inappropriate-tone' },
              { title: 'Completeness', href: '/docs/evaluation/builtin/completeness' },
              { title: 'Content Moderation', href: '/docs/evaluation/builtin/content-moderation' },
              { title: 'Content Safety Violation', href: '/docs/evaluation/builtin/content-safety-violation' },
              { title: 'Context Adherence', href: '/docs/evaluation/builtin/context-adherence' },
              { title: 'Context Relevance', href: '/docs/evaluation/builtin/context-relevance' },
              { title: 'Conversation Coherence', href: '/docs/evaluation/builtin/conversation-coherence' },
              { title: 'Conversation Resolution', href: '/docs/evaluation/builtin/conversation-resolution' },
              { title: 'Cultural Sensitivity', href: '/docs/evaluation/builtin/cultural-sensitivity' },
              { title: 'Data Privacy', href: '/docs/evaluation/builtin/data-privacy' },
              { title: 'Detect Hallucination', href: '/docs/evaluation/builtin/detect-hallucination' },
              { title: 'Embedding Similarity', href: '/docs/evaluation/builtin/embedding-similarity' },
              { title: 'Eval Ranking', href: '/docs/evaluation/builtin/eval-ranking' },
              { title: 'Factual Accuracy', href: '/docs/evaluation/builtin/factual-accuracy' },
              { title: 'Fuzzy Match', href: '/docs/evaluation/builtin/fuzzy-match' },
              { title: 'Groundedness', href: '/docs/evaluation/builtin/groundedness' },
              { title: 'Instruction Adherence', href: '/docs/evaluation/builtin/instruction-adherence' },
              { title: 'Is Compliant', href: '/docs/evaluation/builtin/is-compliant' },
              { title: 'Is Concise', href: '/docs/evaluation/builtin/is-concise' },
              { title: 'Is Email', href: '/docs/evaluation/builtin/is-email' },
              { title: 'Is Factually Consistent', href: '/docs/evaluation/builtin/is-factually-consistent' },
              { title: 'Is Good Summary', href: '/docs/evaluation/builtin/is-good-summary' },
              { title: 'Is Harmful Advice', href: '/docs/evaluation/builtin/is-harmful-advice' },
              { title: 'Is Helpful', href: '/docs/evaluation/builtin/is-helpful' },
              { title: 'Is Informal Tone', href: '/docs/evaluation/builtin/is-informal-tone' },
              { title: 'Is JSON', href: '/docs/evaluation/builtin/is-json' },
              { title: 'Is Polite', href: '/docs/evaluation/builtin/is-polite' },
              { title: 'Levenshtein Similarity', href: '/docs/evaluation/builtin/lavenshtein-similarity' },
              { title: 'Length Evals', href: '/docs/evaluation/builtin/length-evals' },
              { title: 'LLM Function Calling', href: '/docs/evaluation/builtin/llm-function-calling' },
              { title: 'No Age Bias', href: '/docs/evaluation/builtin/no-age-bias' },
              { title: 'No Apologies', href: '/docs/evaluation/builtin/no-apologies' },
              { title: 'No Gender Bias', href: '/docs/evaluation/builtin/no-gender-bias' },
              { title: 'No Harmful Therapeutic Guidance', href: '/docs/evaluation/builtin/no-harmful-therapeutic-guidance' },
              { title: 'No LLM Reference', href: '/docs/evaluation/builtin/no-llm-reference' },
              { title: 'No Racial Bias', href: '/docs/evaluation/builtin/no-racial-bias' },
              { title: 'Numeric Similarity', href: '/docs/evaluation/builtin/numeric-similarity' },
              { title: 'PII Detection', href: '/docs/evaluation/builtin/pii' },
              { title: 'Prompt Injection', href: '/docs/evaluation/builtin/prompt-injection' },
              { title: 'Recall Score', href: '/docs/evaluation/builtin/recall-score' },
              { title: 'ROUGE', href: '/docs/evaluation/builtin/rouge' },
              { title: 'Semantic List Contains', href: '/docs/evaluation/builtin/semantic-list-contains' },
              { title: 'Sexist', href: '/docs/evaluation/builtin/sexist' },
              { title: 'Summary Quality', href: '/docs/evaluation/builtin/summary-quality' },
              { title: 'Synthetic Image Evaluator', href: '/docs/evaluation/builtin/synthetic-image-evaluator' },
              { title: 'Task Completion', href: '/docs/evaluation/builtin/task-completion' },
              { title: 'Text to SQL', href: '/docs/evaluation/builtin/text-to-sql' },
              { title: 'Tone', href: '/docs/evaluation/builtin/tone' },
              { title: 'Toxicity', href: '/docs/evaluation/builtin/toxicity' },
              { title: 'Translation Accuracy', href: '/docs/evaluation/builtin/translation-accuracy' },
              { title: 'Valid Links', href: '/docs/evaluation/builtin/valid-links' },
            ]
          },
        ]
      },
      {
        group: 'Prompt',
        icon: 'zap',
        items: [
          { title: 'Overview', href: '/docs/prompt' },
          { title: 'Create from Scratch', href: '/docs/prompt/create' },
          { title: 'Use Templates', href: '/docs/prompt/templates' },
          { title: 'SDK Integration', href: '/docs/prompt/sdk' },
          { title: 'Linked Traces', href: '/docs/prompt/linked-traces' },
          { title: 'Manage Folders', href: '/docs/prompt/folders' },
        ]
      },
      {
        group: 'Prototype',
        icon: 'flask',
        items: [
          { title: 'Overview', href: '/docs/prototype' },
          { title: 'Quickstart', href: '/docs/prototype/quickstart' },
          { title: 'Evals', href: '/docs/prototype/evals' },
          { title: 'Winner', href: '/docs/prototype/winner' },
        ]
      },
      {
        group: 'Observability',
        icon: 'eye',
        items: [
          { title: 'Overview', href: '/docs/observe' },
          { title: 'Quickstart', href: '/docs/observe/quickstart' },
          { title: 'Evals', href: '/docs/observe/evals' },
          { title: 'Sessions', href: '/docs/observe/session' },
          { title: 'Users', href: '/docs/observe/users' },
          { title: 'Alerts & Monitors', href: '/docs/observe/alerts' },
          {
            title: 'Voice Observability',
            items: [
              { title: 'Overview', href: '/docs/observe/voice' },
              { title: 'Quickstart', href: '/docs/observe/voice/quickstart' },
            ]
          },
          {
            title: 'Tracing',
            items: [
              { title: 'Overview', href: '/docs/tracing' },
              { title: 'Core Concepts', href: '/docs/tracing/concepts' },
              { title: 'Core Components', href: '/docs/tracing/components' },
              { title: 'Spans', href: '/docs/tracing/spans' },
              { title: 'Traces', href: '/docs/tracing/traces' },
              { title: 'OpenTelemetry', href: '/docs/tracing/otel' },
              { title: 'TraceAI', href: '/docs/tracing/traceai' },
              { title: 'Auto Instrumentation', href: '/docs/tracing/auto' },
            ]
          },
        ]
      },
      {
        group: 'Agent Compass',
        icon: 'compass',
        items: [
          { title: 'Overview', href: '/docs/agent-compass' },
          { title: 'Quickstart', href: '/docs/agent-compass/quickstart' },
          { title: 'Taxonomy', href: '/docs/agent-compass/taxonomy' },
        ]
      },
      {
        group: 'Optimization',
        icon: 'gauge',
        items: [
          { title: 'Overview', href: '/docs/optimization' },
          { title: 'Quickstart', href: '/docs/optimization/quickstart' },
          {
            title: 'Algorithms',
            items: [
              { title: 'Overview', href: '/docs/optimization/overview' },
              { title: 'Bayesian Search', href: '/docs/optimization/bayesian' },
              { title: 'Meta-Prompt', href: '/docs/optimization/meta-prompt' },
              { title: 'ProTeGi', href: '/docs/optimization/protegi' },
              { title: 'PromptWizard', href: '/docs/optimization/promptwizard' },
              { title: 'GEPA', href: '/docs/optimization/gepa' },
              { title: 'Random Search', href: '/docs/optimization/random-search' },
            ]
          },
        ]
      },
      {
        group: 'Protect',
        icon: 'shield',
        items: [
          { title: 'Overview', href: '/docs/protect' },
          { title: 'Concepts', href: '/docs/protect/concept' },
          { title: 'How To', href: '/docs/protect/how-to' },
        ]
      },
      {
        group: 'Knowledge Base',
        icon: 'brain',
        items: [
          { title: 'Overview', href: '/docs/knowledge-base' },
          { title: 'Concepts', href: '/docs/knowledge-base/concept' },
          { title: 'Create via SDK', href: '/docs/knowledge-base/sdk' },
          { title: 'Create via UI', href: '/docs/knowledge-base/ui' },
        ]
      },
      {
        group: 'Resources',
        items: [
          { title: 'Admin & Settings', href: '/docs/admin-settings' },
          { title: 'FAQ', href: '/docs/faq' },
          { title: 'Release Notes', href: '/changelog' },
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
          { title: 'Anthropic', href: '/docs/integrations/anthropic' },
          { title: 'AutoGen', href: '/docs/integrations/autogen' },
          { title: 'AWS Bedrock', href: '/docs/integrations/bedrock' },
          { title: 'CrewAI', href: '/docs/integrations/crewai' },
          { title: 'DSPy', href: '/docs/integrations/dspy' },
          { title: 'Google ADK', href: '/docs/integrations/google-adk' },
          { title: 'Google GenAI', href: '/docs/integrations/google-genai' },
          { title: 'Groq', href: '/docs/integrations/groq' },
          { title: 'Guardrails', href: '/docs/integrations/guardrails' },
          { title: 'Haystack', href: '/docs/integrations/haystack' },
          { title: 'Instructor', href: '/docs/integrations/instructor' },
          { title: 'LangChain', href: '/docs/integrations/langchain' },
          { title: 'LangGraph', href: '/docs/integrations/langgraph' },
          { title: 'LiteLLM', href: '/docs/integrations/litellm' },
          { title: 'LiveKit', href: '/docs/integrations/livekit' },
          { title: 'LlamaIndex', href: '/docs/integrations/llamaindex' },
          { title: 'LlamaIndex Workflows', href: '/docs/integrations/llamaindex-workflows' },
          { title: 'MistralAI', href: '/docs/integrations/mistralai' },
          { title: 'n8n', href: '/docs/integrations/n8n' },
          { title: 'Ollama', href: '/docs/integrations/ollama' },
          { title: 'OpenAI', href: '/docs/integrations/openai' },
          { title: 'OpenAI Agents', href: '/docs/integrations/openai-agents' },
          { title: 'Pipecat', href: '/docs/integrations/pipecat' },
          { title: 'Portkey', href: '/docs/integrations/portkey' },
          { title: 'PromptFlow', href: '/docs/integrations/promptflow' },
          { title: 'Smol Agents', href: '/docs/integrations/smol-agents' },
          { title: 'Together AI', href: '/docs/integrations/togetherai' },
          { title: 'Vercel', href: '/docs/integrations/vercel' },
          { title: 'Vertex AI', href: '/docs/integrations/vertexai' },
        ]
      }
    ]
  },
  {
    tab: 'Guides',
    icon: 'book',
    href: '/docs/cookbook',
    groups: [
      {
        group: 'Getting Started',
        icon: 'rocket',
        items: [
          { title: 'Overview', href: '/docs/cookbook' },
          { title: 'Using FutureAGI Evals', href: '/docs/cookbook/using-futureagi-evals' },
          { title: 'Using FutureAGI Protect', href: '/docs/cookbook/using-futureagi-protect' },
          { title: 'Using FutureAGI Dataset', href: '/docs/cookbook/using-futureagi-dataset' },
          { title: 'Using FutureAGI KB', href: '/docs/cookbook/using-futureagi-kb' },
        ]
      },
      {
        group: 'Integrations',
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
        group: 'Evaluation',
        icon: 'chart',
        items: [
          { title: 'Meeting Summarization', href: '/docs/cookbook/meeting-summarization' },
          { title: 'AI SDR Evaluation', href: '/docs/cookbook/ai-sdr' },
          { title: 'AI Agents Evaluation', href: '/docs/cookbook/ai-agents' },
        ]
      },
      {
        group: 'Observability',
        icon: 'eye',
        items: [
          { title: 'Implement Observability', href: '/docs/cookbook/observability' },
          { title: 'Text-to-SQL Evaluation', href: '/docs/cookbook/text-to-sql' },
        ]
      },
      {
        group: 'RAG',
        icon: 'search',
        items: [
          { title: 'RAG with LangChain', href: '/docs/cookbook/rag-langchain' },
          { title: 'Evaluate RAG Apps', href: '/docs/cookbook/evaluate-rag' },
          { title: 'Trustworthy RAG Chatbots', href: '/docs/cookbook/trustworthy-rag' },
          { title: 'Decrease RAG Hallucination', href: '/docs/cookbook/decrease-hallucination' },
        ]
      },
      {
        group: 'Optimization',
        icon: 'gauge',
        items: [
          { title: 'Basic Prompt Optimization', href: '/docs/cookbook/basic-optimization' },
          { title: 'GEPA Optimization', href: '/docs/cookbook/gepa-optimization' },
          { title: 'Eval Metrics for Optimization', href: '/docs/cookbook/eval-metrics-optimization' },
          { title: 'Compare Strategies', href: '/docs/cookbook/compare-optimization' },
          { title: 'Import Datasets', href: '/docs/cookbook/import-datasets' },
        ]
      },
      {
        group: 'Simulate',
        icon: 'play',
        items: [
          { title: 'Simulate SDK Demo', href: '/docs/cookbook/simulate-sdk' },
        ]
      },
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
          { title: 'Python SDK Client', href: '/docs/sdk' },
          { title: 'Evals', href: '/docs/sdk/evals' },
          { title: 'Datasets', href: '/docs/sdk/datasets' },
          { title: 'Protect', href: '/docs/sdk/protect' },
          { title: 'Knowledge Base', href: '/docs/sdk/knowledgebase' },
          { title: 'Tracing', href: '/docs/sdk/tracing' },
          { title: 'Test Case', href: '/docs/sdk/testcase' },
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
        group: 'Overview',
        icon: 'book',
        items: [
          { title: 'Introduction', href: '/docs/api' },
        ]
      },
      {
        group: 'Health',
        icon: 'check',
        items: [
          { title: 'Health check', href: '/docs/api/health/healthcheck' },
        ]
      },
      {
        group: 'Scenarios',
        icon: 'play',
        items: [
          { title: 'Create scenario', href: '/docs/api/scenarios/createscenario' },
          { title: 'Add rows with AI', href: '/docs/api/scenarios/addscenariorowswithai' },
          { title: 'Edit scenario', href: '/docs/api/scenarios/editscenario' },
          { title: 'Add empty rows', href: '/docs/api/scenarios/addemptyrowstodataset' },
        ]
      },
      {
        group: 'Agent Definitions',
        icon: 'robot',
        items: [
          { title: 'Create agent', href: '/docs/api/agent-definitions/createagentdefinition' },
        ]
      },
      {
        group: 'Agent Versions',
        icon: 'code',
        items: [
          { title: 'Create version', href: '/docs/api/agent-versions/createagentversion' },
        ]
      },
      {
        group: 'Run Tests',
        icon: 'play',
        items: [
          { title: 'Create test run', href: '/docs/api/run-tests/createruntest' },
          { title: 'Execute test', href: '/docs/api/run-tests/executeruntest' },
        ]
      },
      {
        group: 'Eval Groups',
        icon: 'chart',
        items: [
          { title: 'List groups', href: '/docs/api/eval-groups/listevalgroups' },
          { title: 'Create group', href: '/docs/api/eval-groups/createevalgroup' },
          { title: 'Get group', href: '/docs/api/eval-groups/retrieveevalgroup' },
          { title: 'Update group', href: '/docs/api/eval-groups/updateevalgroup' },
          { title: 'Delete group', href: '/docs/api/eval-groups/deleteevalgroup' },
          { title: 'Edit members', href: '/docs/api/eval-groups/editevallist' },
          { title: 'Apply group', href: '/docs/api/eval-groups/applyevalgroup' },
        ]
      },
      {
        group: 'Eval Logs',
        icon: 'search',
        items: [
          { title: 'Get log details', href: '/docs/api/eval-logs-metrics/getevallogdetails' },
          { title: 'Get evals list', href: '/docs/api/evals-list/getevalslist' },
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
  .find(i => i.title === 'Built-in Evals')?.items || [];

export const integrations = tabNavigation[1].groups[0].items;

export const cookbooks = tabNavigation[2].groups.flatMap(g => g.items);
