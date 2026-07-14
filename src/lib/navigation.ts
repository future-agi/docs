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
          { title: 'Overview', href: '/docs' },
          {
            title: 'Bring your data in',
            items: [
              { title: 'Send your first trace', href: '/docs/get-started/send-your-first-trace' },
              { title: 'Route your first LLM request', href: '/docs/get-started/route-your-first-llm-request' },
              { title: 'Connect no code agents', href: '/docs/get-started/connect-no-code-agents' },
              { title: 'Create your first prompt', href: '/docs/get-started/create-your-first-prompt' },
            ]
          },
          {
            title: 'Migrate',
            items: [
              { title: 'Migrate from Langfuse', href: '/docs/get-started/migrate/langfuse' },
              { title: 'Migrate from LangSmith', badge: 'Coming soon' },
              { title: 'Migrate from Arize', badge: 'Coming soon' },
            ]
          },
          {
            title: 'Self-Hosting',
            items: [
              { title: 'Overview', href: '/docs/self-hosting' },
              { title: 'Requirements', href: '/docs/self-hosting/requirements' },
              { title: 'Installation', href: '/docs/self-hosting/installation' },
              {
                title: 'Configuration',
                items: [
                  { title: 'System configuration', href: '/docs/self-hosting/configuration/system' },
                  { title: 'Environment variables', href: '/docs/self-hosting/configuration/environment' },
                ]
              },
              {
                title: 'Production',
                items: [
                  { title: 'Overview', href: '/docs/self-hosting/production' },
                  { title: 'Checklist', href: '/docs/self-hosting/production/checklist' },
                  { title: 'Security & TLS', href: '/docs/self-hosting/production/security-tls' },
                  { title: 'Backups & restore', href: '/docs/self-hosting/production/backups-restore' },
                  { title: 'Monitoring', href: '/docs/self-hosting/production/monitoring' },
                  { title: 'Upgrades & rollback', href: '/docs/self-hosting/production/upgrades-rollback' },
                ]
              },
              { title: 'Troubleshooting & FAQs', href: '/docs/self-hosting/troubleshooting' },
              { title: 'Support', href: '/docs/self-hosting/support' },
            ]
          },
          {
            title: 'Release notes',
            items: [
              { title: "What's new", href: '/docs/release-notes' },
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
              { title: 'Annotation Queue Using SDK', href: '/docs/annotations/sdk/annotation-queue-using-sdk' },
            ]
          },
        ]
      },
      {
        group: 'Agent Command Center',
        icon: 'server',
        items: [
          { title: 'Overview', href: '/docs/command-center' },
          {
            title: 'Concepts',
            items: [
              { title: 'How it works', href: '/docs/command-center/concepts/core' },
              { title: 'Virtual keys & access control', href: '/docs/command-center/concepts/virtual-keys' },
              { title: 'Configuration', href: '/docs/command-center/concepts/configuration' },
              { title: 'Platform integration', href: '/docs/command-center/concepts/platform-integration' },
            ]
          },
          {
            title: 'Features',
            items: [
              {
                title: 'Providers',
                items: [
                  { title: 'Supported providers', href: '/docs/command-center/features/providers' },
                  { title: 'Self-hosted models', href: '/docs/command-center/features/self-hosted-models' },
                ]
              },
              {
                title: 'API Reference',
                items: [
                  { title: 'Endpoints overview', href: '/docs/command-center/api/endpoints' },
                  { title: 'Chat completions', href: '/docs/command-center/api/chat' },
                  { title: 'Embeddings & reranking', href: '/docs/command-center/api/embeddings' },
                  { title: 'Media endpoints', href: '/docs/command-center/api/media' },
                  { title: 'Assistants API', href: '/docs/command-center/api/assistants' },
                  { title: 'Files & vector stores', href: '/docs/command-center/api/files' },
                  { title: 'Async & batch', href: '/docs/command-center/api/async-batch' },
                  { title: 'Request & response headers', href: '/docs/command-center/api/headers' },
                ]
              },
              {
                title: 'Routing',
                items: [
                  { title: 'Routing & reliability', href: '/docs/command-center/features/routing' },
                ]
              },
              {
                title: 'Safety & Policy',
                items: [
                  { title: 'Guardrails', href: '/docs/command-center/features/guardrails' },
                ]
              },
              {
                title: 'Performance',
                items: [
                  { title: 'Caching', href: '/docs/command-center/features/caching' },
                  { title: 'Rate limiting', href: '/docs/command-center/features/rate-limiting' },
                ]
              },
              {
                title: 'Cost & Observability',
                items: [
                  { title: 'Cost tracking', href: '/docs/command-center/features/cost-tracking' },
                  { title: 'Observability', href: '/docs/command-center/features/observability' },
                  { title: 'Shadow experiments', href: '/docs/command-center/features/shadow-experiments' },
                  { title: 'Webhooks', href: '/docs/command-center/features/webhooks' },
                  { title: 'Custom Properties', href: '/docs/command-center/features/custom-properties' },
                ]
              },
              {
                title: 'Agentic',
                items: [
                  { title: 'MCP & A2A', href: '/docs/command-center/features/mcp-a2a' },
                ]
              },
            ]
          },
          {
            title: 'Admin',
            items: [
              { title: 'Organization management', href: '/docs/command-center/admin/organizations' },
            ]
          },
          {
            title: 'Deployment',
            items: [
              { title: 'Self-hosted', href: '/docs/command-center/deployment/self-hosted' },
            ]
          },
          {
            title: 'Guides',
            items: [
              { title: 'Error handling', href: '/docs/command-center/guides/errors' },
              { title: 'Troubleshooting', href: '/docs/command-center/guides/troubleshooting' },
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
              { title: 'How It Works', href: '/docs/error-feed/concepts/how-it-works' },
              { title: 'Error Taxonomy', href: '/docs/error-feed/concepts/taxonomy' },
              { title: 'Scoring', href: '/docs/error-feed/concepts/scoring' },
              { title: 'Severity and Status', href: '/docs/error-feed/concepts/severity-and-status' },
            ]
          },
          {
            title: 'Features',
            items: [
              { title: 'The Feed', href: '/docs/error-feed/features/the-feed' },
              { title: 'Issue Overview', href: '/docs/error-feed/features/issue-overview' },
              { title: 'Traces', href: '/docs/error-feed/features/traces' },
              { title: 'State Graph', href: '/docs/error-feed/features/state-graph' },
              { title: 'Trends', href: '/docs/error-feed/features/trends' },
              { title: 'Metadata Panel', href: '/docs/error-feed/features/metadata-panel' },
              { title: 'Triage Workflow', href: '/docs/error-feed/features/triage-workflow' },
              { title: 'Deep Analysis', href: '/docs/error-feed/features/deep-analysis' },
              { title: 'Linear Integration', href: '/docs/error-feed/features/linear-integration' },
              { title: 'Sampling', href: '/docs/error-feed/features/sampling' },
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
              { title: 'Eval types', href: '/docs/evaluation/concepts/eval-types' },
              { title: 'Eval templates & versions', href: '/docs/evaluation/concepts/eval-templates' },
              { title: 'Evaluator models', href: '/docs/evaluation/concepts/evaluator-models' },
              { title: 'Error localization', href: '/docs/evaluation/concepts/error-localization' },
              { title: 'Guardrails', href: '/docs/evaluation/concepts/guardrails' },
              { title: 'Composite evals', href: '/docs/evaluation/concepts/composite-evals' },
              { title: 'Feedback', href: '/docs/evaluation/concepts/feedback' },
              { title: 'Ground truth', href: '/docs/evaluation/concepts/ground-truth' },
            ]
          },
          {
            title: 'Guides',
            items: [
              { title: 'Running Evaluations', href: '/docs/evaluation/guides/running-evaluations' },
              {
                title: 'Explore playground',
                items: [
                  { title: 'The Evaluations page', href: '/docs/evaluation/guides/explore-playground' },
                  { title: 'Test an eval', href: '/docs/evaluation/guides/explore-playground/test-an-eval' },
                  { title: 'Usage & analytics', href: '/docs/evaluation/guides/explore-playground/usage-analytics' },
                ]
              },
              { title: 'Create a custom eval', href: '/docs/evaluation/guides/custom-evals' },
              { title: 'Build a composite evals', href: '/docs/evaluation/guides/composite-evals' },
              { title: 'Set up guardrails', href: '/docs/evaluation/guides/guardrails' },
              { title: 'Add ground truth', href: '/docs/evaluation/guides/ground-truth' },
              { title: 'Collect feedback', href: '/docs/evaluation/guides/collect-feedback' },
              { title: 'Use custom models', href: '/docs/evaluation/guides/custom-models' },
              { title: 'Evaluate in CI/CD', href: '/docs/evaluation/guides/cicd' },
              { title: 'Advanced usage', href: '/docs/evaluation/guides/advanced-usage' },
            ]
          },
          {
            title: 'References',
            items: [
              {
                title: 'Built-in evals',
                items: [
                  { title: 'Overview', href: '/docs/evaluation/builtin' },
                  {
                    title: 'RAG & retrieval',
                    items: [
                      { title: 'Context Adherence', href: '/docs/evaluation/builtin/context-adherence' },
                      { title: 'Context Relevance', href: '/docs/evaluation/builtin/context-relevance' },
                      { title: 'Completeness', href: '/docs/evaluation/builtin/completeness' },
                      { title: 'Chunk Attribution', href: '/docs/evaluation/builtin/chunk-attribution' },
                      { title: 'Chunk Utilization', href: '/docs/evaluation/builtin/chunk-utilization' },
                      { title: 'Groundedness', href: '/docs/evaluation/builtin/groundedness' },
                      { title: 'Detect Hallucination', href: '/docs/evaluation/builtin/detect-hallucination' },
                      { title: 'Eval Ranking', href: '/docs/evaluation/builtin/eval-ranking' },
                      { title: 'Recall@K', href: '/docs/evaluation/builtin/recall-at-k' },
                      { title: 'Precision@K', href: '/docs/evaluation/builtin/precision-at-k' },
                      { title: 'NDCG@K', href: '/docs/evaluation/builtin/ndcg-at-k' },
                      { title: 'MRR', href: '/docs/evaluation/builtin/mrr' },
                      { title: 'Hit Rate', href: '/docs/evaluation/builtin/hit-rate' },
                      { title: 'Retrieval Metrics', href: '/docs/evaluation/builtin/retrieval-metrics' },
                    ]
                  },
                  {
                    title: 'Safety & compliance',
                    items: [
                      { title: 'PII Detection', href: '/docs/evaluation/builtin/pii' },
                      { title: 'Toxicity', href: '/docs/evaluation/builtin/toxicity' },
                      { title: 'Sexist', href: '/docs/evaluation/builtin/sexist' },
                      { title: 'Prompt Injection', href: '/docs/evaluation/builtin/prompt-injection' },
                      { title: 'Data Privacy Compliance', href: '/docs/evaluation/builtin/data-privacy' },
                      { title: 'Cultural Sensitivity', href: '/docs/evaluation/builtin/cultural-sensitivity' },
                      { title: 'Bias Detection', href: '/docs/evaluation/builtin/bias-detection' },
                      { title: 'No Racial Bias', href: '/docs/evaluation/builtin/no-racial-bias' },
                      { title: 'No Gender Bias', href: '/docs/evaluation/builtin/no-gender-bias' },
                      { title: 'No Age Bias', href: '/docs/evaluation/builtin/no-age-bias' },
                      { title: 'Answer Refusal', href: '/docs/evaluation/builtin/answer-refusal' },
                      { title: 'No Harmful Therapeutic Guidance', href: '/docs/evaluation/builtin/no-harmful-therapeutic-guidance' },
                      { title: 'Clinically Inappropriate Tone', href: '/docs/evaluation/builtin/clinically-inappropriate-tone' },
                      { title: 'Is Harmful Advice', href: '/docs/evaluation/builtin/is-harmful-advice' },
                    ]
                  },
                  {
                    title: 'Conversation & agents',
                    items: [
                      { title: 'Conversation Coherence', href: '/docs/evaluation/builtin/conversation-coherence' },
                      { title: 'Conversation Resolution', href: '/docs/evaluation/builtin/conversation-resolution' },
                      { title: 'Evaluate Function Calling', href: '/docs/evaluation/builtin/llm-function-calling' },
                      { title: 'Task Completion', href: '/docs/evaluation/builtin/task-completion' },
                      { title: 'Customer Agent: Loop Detection', href: '/docs/evaluation/builtin/customer-agent-loop-detection' },
                      { title: 'Customer Agent: Context Retention', href: '/docs/evaluation/builtin/customer-agent-context-retention' },
                      { title: 'Customer Agent: Query Handling', href: '/docs/evaluation/builtin/customer-agent-query-handling' },
                      { title: 'Customer Agent: Termination Handling', href: '/docs/evaluation/builtin/customer-agent-termination-handling' },
                      { title: 'Customer Agent: Interruption Handling', href: '/docs/evaluation/builtin/customer-agent-interruption-handling' },
                      { title: 'Customer Agent: Conversation Quality', href: '/docs/evaluation/builtin/customer-agent-conversation-quality' },
                      { title: 'Customer Agent: Objection Handling', href: '/docs/evaluation/builtin/customer-agent-objection-handling' },
                      { title: 'Customer Agent: Language Handling', href: '/docs/evaluation/builtin/customer-agent-language-handling' },
                      { title: 'Customer Agent: Human Escalation', href: '/docs/evaluation/builtin/customer-agent-human-escalation' },
                      { title: 'Customer Agent: Clarification Seeking', href: '/docs/evaluation/builtin/customer-agent-clarification-seeking' },
                      { title: 'Customer Agent: Prompt Conformance', href: '/docs/evaluation/builtin/customer-agent-prompt-conformance' },
                      { title: 'Customer Agent: Task Completion', href: '/docs/evaluation/builtin/customer-agent-task-completion' },
                      { title: 'Conversation Hallucination', href: '/docs/evaluation/builtin/conversation-hallucination' },
                      { title: 'Tool Call Accuracy', href: '/docs/evaluation/builtin/tool-call-accuracy' },
                      { title: 'Trajectory Match', href: '/docs/evaluation/builtin/trajectory-match' },
                      { title: 'Step Count', href: '/docs/evaluation/builtin/step-count' },
                    ]
                  },
                  {
                    title: 'Output quality & format',
                    items: [
                      { title: 'Tone', href: '/docs/evaluation/builtin/tone' },
                      { title: 'Instruction Adherence', href: '/docs/evaluation/builtin/instruction-adherence' },
                      { title: 'Summary Quality', href: '/docs/evaluation/builtin/summary-quality' },
                      { title: 'Translation Accuracy', href: '/docs/evaluation/builtin/translation-accuracy' },
                      { title: 'No LLM Reference', href: '/docs/evaluation/builtin/no-llm-reference' },
                      { title: 'No Apologies', href: '/docs/evaluation/builtin/no-apologies' },
                      { title: 'Is Polite', href: '/docs/evaluation/builtin/is-polite' },
                      { title: 'Is Concise', href: '/docs/evaluation/builtin/is-concise' },
                      { title: 'Is Helpful', href: '/docs/evaluation/builtin/is-helpful' },
                      { title: 'Is Good Summary', href: '/docs/evaluation/builtin/is-good-summary' },
                      { title: 'Is Informal Tone', href: '/docs/evaluation/builtin/is-informal-tone' },
                      { title: 'Contains Code', href: '/docs/evaluation/builtin/is-code' },
                      { title: 'Text to SQL', href: '/docs/evaluation/builtin/text-to-sql' },
                      { title: 'Is JSON', href: '/docs/evaluation/builtin/is-json' },
                      { title: 'One Line', href: '/docs/evaluation/builtin/contain-evals' },
                      { title: 'Contains Valid Link', href: '/docs/evaluation/builtin/contains-valid-link' },
                      { title: 'Is Email', href: '/docs/evaluation/builtin/is-email' },
                      { title: 'No Invalid Links', href: '/docs/evaluation/builtin/no-invalid-links' },
                      { title: 'Is Refusal', href: '/docs/evaluation/builtin/is-refusal' },
                      { title: 'Code & Output Validation Checks', href: '/docs/evaluation/builtin/code-output-validation-checks' },
                    ]
                  },
                  {
                    title: 'Reference & similarity',
                    items: [
                      { title: 'Fuzzy Match', href: '/docs/evaluation/builtin/fuzzy-match' },
                      { title: 'Ground Truth Match', href: '/docs/evaluation/builtin/ground-truth-match' },
                      { title: 'BLEU Score', href: '/docs/evaluation/builtin/bleu' },
                      { title: 'ROUGE Score', href: '/docs/evaluation/builtin/rouge' },
                      { title: 'Levenshtein Similarity', href: '/docs/evaluation/builtin/lavenshtein-similarity' },
                      { title: 'Numeric Similarity', href: '/docs/evaluation/builtin/numeric-similarity' },
                      { title: 'Embedding Similarity', href: '/docs/evaluation/builtin/embedding-similarity' },
                      { title: 'Semantic List Contains', href: '/docs/evaluation/builtin/semantic-list-contains' },
                      { title: 'Similarity & Image-Quality Metrics', href: '/docs/evaluation/builtin/similarity-image-quality-metrics' },
                    ]
                  },
                  {
                    title: 'Audio & voice',
                    items: [
                      { title: 'Audio Transcription (ASR/STT)', href: '/docs/evaluation/builtin/audio-transcription' },
                      { title: 'Audio Quality', href: '/docs/evaluation/builtin/audio-quality' },
                      { title: 'TTS Accuracy', href: '/docs/evaluation/builtin/tts-accuracy' },
                      { title: 'Audio & ASR Metrics', href: '/docs/evaluation/builtin/audio-asr-metrics' },
                      { title: 'Dead Air Detection', href: '/docs/evaluation/builtin/dead-air-detection' },
                    ]
                  },
                  {
                    title: 'Image & document',
                    items: [
                      { title: 'Caption Hallucination', href: '/docs/evaluation/builtin/caption-hallucination' },
                      { title: 'Synthetic Image Evaluator', href: '/docs/evaluation/builtin/synthetic-image-evaluator' },
                      { title: 'OCR Evaluation', href: '/docs/evaluation/builtin/ocr-evaluation' },
                      { title: 'FID Score', href: '/docs/evaluation/builtin/fid-score' },
                      { title: 'CLIP Score', href: '/docs/evaluation/builtin/clip-score' },
                      { title: 'Image Instruction Adherence', href: '/docs/evaluation/builtin/image-instruction-adherence' },
                    ]
                  },
                  {
                    title: 'Statistical & NLP metrics',
                    items: [
                      { title: 'Statistical & Classification Metrics', href: '/docs/evaluation/builtin/statistical-classification-metrics' },
                      { title: 'NLP & Text Metrics', href: '/docs/evaluation/builtin/nlp-text-metrics' },
                    ]
                  },
                ]
              },
              { title: 'Output types & scoring', href: '/docs/evaluation/reference/output-types' },
              { title: 'SDK & API', href: '/docs/evaluation/reference/sdk-api' },
            ]
          },
          {
            title: 'Troubleshooting',
            items: [
              { title: 'Evaluation FAQ & fixes', href: '/docs/evaluation/troubleshooting' },
            ]
          },
        ]
      },
      {
        group: 'Falcon AI',
        icon: 'rocket',
        items: [
          { title: 'Overview', href: '/docs/falcon-ai' },
          {
            title: 'Features',
            items: [
              { title: 'Using Falcon AI', href: '/docs/falcon-ai/features/chat' },
              { title: 'Skill Builder', href: '/docs/falcon-ai/features/skills' },
              { title: 'MCP Connectors', href: '/docs/falcon-ai/features/mcp-connectors' },
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
          { title: 'Quickstart', href: '/docs/observe/quickstart' },
          {
            title: 'Concepts',
            items: [
              { title: 'Spans', href: '/docs/observe/concepts/spans' },
              { title: 'Traces', href: '/docs/observe/concepts/traces' },
              { title: 'Sessions', href: '/docs/observe/concepts/sessions' },
              { title: 'Users', href: '/docs/observe/concepts/users' },
              { title: 'Voice observability', href: '/docs/observe/concepts/voice-observability' },
              { title: 'Observability model', href: '/docs/observe/concepts/observability-model' },
            ]
          },
          {
            title: 'Guides',
            items: [
              {
                title: 'Explore dashboard',
                items: [
                  { title: 'Overview', href: '/docs/observe/guides/explore-dashboard' },
                  { title: 'Filters', href: '/docs/observe/guides/explore-dashboard/filters' },
                  { title: 'Views', href: '/docs/observe/guides/explore-dashboard/views' },
                  { title: 'Display options', href: '/docs/observe/guides/explore-dashboard/display-options' },
                ]
              },
              { title: 'Setup alerts', href: '/docs/observe/guides/setup-alerts' },
              { title: 'Setup evals', href: '/docs/observe/guides/setup-evals' },
            ]
          },
          {
            title: 'Reference',
            items: [
              { title: 'Filters', href: '/docs/observe/reference/filters' },
              { title: 'traceAI', href: '/docs/observe/concepts/traceai' },
            ]
          },
          {
            title: 'Troubleshooting',
            items: [
              { title: 'No traces appear', href: '/docs/observe/troubleshooting/no-traces-appearing' },
              { title: 'Missing spans or fields', href: '/docs/observe/troubleshooting/missing-attributes' },
              { title: 'Dashboard numbers look wrong', href: '/docs/observe/troubleshooting/dashboard-numbers-look-wrong' },
              { title: 'Alerts not firing', href: '/docs/observe/troubleshooting/alerts-did-not-fire' },
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
        ]
      },
      {
        group: 'Simulation',
        icon: 'play',
        items: [
          {
            title: 'Simulation',
            items: [
              { title: 'Overview', href: '/docs/simulation' },
            ]
          },
          {
            title: 'Concepts',
            items: [
              { title: 'Understanding Simulation', href: '/docs/simulation/concepts/understanding-simulation' },
              { title: 'Agent definitions & versions', href: '/docs/simulation/concepts/agent-definitions' },
              { title: 'Scenarios', href: '/docs/simulation/concepts/scenarios' },
              { title: 'Personas', href: '/docs/simulation/concepts/personas' },
              { title: 'Runs & results', href: '/docs/simulation/concepts/runs-and-results' },
              { title: 'Replay', href: '/docs/simulation/concepts/replay' },
              { title: 'Optimization', href: '/docs/simulation/concepts/optimization' },
            ]
          },
          {
            title: 'Guides',
            items: [
              { title: 'Connect your agent', href: '/docs/simulation/guides/connect-your-agent' },
              { title: 'Create scenarios', href: '/docs/simulation/guides/create-scenarios' },
              { title: 'Explore scenarios', href: '/docs/simulation/guides/explore-scenarios' },
              { title: 'Create personas', href: '/docs/simulation/guides/create-personas' },
              { title: 'Run a voice simulation', href: '/docs/simulation/guides/run-voice-simulation' },
              { title: 'Run a chat simulation', href: '/docs/simulation/guides/run-chat-simulation' },
              { title: 'Simulate a prompt', href: '/docs/simulation/guides/prompt-simulation' },
              { title: 'Edit evals in a simulation', href: '/docs/simulation/guides/edit-evals' },
              { title: 'Replay chat sessions', href: '/docs/simulation/guides/replay-chat' },
              { title: 'Replay voice calls', href: '/docs/simulation/guides/replay-voice' },
              { title: 'Evaluate tool calls', href: '/docs/simulation/guides/evaluate-tool-calls' },
              {
                title: 'Explore results',
                items: [
                  { title: 'Overview', href: '/docs/simulation/guides/explore-results' },
                  { title: 'Calls & transcripts', href: '/docs/simulation/guides/explore-results/calls-and-transcripts' },
                  { title: 'Analytics & metrics', href: '/docs/simulation/guides/explore-results/analytics' },
                ]
              },
              { title: 'Fix My Agent', href: '/docs/simulation/guides/fix-my-agent' },
              { title: 'Running optimizations', href: '/docs/simulation/guides/running-optimizations' },
              { title: 'Optimization runs', href: '/docs/simulation/guides/optimization-runs' },
            ]
          },
          {
            title: 'References',
            items: [
              { title: 'Persona settings', href: '/docs/simulation/reference/persona-settings' },
              { title: 'Voice providers', href: '/docs/simulation/reference/voice-providers' },
              { title: 'Call metrics', href: '/docs/simulation/reference/call-metrics' },
              { title: 'SDK & API', href: '/docs/simulation/reference/sdk-api' },
            ]
          },
          {
            title: 'Troubleshooting',
            items: [
              { title: 'Simulation FAQ & fixes', href: '/docs/simulation/troubleshooting' },
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
            ]
          },
          {
            title: 'Use Cases',
            icon: 'flask',
            items: [
              { title: 'Test and Fix Your Chat Agent with Simulated Conversations', href: '/docs/cookbook/use-cases/end-to-end-agent-testing' },
              { title: 'Monitor LLM Quality in Production and Catch Regressions', href: '/docs/cookbook/use-cases/production-quality-monitoring' },
            ]
          },
          {
            title: 'Falcon AI',
            icon: 'rocket',
            items: [
              { title: 'End-to-End with Falcon AI: Trace → Debug → Evaluate → Dataset → Fix in One Workflow', href: '/docs/cookbook/falcon-ai/end-to-end' },
              { title: 'Context-Aware Trace Debugging with Falcon AI', href: '/docs/cookbook/falcon-ai/context-aware-debugging' },
              { title: 'Building Golden Datasets from Production Traces with Falcon AI', href: '/docs/cookbook/falcon-ai/eval-datasets-from-traces' },
            ]
          },
          {
            title: 'Agent Command Center',
            icon: 'server',
            items: [
              { title: 'Cut LLM Costs 80% With Semantic Caching', href: '/docs/cookbook/command-center/semantic-caching' },
            ]
          },
          {
            title: 'MCP Server',
            icon: 'plug',
            items: [
              { title: 'Debug LLM Traces From Your IDE Using Natural Language MCP Queries', href: '/docs/cookbook/mcp/debug-traces-from-ide' },
            ]
          },
          {
            title: 'Evaluation',
            icon: 'check-double',
            items: [
              { title: "Building an Eval Correction Loop: Teaching Your Evaluator What 'Good' Means for Your Domain", href: '/docs/cookbook/evaluation/eval-correction-loop' },
            ]
          },
          {
            title: 'Self-Hosting',
            icon: 'box',
            items: [
              { title: 'Deploy the Full Open-Source AI Stack Locally With Docker Compose in 5 Minutes', href: '/docs/cookbook/self-hosting/docker-compose-quickstart' },
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
              { title: 'Observing a LangGraph agent and obtaining insights', href: '/docs/cookbook/observe-langgraph-agent-and-obtain-insights' },
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
        group: 'SDK Overview',
        icon: 'code',
        items: [
          { title: 'SDK Overview', href: '/docs/sdk' },
          {
            title: 'List of SDKs',
            items: [
              { title: 'Evaluation', href: '/docs/sdk/list/evaluation' },
              { title: 'TraceAI', href: '/docs/sdk/list/traceai' },
              { title: 'Core SDKs', href: '/docs/sdk/list/core' },
            ]
          },
        ]
      },
      {
        group: 'Evaluation',
        icon: 'chart',
        items: [
          { title: 'Overview', href: '/docs/sdk/evals' },
          { title: 'Running Evaluations', href: '/docs/sdk/evals/evaluate' },
          { title: 'AutoEval', href: '/docs/sdk/evals/autoeval' },
          { title: 'LLM-as-Judge', href: '/docs/sdk/evals/llm-judge' },
          { title: 'Guardrails', href: '/docs/sdk/evals/guardrails-module' },
          { title: 'Local & Hybrid', href: '/docs/sdk/evals/local' },
          { title: 'Distributed Evaluator', href: '/docs/sdk/evals/distributed' },
          { title: 'Streaming', href: '/docs/sdk/evals/streaming' },
          { title: 'Cloud Evals', href: '/docs/sdk/evals/cloud-evals' },
          { title: 'Feedback Loops', href: '/docs/sdk/evals/feedback' },
          { title: 'Code Security', href: '/docs/sdk/evals/code-security' },
          { title: 'OpenTelemetry', href: '/docs/sdk/evals/otel' },
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
        ]
      },
      {
        group: 'traceAI',
        icon: 'eye',
        items: [
          { title: 'Overview', href: '/docs/sdk/tracing' },
          {
            title: 'How-to guides',
            items: [
              { title: 'Set up tracing', href: '/docs/sdk/tracing/set-up-tracing' },
              { title: 'Instrument with helpers', href: '/docs/sdk/tracing/instrument-with-traceai-helpers' },
              { title: 'Set session & user IDs', href: '/docs/sdk/tracing/set-session-user-id' },
              { title: 'Attributes, metadata & tags', href: '/docs/sdk/tracing/add-attributes-metadata-tags' },
              { title: 'Log prompt templates', href: '/docs/sdk/tracing/log-prompt-templates' },
              { title: 'Events, exceptions & status', href: '/docs/sdk/tracing/add-events-exceptions-status' },
              { title: 'Mask attributes', href: '/docs/sdk/tracing/mask-span-attributes' },
              { title: 'Create tool spans', href: '/docs/sdk/tracing/create-tool-spans' },
              { title: 'Get span context', href: '/docs/sdk/tracing/get-current-span-context' },
              { title: 'In-line evals', href: '/docs/sdk/tracing/in-line-evals' },
              { title: 'Annotate via API', href: '/docs/sdk/tracing/annotating-using-api' },
              { title: 'Advanced examples', href: '/docs/sdk/tracing/advanced-tracing-examples' },
              { title: 'Langfuse integration', href: '/docs/sdk/tracing/langfuse-integration' },
            ]
          },
          {
            title: 'Reference',
            items: [
              { title: 'register()', href: '/docs/sdk/tracing/register' },
              { title: 'FITracer & custom spans', href: '/docs/sdk/tracing/fitracer' },
              { title: 'Context helpers', href: '/docs/sdk/tracing/context-helpers' },
              { title: 'TraceConfig', href: '/docs/sdk/tracing/trace-config' },
              { title: 'EvalTags', href: '/docs/sdk/tracing/eval-tags' },
              { title: 'Instrumentors', href: '/docs/sdk/tracing/instrumentors' },
              { title: 'Environment variables', href: '/docs/sdk/tracing/environment-variables' },
              { title: 'Semantic conventions', href: '/docs/sdk/tracing/semantic-conventions' },
            ]
          },
        ]
      },
      {
        group: 'Simulation',
        icon: 'play',
        items: [
          { title: 'Overview', href: '/docs/sdk/simulate' },
        ]
      },
      {
        group: 'Datasets',
        icon: 'table',
        items: [
          { title: 'Overview', href: '/docs/sdk/datasets' },
        ]
      },
      {
        group: 'Prompt Optimization',
        icon: 'gauge',
        items: [
          { title: 'Overview', href: '/docs/sdk/optimization' },
        ]
      },
      {
        group: 'Annotation Queues',
        icon: 'pen',
        items: [
          { title: 'Overview', href: '/docs/sdk/annotation-queues' },
          {
            title: 'Concepts',
            items: [
              { title: 'Labels', href: '/docs/sdk/annotation-queues/labels' },
              { title: 'Queue management', href: '/docs/sdk/annotation-queues/queues' },
              { title: 'Queue lifecycle', href: '/docs/sdk/annotation-queues/lifecycle' },
              { title: 'Queue items', href: '/docs/sdk/annotation-queues/items' },
              { title: 'Annotations', href: '/docs/sdk/annotation-queues/annotations' },
              { title: 'Scores', href: '/docs/sdk/annotation-queues/scores' },
              { title: 'Progress & analytics', href: '/docs/sdk/annotation-queues/analytics' },
              { title: 'Export', href: '/docs/sdk/annotation-queues/export' },
              { title: 'Data models', href: '/docs/sdk/annotation-queues/data-models' },
            ]
          },
        ]
      },
      {
        group: 'Knowledge Base',
        icon: 'brain',
        items: [
          { title: 'Overview', href: '/docs/sdk/knowledgebase' },
        ]
      },
      {
        group: 'Protect',
        icon: 'shield',
        items: [
          { title: 'Overview', href: '/docs/sdk/protect' },
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
            title: 'Eval Tasks',
            items: [
              { title: 'List Eval Tasks', href: '/docs/api/eval-tasks/list-eval-tasks-filtered' },
              { title: 'Create Eval Task', href: '/docs/api/eval-tasks/create-eval-task' },
              { title: 'Get Eval Task', href: '/docs/api/eval-tasks/get-eval-task' },
              { title: 'Update Eval Task', href: '/docs/api/eval-tasks/update-eval-task' },
              { title: 'Delete Eval Task', href: '/docs/api/eval-tasks/delete-eval-task' },
              { title: 'Bulk Delete Eval Tasks', href: '/docs/api/eval-tasks/bulk-delete-eval-tasks' },
              { title: 'Pause Eval Task', href: '/docs/api/eval-tasks/pause-eval-task' },
              { title: 'Unpause Eval Task', href: '/docs/api/eval-tasks/unpause-eval-task' },
              { title: 'Eval Task Aggregations', href: '/docs/api/eval-tasks/eval-task-aggregations' },
            ]
          },
          {
            title: 'Custom Eval Configs',
            items: [
              { title: 'List Custom Eval Configs', href: '/docs/api/custom-eval-configs/list-configs-filtered' },
              { title: 'Create Custom Eval Config', href: '/docs/api/custom-eval-configs/create-custom-eval-config' },
              { title: 'Get Custom Eval Config', href: '/docs/api/custom-eval-configs/get-custom-eval-config' },
              { title: 'Update Custom Eval Config', href: '/docs/api/custom-eval-configs/update-custom-eval-config' },
              { title: 'Delete Custom Eval Config', href: '/docs/api/custom-eval-configs/delete-custom-eval-config' },
              { title: 'Check Config Exists', href: '/docs/api/custom-eval-configs/check-config-exists' },
            ]
          },
          {
            title: 'Dataset Evals',
            items: [
              { title: 'Get Eval Template Names', href: '/docs/api/dataset-evals/get-eval-template-names' },
              { title: 'Create Custom Eval Template', href: '/docs/api/dataset-evals/create-custom-eval-template' },
              { title: 'List Dataset Evals', href: '/docs/api/dataset-evals/list-dataset-evals' },
              { title: 'Get Eval Structure', href: '/docs/api/dataset-evals/get-eval-structure' },
              { title: 'Add Dataset Eval', href: '/docs/api/dataset-evals/add-dataset-eval' },
              { title: 'Start Evals Process', href: '/docs/api/dataset-evals/start-evals-process' },
              { title: 'Delete Dataset Eval', href: '/docs/api/dataset-evals/delete-dataset-eval' },
              { title: 'Edit and Run Eval', href: '/docs/api/dataset-evals/edit-and-run-eval' },
            ]
          },
          {
            title: 'Scenarios',
            items: [
              { title: 'List Scenarios', href: '/docs/api/scenarios/listscenarios' },
              { title: 'Get Scenario Details', href: '/docs/api/scenarios/getscenario' },
              { title: 'Create Scenario', href: '/docs/api/scenarios/createscenario' },
              { title: 'Edit Scenario', href: '/docs/api/scenarios/editscenario' },
              { title: 'Delete Scenario', href: '/docs/api/scenarios/deletescenario' },
              { title: 'Add Rows with AI', href: '/docs/api/scenarios/addscenariorowswithai' },
              { title: 'Add Columns', href: '/docs/api/scenarios/addcolumns' },
            ]
          },
          {
            title: 'Personas',
            items: [
              { title: 'List Personas', href: '/docs/api/personas/listpersonas' },
              { title: 'Create Persona', href: '/docs/api/personas/createpersona' },
              { title: 'Update Persona', href: '/docs/api/personas/updatepersona' },
              { title: 'Delete Persona', href: '/docs/api/personas/deletepersona' },
              { title: 'Duplicate Persona', href: '/docs/api/personas/duplicatepersona' },
            ]
          },
          {
            title: 'Agent Definitions',
            items: [
              { title: 'List Agent Definitions', href: '/docs/api/agent-definitions/listagentdefinitions' },
              { title: 'Create Agent Definition', href: '/docs/api/agent-definitions/createagentdefinition' },
              { title: 'Get Agent Definition', href: '/docs/api/agent-definitions/getagentdefinition' },
              { title: 'Delete Agent Definitions', href: '/docs/api/agent-definitions/deleteagentdefinitions' },
              { title: 'Fetch from Provider', href: '/docs/api/agent-definitions/fetchassistantfromprovider' },
            ]
          },
          {
            title: 'Agent Versions',
            items: [
              { title: 'List Agent Versions', href: '/docs/api/agent-versions/listagentversions' },
              { title: 'Create Agent Version', href: '/docs/api/agent-versions/createagentversion' },
              { title: 'Get Agent Version', href: '/docs/api/agent-versions/getagentversion' },
              { title: 'Get Version Call Executions', href: '/docs/api/agent-versions/getversioncallexecutions' },
              { title: 'Get Version Eval Summary', href: '/docs/api/agent-versions/getversionevalsummary' },
            ]
          },
          {
            title: 'Run Tests',
            items: [
              { title: 'List Test Runs', href: '/docs/api/run-tests/listruntests' },
              { title: 'Create Run Test', href: '/docs/api/run-tests/createruntest' },
              { title: 'Get Test Run Details', href: '/docs/api/run-tests/getruntestdetails' },
              { title: 'Delete Test Run', href: '/docs/api/run-tests/deleteruntest' },
              { title: 'Execute Run Test', href: '/docs/api/run-tests/executeruntest' },
              { title: 'Get Test Executions', href: '/docs/api/run-tests/gettestexecutions' },
              { title: 'Get Test Scenarios', href: '/docs/api/run-tests/gettestscenarios' },
              { title: 'Get Eval Summary', href: '/docs/api/run-tests/getevalsummary' },
              { title: 'Compare Eval Summaries', href: '/docs/api/run-tests/compareevalsummaries' },
              { title: 'Add Eval Configs', href: '/docs/api/run-tests/addevalconfigs' },
              { title: 'Update Eval Config', href: '/docs/api/run-tests/updateevalconfig' },
              { title: 'Delete Eval Config', href: '/docs/api/run-tests/deleteevalconfig' },
              { title: 'Run New Evals', href: '/docs/api/run-tests/runnewevalsontestexecution' },
              { title: 'Rerun Test Executions', href: '/docs/api/run-tests/reruntestexecutions' },
              { title: 'Delete Test Executions', href: '/docs/api/run-tests/deletetestexecutions' },
            ]
          },
          {
            title: 'Test Executions',
            items: [
              { title: 'Get Execution Details', href: '/docs/api/test-executions/gettestexecutiondetails' },
              { title: 'Get Execution KPIs', href: '/docs/api/test-executions/getkpis' },
              { title: 'Get Performance Summary', href: '/docs/api/test-executions/getperformancesummary' },
              { title: 'Cancel Execution', href: '/docs/api/test-executions/cancelexecution' },
              { title: 'Rerun Calls', href: '/docs/api/test-executions/reruncalls' },
              { title: 'Get Call Details', href: '/docs/api/test-executions/getcallexecutiondetails' },
            ]
          },
          {
            title: 'Simulation Analytics',
            items: [
              { title: 'Get Simulation Metrics', href: '/docs/api/simulation-analytics/metrics' },
              { title: 'Get Simulation Runs', href: '/docs/api/simulation-analytics/runs' },
              { title: 'Get Simulation Analytics', href: '/docs/api/simulation-analytics/analytics' },
            ]
          },
          {
            title: 'Datasets',
            items: [
              { title: 'List Datasets', href: '/docs/api/datasets/list-datasets' },
              { title: 'Create Dataset', href: '/docs/api/datasets/create-dataset' },
              { title: 'Create Empty Dataset', href: '/docs/api/datasets/create-empty-dataset' },
              { title: 'Upload Dataset from File', href: '/docs/api/datasets/upload-dataset' },
              { title: 'Create from HuggingFace', href: '/docs/api/datasets/create-dataset-from-huggingface' },
              { title: 'Clone Dataset', href: '/docs/api/datasets/clone-dataset' },
              { title: 'Duplicate Dataset', href: '/docs/api/datasets/duplicate-dataset' },
              { title: 'Add as New Dataset', href: '/docs/api/datasets/add-as-new' },
              { title: 'Update Dataset', href: '/docs/api/datasets/update-dataset' },
              { title: 'Merge Dataset', href: '/docs/api/datasets/merge-dataset' },
              { title: 'Delete Dataset', href: '/docs/api/datasets/delete-dataset' },
              { title: 'Add Rows from File', href: '/docs/api/datasets/add-rows-from-file' },
              { title: 'Add Empty Rows', href: '/docs/api/datasets/add-empty-rows' },
              { title: 'Add Rows from Existing', href: '/docs/api/datasets/add-rows-from-existing' },
              { title: 'Add Rows from HuggingFace', href: '/docs/api/datasets/add-rows-from-huggingface' },
              { title: 'Duplicate Rows', href: '/docs/api/datasets/duplicate-rows' },
              { title: 'Delete Rows', href: '/docs/api/datasets/delete-rows' },
              { title: 'Update Cell Value', href: '/docs/api/datasets/update-cell-value' },
            ]
          },
          {
            title: 'Dataset Columns',
            items: [
              { title: 'Get Column Details', href: '/docs/api/datasets/columns/get-column-details' },
              { title: 'Get Column Config', href: '/docs/api/datasets/columns/get-column-config' },
              { title: 'Add Static Column', href: '/docs/api/datasets/columns/add-static-column' },
              { title: 'Add Multiple Static Columns', href: '/docs/api/datasets/columns/add-multiple-static-columns' },
              { title: 'Add Columns', href: '/docs/api/datasets/columns/add-columns' },
              { title: 'Update Column Name', href: '/docs/api/datasets/columns/update-column-name' },
              { title: 'Update Column Type', href: '/docs/api/datasets/columns/update-column-type' },
              { title: 'Delete Column', href: '/docs/api/datasets/columns/delete-column' },
            ]
          },
          {
            title: 'Dataset Run Prompt',
            items: [
              { title: 'Add Run Prompt Column', href: '/docs/api/datasets/run-prompt/add-run-prompt-column' },
              { title: 'Edit Run Prompt Column', href: '/docs/api/datasets/run-prompt/edit-run-prompt-column' },
              { title: 'Get Run Prompt Config', href: '/docs/api/datasets/run-prompt/retrieve-run-prompt-column-config' },
              { title: 'Get Run Prompt Options', href: '/docs/api/datasets/run-prompt/retrieve-run-prompt-options' },
              { title: 'Get Model Voices', href: '/docs/api/datasets/run-prompt/get-model-voices' },
              { title: 'TTS Voices', href: '/docs/api/datasets/run-prompt/tts-voices' },
              { title: 'Get Column Values', href: '/docs/api/datasets/run-prompt/get-column-values' },
            ]
          },
          {
            title: 'Dataset Analytics',
            items: [
              { title: 'Run Prompt Stats', href: '/docs/api/datasets/analytics/run-prompt-stats' },
              { title: 'Eval Stats', href: '/docs/api/datasets/analytics/eval-stats' },
              { title: 'Annotation Summary', href: '/docs/api/datasets/analytics/annotation-summary' },
              { title: 'Explanation Summary', href: '/docs/api/datasets/analytics/explanation-summary' },
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
