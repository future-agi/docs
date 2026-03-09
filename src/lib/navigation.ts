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
            icon: 'rocket',
            href: '/docs/quickstart',
            items: [
              { title: 'Overview', href: '/docs/quickstart' },
              { title: 'Setup Observability', href: '/docs/quickstart/setup-observability' },
              { title: 'Running Evals in Simulation', href: '/docs/quickstart/running-evals-in-simulation' },
              { title: 'Generate Synthetic Data', href: '/docs/quickstart/generate-synthetic-data' },
              { title: 'Prompts', href: '/docs/quickstart/prompts' },
              { title: 'Create Prompt from Scratch', href: '/docs/prompt/create-from-scratch' },
              { title: 'Setup MCP Server', href: '/docs/quickstart/setup-mcp-server' },
            ]
          },
          { title: 'Best Practices: Synthetic Data', href: '/docs/best-practices/creating-synthetic-data' },
        ]
      },
      {
        group: 'Evaluation',
        icon: 'chart',
        items: [
          { title: 'Overview', href: '/docs/evaluation/overview' },
          { title: 'Running Your First Eval', href: '/docs/evaluation' },
          { title: 'Create Custom Evals', href: '/docs/evaluation/custom' },
          { title: 'Eval Groups', href: '/docs/evaluation/groups' },
          { title: 'Use Custom Models', href: '/docs/evaluation/custom-models' },
          { title: 'Future AGI Models', href: '/docs/evaluation/futureagi-models' },
          { title: 'Evaluate CI/CD Pipeline', href: '/docs/evaluation/cicd' },
          {
            title: 'Built-in Evals',
            href: '/docs/evaluation/builtin',
            items: [
              { title: 'Overview', href: '/docs/evaluation/builtin' },
              {
                title: 'Audio',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/audio' },
                  { title: 'Audio Quality', href: '/docs/evaluation/builtin/audio/audio-quality' },
                  { title: 'Audio Transcription', href: '/docs/evaluation/builtin/audio/audio-transcription' },
                  { title: 'Audio Description Eval', href: '/docs/evaluation/builtin/audio/eval-audio-description' },
                ]
              },
              {
                title: 'Image',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/image' },
                  { title: 'Caption Hallucination', href: '/docs/evaluation/builtin/image/caption-hallucination' },
                  { title: 'Synthetic Image Evaluator', href: '/docs/evaluation/builtin/image/synthetic-image-evaluator' },
                  { title: 'Image Instruction Eval', href: '/docs/evaluation/builtin/image/eval-image-instruction' },
                ]
              },
              {
                title: 'Safety & Moderation',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/safety-moderation' },
                  { title: 'Content Moderation', href: '/docs/evaluation/builtin/safety-moderation/content-moderation' },
                  { title: 'Content Safety Violation', href: '/docs/evaluation/builtin/safety-moderation/content-safety-violation' },
                  { title: 'Toxicity', href: '/docs/evaluation/builtin/safety-moderation/toxicity' },
                  { title: 'Sexist', href: '/docs/evaluation/builtin/safety-moderation/sexist' },
                  { title: 'Is Harmful Advice', href: '/docs/evaluation/builtin/safety-moderation/is-harmful-advice' },
                  { title: 'No Harmful Therapeutic Guidance', href: '/docs/evaluation/builtin/safety-moderation/no-harmful-therapeutic-guidance' },
                  { title: 'Prompt Injection', href: '/docs/evaluation/builtin/safety-moderation/prompt-injection' },
                  { title: 'PII Detection', href: '/docs/evaluation/builtin/safety-moderation/pii' },
                  { title: 'Data Privacy', href: '/docs/evaluation/builtin/safety-moderation/data-privacy' },
                  { title: 'SFW Text', href: '/docs/evaluation/builtin/safety-moderation/sfw-text' },
                ]
              },
              {
                title: 'Bias & Fairness',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/bias-fairness' },
                  { title: 'Bias Detection', href: '/docs/evaluation/builtin/bias-fairness/bias-detection' },
                  { title: 'Cultural Sensitivity', href: '/docs/evaluation/builtin/bias-fairness/cultural-sensitivity' },
                  { title: 'No Age Bias', href: '/docs/evaluation/builtin/bias-fairness/no-age-bias' },
                  { title: 'No Gender Bias', href: '/docs/evaluation/builtin/bias-fairness/no-gender-bias' },
                  { title: 'No Racial Bias', href: '/docs/evaluation/builtin/bias-fairness/no-racial-bias' },
                ]
              },
              {
                title: 'Factuality & Grounding',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/factuality-grounding' },
                  { title: 'Factual Accuracy', href: '/docs/evaluation/builtin/factuality-grounding/factual-accuracy' },
                  { title: 'Is Factually Consistent', href: '/docs/evaluation/builtin/factuality-grounding/is-factually-consistent' },
                  { title: 'Detect Hallucination', href: '/docs/evaluation/builtin/factuality-grounding/detect-hallucination' },
                  { title: 'Groundedness', href: '/docs/evaluation/builtin/factuality-grounding/groundedness' },
                  { title: 'Context Adherence', href: '/docs/evaluation/builtin/factuality-grounding/context-adherence' },
                  { title: 'Context Relevance', href: '/docs/evaluation/builtin/factuality-grounding/context-relevance' },
                  { title: 'Context Similarity', href: '/docs/evaluation/builtin/factuality-grounding/context-similarity' },
                ]
              },
              {
                title: 'Quality, Tone & Helpfulness',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/quality-tone-helpfulness' },
                  { title: 'Tone', href: '/docs/evaluation/builtin/quality-tone-helpfulness/tone' },
                  { title: 'Is Polite', href: '/docs/evaluation/builtin/quality-tone-helpfulness/is-polite' },
                  { title: 'Is Informal Tone', href: '/docs/evaluation/builtin/quality-tone-helpfulness/is-informal-tone' },
                  { title: 'Clinically Inappropriate Tone', href: '/docs/evaluation/builtin/quality-tone-helpfulness/clinically-inappropriate-tone' },
                  { title: 'Is Helpful', href: '/docs/evaluation/builtin/quality-tone-helpfulness/is-helpful' },
                  { title: 'Is Concise', href: '/docs/evaluation/builtin/quality-tone-helpfulness/is-concise' },
                  { title: 'Completeness', href: '/docs/evaluation/builtin/quality-tone-helpfulness/completeness' },
                  { title: 'Instruction Adherence', href: '/docs/evaluation/builtin/quality-tone-helpfulness/instruction-adherence' },
                  { title: 'Task Completion', href: '/docs/evaluation/builtin/quality-tone-helpfulness/task-completion' },
                  { title: 'Conversation Coherence', href: '/docs/evaluation/builtin/quality-tone-helpfulness/conversation-coherence' },
                  { title: 'Conversation Resolution', href: '/docs/evaluation/builtin/quality-tone-helpfulness/conversation-resolution' },
                  { title: 'Is Good Summary', href: '/docs/evaluation/builtin/quality-tone-helpfulness/is-good-summary' },
                  { title: 'Summary Quality', href: '/docs/evaluation/builtin/quality-tone-helpfulness/summary-quality' },
                  { title: 'Not Gibberish', href: '/docs/evaluation/builtin/quality-tone-helpfulness/not-gibberish' },
                ]
              },
              {
                title: 'RAG & Retrieval',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/rag-retrieval' },
                  { title: 'Chunk Attribution', href: '/docs/evaluation/builtin/rag-retrieval/chunk-attribution' },
                  { title: 'Chunk Utilization', href: '/docs/evaluation/builtin/rag-retrieval/chunk-utilization' },
                  { title: 'Recall Score', href: '/docs/evaluation/builtin/rag-retrieval/recall-score' },
                  { title: 'Context Retrieval Eval', href: '/docs/evaluation/builtin/rag-retrieval/eval-context-retrieval' },
                ]
              },
              {
                title: 'Similarity & String Metrics',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/similarity-string-metrics' },
                  { title: 'BLEU', href: '/docs/evaluation/builtin/similarity-string-metrics/bleu' },
                  { title: 'ROUGE', href: '/docs/evaluation/builtin/similarity-string-metrics/rouge' },
                  { title: 'Embedding Similarity', href: '/docs/evaluation/builtin/similarity-string-metrics/embedding-similarity' },
                  { title: 'Fuzzy Match', href: '/docs/evaluation/builtin/similarity-string-metrics/fuzzy-match' },
                  { title: 'Levenshtein Similarity', href: '/docs/evaluation/builtin/similarity-string-metrics/lavenshtein-similarity' },
                  { title: 'Numeric Similarity', href: '/docs/evaluation/builtin/similarity-string-metrics/numeric-similarity' },
                  { title: 'Semantic List Contains', href: '/docs/evaluation/builtin/similarity-string-metrics/semantic-list-contains' },
                  { title: 'Answer Similarity', href: '/docs/evaluation/builtin/similarity-string-metrics/answer-similarity' },
                ]
              },
              {
                title: 'Format & Structure',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/format-structure' },
                  { title: 'Is Email', href: '/docs/evaluation/builtin/format-structure/is-email' },
                  { title: 'Is JSON', href: '/docs/evaluation/builtin/format-structure/is-json' },
                  { title: 'Length Evals', href: '/docs/evaluation/builtin/format-structure/length-evals' },
                  { title: 'Valid Links', href: '/docs/evaluation/builtin/format-structure/valid-links' },
                  { title: 'No Apologies', href: '/docs/evaluation/builtin/format-structure/no-apologies' },
                  { title: 'No LLM Reference', href: '/docs/evaluation/builtin/format-structure/no-llm-reference' },
                  { title: 'Is Code', href: '/docs/evaluation/builtin/format-structure/is-code' },
                  { title: 'JSON Schema', href: '/docs/evaluation/builtin/format-structure/json-schema' },
                  { title: 'Regex', href: '/docs/evaluation/builtin/format-structure/regex' },
                  { title: 'Contain Evals', href: '/docs/evaluation/builtin/format-structure/contain-evals' },
                ]
              },
              {
                title: 'Compliance & Refusal',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/compliance-refusal' },
                  { title: 'Answer Refusal', href: '/docs/evaluation/builtin/compliance-refusal/answer-refusal' },
                  { title: 'Is Compliant', href: '/docs/evaluation/builtin/compliance-refusal/is-compliant' },
                ]
              },
              {
                title: 'Specialized',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin/specialized' },
                  { title: 'Eval Ranking', href: '/docs/evaluation/builtin/specialized/eval-ranking' },
                  { title: 'Output Eval', href: '/docs/evaluation/builtin/specialized/eval-output' },
                  { title: 'LLM Function Calling', href: '/docs/evaluation/builtin/specialized/llm-function-calling' },
                  { title: 'Text to SQL', href: '/docs/evaluation/builtin/specialized/text-to-sql' },
                  { title: 'Translation Accuracy', href: '/docs/evaluation/builtin/specialized/translation-accuracy' },
                  { title: 'Score Eval', href: '/docs/evaluation/builtin/specialized/score-eval' },
                  { title: 'Prompt Perplexity', href: '/docs/evaluation/builtin/specialized/prompt-perplexity' },
                  { title: 'Deterministic Eval', href: '/docs/evaluation/builtin/specialized/deterministic-eval' },
                  { title: 'Custom Code', href: '/docs/evaluation/builtin/specialized/custom-code' },
                  { title: 'API Call', href: '/docs/evaluation/builtin/specialized/api-call' },
                  { title: 'Aggregated Metric', href: '/docs/evaluation/builtin/specialized/aggregated-metric' },
                  { title: 'Agent Judge', href: '/docs/evaluation/builtin/specialized/agent-judge' },
                ]
              },
            ]
          },
        ]
      },
      {
        group: 'Observability',
        icon: 'eye',
        items: [
          { title: 'Overview', href: '/docs/observe' },
          { title: 'Set Up Observability', href: '/docs/observe/quickstart' },
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
              {
                title: 'Concept',
                items: [
                  { title: 'Overview', href: '/docs/tracing/concepts' },
                  { title: 'Core Components', href: '/docs/tracing/components' },
                  { title: 'Spans', href: '/docs/tracing/spans' },
                  { title: 'Traces', href: '/docs/tracing/traces' },
                  { title: 'OpenTelemetry', href: '/docs/tracing/otel' },
                  { title: 'TraceAI', href: '/docs/tracing/traceai' },
                ]
              },
              {
                title: 'Instrumentation (Auto)',
                items: [
                  { title: 'Overview', href: '/docs/tracing/auto' },
                  { title: 'Auto Overview', href: '/docs/tracing/auto-overview' },
                  { title: 'Anthropic', href: '/docs/tracing/auto/anthropic' },
                  { title: 'AutoGen', href: '/docs/tracing/auto/autogen' },
                  { title: 'AWS Bedrock', href: '/docs/tracing/auto/bedrock' },
                  { title: 'CrewAI', href: '/docs/tracing/auto/crewai' },
                  { title: 'DSPy', href: '/docs/tracing/auto/dspy' },
                  { title: 'Experiment', href: '/docs/tracing/auto/experiment' },
                  { title: 'Google ADK', href: '/docs/tracing/auto/google_adk' },
                  { title: 'Google GenAI', href: '/docs/tracing/auto/google_genai' },
                  { title: 'Groq', href: '/docs/tracing/auto/groq' },
                  { title: 'Guardrails', href: '/docs/tracing/auto/guardrails' },
                  { title: 'Haystack', href: '/docs/tracing/auto/haystack' },
                  { title: 'Instructor', href: '/docs/tracing/auto/instructor' },
                  { title: 'LangChain', href: '/docs/tracing/auto/langchain' },
                  { title: 'LangGraph', href: '/docs/tracing/auto/langgraph' },
                  { title: 'LiteLLM', href: '/docs/tracing/auto/litellm' },
                  { title: 'LlamaIndex', href: '/docs/tracing/auto/llamaindex' },
                  { title: 'LlamaIndex Workflows', href: '/docs/tracing/auto/llamaindex-workflows' },
                  { title: 'Mastra', href: '/docs/tracing/auto/mastra' },
                  { title: 'MCP', href: '/docs/tracing/auto/mcp' },
                  { title: 'MistralAI', href: '/docs/tracing/auto/mistralai' },
                  { title: 'Ollama', href: '/docs/tracing/auto/ollama' },
                  { title: 'OpenAI', href: '/docs/tracing/auto/openai' },
                  { title: 'OpenAI Agents', href: '/docs/tracing/auto/openai_agents' },
                  { title: 'Pipecat', href: '/docs/tracing/auto/pipecat' },
                  { title: 'Portkey', href: '/docs/tracing/auto/portkey' },
                  { title: 'PromptFlow', href: '/docs/tracing/auto/promptflow' },
                  { title: 'Smol Agents', href: '/docs/tracing/auto/smol_agents' },
                  { title: 'Together AI', href: '/docs/tracing/auto/togetherai' },
                  { title: 'Vercel', href: '/docs/tracing/auto/vercel' },
                  { title: 'Vertex AI', href: '/docs/tracing/auto/vertexai' },
                ]
              },
              {
                title: 'Manual Tracing',
                items: [
                  { title: 'Set Up Tracing', href: '/docs/tracing/manual/set-up-tracing' },
                  { title: 'Instrument with TraceAI', href: '/docs/tracing/manual/instrument-with-traceai-helpers' },
                  { title: 'Get Current Span Context', href: '/docs/tracing/manual/get-current-span-context' },
                  { title: 'Add Attributes & Metadata', href: '/docs/tracing/manual/add-attributes-metadata-tags' },
                  { title: 'Log Prompt Templates', href: '/docs/tracing/manual/log-prompt-templates' },
                  { title: 'Add Events & Exceptions', href: '/docs/tracing/manual/add-events-exceptions-status' },
                  { title: 'Set Session & User ID', href: '/docs/tracing/manual/set-session-user-id' },
                  { title: 'Create Tool Spans', href: '/docs/tracing/manual/create-tool-spans' },
                  { title: 'Mask Span Attributes', href: '/docs/tracing/manual/mask-span-attributes' },
                  { title: 'Advanced Examples', href: '/docs/tracing/manual/advanced-tracing-examples' },
                  { title: 'Semantic Conventions', href: '/docs/tracing/manual/semantic-conventions' },
                  { title: 'Inline Evals', href: '/docs/tracing/manual/in-line-evals' },
                  { title: 'Annotating via API', href: '/docs/tracing/manual/annotating-using-api' },
                  { title: 'Langfuse Integration', href: '/docs/tracing/manual/langfuse-intergation' },
                ]
              },
            ]
          },
        ]
      },
      {
        group: 'Dataset',
        icon: 'table',
        items: [
          { title: 'Overview', href: '/docs/dataset' },
          { title: 'Quickstart', href: '/docs/dataset/quickstart' },
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
          {
            title: 'Concepts',
            items: [
              { title: 'Understanding Datasets', href: '/docs/dataset/concept/understanding-dataset' },
              { title: 'Static Columns', href: '/docs/dataset/concept/static-column' },
              { title: 'Dynamic Columns', href: '/docs/dataset/concept/dynamic-column' },
              { title: 'Synthetic Data', href: '/docs/dataset/concept/synthetic-data' },
            ]
          },
        ]
      },
      {
        group: 'Simulation',
        icon: 'play',
        items: [
          { title: 'Overview', href: '/docs/simulation' },
          {
            title: 'Set Up',
            items: [
              { title: 'Agent Definition', href: '/docs/simulation/set-up/agent-definition' },
              { title: 'Scenarios', href: '/docs/simulation/set-up/scenarios' },
              { title: 'Personas', href: '/docs/simulation/set-up/personas' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'Simulation Using SDK', href: '/docs/simulation/features/simulation-using-sdk' },
              { title: 'Evaluate Tool Calling', href: '/docs/simulation/features/evaluate-tool-calling' },
              { title: 'Fix My Agent', href: '/docs/simulation/features/fix-my-agent' },
              { title: 'Replay', href: '/docs/simulation/features/observe-to-simulate' },
              { title: 'Prompt Simulation', href: '/docs/simulation/features/prompt-simulation' },
            ]
          },
          {
            title: 'Concepts',
            items: [
              { title: 'Concepts', href: '/docs/simulation/concepts/concepts' },
            ]
          },
        ]
      },
      {
        group: 'Prompt',
        icon: 'zap',
        items: [
          { title: 'Overview', href: '/docs/prompt' },
          { title: 'Concept', href: '/docs/prompt/concept' },
          { title: 'Create Prompt', href: '/docs/prompt/create' },
          { title: 'Create Prompt from Scratch', href: '/docs/prompt/create-from-scratch' },
          { title: 'Create from Existing Template', href: '/docs/prompt/create-from-template' },
          { title: 'Create with AI', href: '/docs/prompt/create-with-ai' },
          { title: 'Generate Prompt', href: '/docs/prompt/generate' },
          { title: 'Prompt Templates', href: '/docs/prompt/templates' },
          { title: 'Prompt Workbench Using SDK', href: '/docs/prompt/sdk' },
          { title: 'Linked Traces', href: '/docs/prompt/linked-traces' },
          { title: 'Manage Folders', href: '/docs/prompt/folders' },
          {
            title: 'Prompt Workbench',
            items: [
              { title: 'Overview', href: '/docs/prompt-workbench' },
              { title: 'Concept', href: '/docs/prompt-workbench/concept' },
              { title: 'Using SDK', href: '/docs/prompt-workbench/sdk' },
            ]
          },
        ]
      },
      {
        group: 'Prototype',
        icon: 'flask',
        items: [
          { title: 'Overview', href: '/docs/prototype' },
          { title: 'Set Up Prototype', href: '/docs/prototype/quickstart' },
          { title: 'Evals', href: '/docs/prototype/evals' },
          { title: 'Choose Winner', href: '/docs/prototype/winner' },
        ]
      },
      {
        group: 'Optimization',
        icon: 'gauge',
        items: [
          { title: 'Overview', href: '/docs/optimization' },
          { title: 'Concept', href: '/docs/optimization/concept' },
          { title: 'Product Overview', href: '/docs/optimization/product-overview' },
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
          {
            title: 'How To',
            items: [
              { title: 'Optimize Your First Prompt', href: '/docs/optimization/optimize-first-prompt' },
              { title: 'Using Python SDK', href: '/docs/optimization/using-sdk' },
              { title: 'Using Platform', href: '/docs/optimization/using-platform' },
              { title: 'Dataset Optimization', href: '/docs/optimization/howto-dataset-optimization' },
              { title: 'Dataset Optimization Guide', href: '/docs/optimization/dataset-optimization' },
            ]
          },
        ]
      },
      {
        group: 'Agent Compass',
        icon: 'compass',
        items: [
          { title: 'Overview', href: '/docs/agent-compass' },
          { title: 'Introduction', href: '/docs/agent-compass/overview' },
          { title: 'Quickstart', href: '/docs/agent-compass/quickstart' },
          { title: 'Taxonomy', href: '/docs/agent-compass/taxonomy' },
        ]
      },
      {
        group: 'Experimentation',
        icon: 'flask',
        items: [
          { title: 'Overview', href: '/docs/experimentation' },
          { title: 'Concept', href: '/docs/experimentation/concept' },
          { title: 'How To', href: '/docs/experimentation/how-to' },
        ]
      },
      {
        group: 'Protect',
        icon: 'shield',
        items: [
          { title: 'Overview', href: '/docs/protect' },
          { title: 'Concept', href: '/docs/protect/concept' },
          { title: 'How To', href: '/docs/protect/how-to' },
          { title: 'FAQ', href: '/docs/protect/faq' },
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
              { title: 'Concept', href: '/docs/knowledge-base/concepts/concept' },
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
        group: 'Resources',
        icon: 'book',
        items: [
          { title: 'Admin & Settings', href: '/docs/admin-settings' },
          { title: 'FAQ', href: '/docs/faq' },
          { title: 'Release Notes', href: '/docs/release-notes' },
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
          { title: 'Google ADK', href: '/docs/integrations/google_adk' },
          { title: 'Google GenAI', href: '/docs/integrations/google_genai' },
          { title: 'Groq', href: '/docs/integrations/groq' },
          { title: 'Guardrails', href: '/docs/integrations/guardrails' },
          { title: 'Haystack', href: '/docs/integrations/haystack' },
          { title: 'Instructor', href: '/docs/integrations/instructor' },
          { title: 'LangChain', href: '/docs/integrations/langchain' },
          { title: 'LangGraph', href: '/docs/integrations/langgraph' },
          { title: 'LiteLLM', href: '/docs/integrations/litellm' },
          { title: 'LiveKit', href: '/docs/integrations/livekit' },
          { title: 'LlamaIndex', href: '/docs/integrations/llamaindex' },
          { title: 'Mastra', href: '/docs/integrations/mastra' },
          { title: 'MCP', href: '/docs/integrations/mcp' },
          { title: 'LlamaIndex Workflows', href: '/docs/integrations/llamaindex-workflows' },
          { title: 'MistralAI', href: '/docs/integrations/mistralai' },
          { title: 'n8n', href: '/docs/integrations/n8n' },
          { title: 'Ollama', href: '/docs/integrations/ollama' },
          { title: 'OpenAI', href: '/docs/integrations/openai' },
          { title: 'OpenAI Agents', href: '/docs/integrations/openai_agents' },
          { title: 'Pipecat', href: '/docs/integrations/pipecat' },
          { title: 'Portkey', href: '/docs/integrations/portkey' },
          { title: 'PromptFlow', href: '/docs/integrations/promptflow' },
          { title: 'Smol Agents', href: '/docs/integrations/smol_agents' },
          { title: 'Together AI', href: '/docs/integrations/togetherai' },
          { title: 'Vercel', href: '/docs/integrations/vercel' },
          { title: 'Vertex AI', href: '/docs/integrations/vertexai' },
          { title: 'Experiment', href: '/docs/integrations/experiment' },
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
            title: 'Getting Started',
            icon: 'rocket',
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
