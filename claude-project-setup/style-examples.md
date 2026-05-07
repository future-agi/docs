# Style Examples

Three pages that best represent the documentation's ideal style: clear structure, terse developer tone, useful tables and code examples, no marketing fluff.

---

## Example 1: `/docs/sdk/` — SDKs Overview

**Why it's good:** The language-support table up front answers "what can I do in my language?" in 10 seconds. TLDR block handles scanners. Dependency graph using ASCII art is precise and eliminates "do I need to install X separately?" confusion. Tab components let readers self-select their language without reading irrelevant content. Zero marketing language — it's entirely functional.

```mdx
---
title: "SDKs"
description: "Evaluate LLM outputs, trace AI calls, optimize prompts, and test voice agents. Python, TypeScript, Java, and C# supported."
---

<TLDR>
- **Python:** evals, tracing, datasets, prompts, optimization, simulation
- **TypeScript:** evals, tracing, datasets, prompts
- **Java / C#:** tracing
- `pip install ai-evaluation` or `npm install @future-agi/ai-evaluation` to get started
</TLDR>

Future AGI is a set of packages that evaluate LLM outputs, trace calls across your stack, optimize prompts, and load-test voice agents. Install what you need, skip what you don't.

## Language Support

| Module | Python | TypeScript | Java | C# |
|--------|--------|------------|------|----|
| Evaluations | Full | Full | — | — |
| Tracing | Full (45+) | Full (40+) | Full (25+) | Full |
| Datasets | Full | Full | — | — |
| Prompts | Full | Full | — | — |
| Prompt Optimization | Full | — | — | — |
| Simulation | Full | — | — | — |

## Quickstart

<Tabs>
  <Tab title="Python">
    ```bash
    pip install ai-evaluation
    ```

    Requires Python 3.10+. This also installs `futureagi` ([datasets](/docs/sdk/datasets), [prompts](/docs/sdk/datasets), [knowledge bases](/docs/sdk/knowledgebase)) automatically.

    ```bash
    export FI_API_KEY="your-api-key"
    export FI_SECRET_KEY="your-secret-key"
    ```

    ```python
    from fi.evals import evaluate

    # Local metric — no API key needed
    result = evaluate("contains", output="Hello world", keyword="Hello")
    print(result.score)    # 1.0
    print(result.passed)   # True

    # Cloud metric — needs FI_API_KEY and FI_SECRET_KEY
    result = evaluate("toxicity", output="Hello world", model="turing_flash")
    print(result.score)    # 1.0
    print(result.passed)   # True
    ```

    Want tracing too? Add the instrumentor for your provider:

    ```bash
    pip install fi-instrumentation-otel traceai-openai
    ```
  </Tab>
  <Tab title="TypeScript">
    ```bash
    npm install @future-agi/ai-evaluation
    ```

    ```bash
    export FI_API_KEY="your-api-key"
    export FI_SECRET_KEY="your-secret-key"
    ```

    ```typescript
    import { Evaluator, Tone } from "@future-agi/ai-evaluation";

    const evaluator = new Evaluator();

    const result = await evaluator.evaluate({
      evalTemplates: [new Tone()],
      inputs: [{
        query: "Write a professional email",
        response: "Dear Sir/Madam, I hope this message finds you well..."
      }],
      modelName: "turing_flash"
    });

    console.log(result);
    ```
  </Tab>
  <Tab title="Java">
    Java support covers tracing only. 25+ instrumentors including Spring AI and LangChain4j.

    ```xml
    <!-- Maven — add the JitPack repository -->
    <repository>
        <id>jitpack.io</id>
        <url>https://jitpack.io</url>
    </repository>

    <dependency>
        <groupId>com.github.future-agi.traceAI</groupId>
        <artifactId>traceai-java-openai</artifactId>
        <version>LATEST</version>
    </dependency>
    ```

    See the [Tracing docs](/docs/sdk/tracing) for setup instructions.
  </Tab>
  <Tab title="C#">
    C# support covers tracing only.

    ```bash
    dotnet add package fi-instrumentation-otel
    ```

    See the [Tracing docs](/docs/sdk/tracing) for setup instructions.
  </Tab>
</Tabs>

<AccordionGroup>
  <Accordion title="Getting an error? Check these common issues">
    **`ModuleNotFoundError: No module named 'fi'`** — The package is called `ai-evaluation`, not `future-agi` or `futureagi-sdk`:
    ```bash
    pip install ai-evaluation
    ```

    **`AuthenticationError`** — Both `FI_API_KEY` and `FI_SECRET_KEY` must be set. The API key alone is not enough.

    **`Python version error`** — `ai-evaluation` requires Python 3.10+. Check with `python --version`.
  </Accordion>
</AccordionGroup>

## Packages

### Python

Six packages, each installable independently:

| Package | Install | What it does | Python |
|---------|---------|--------------|--------|
| **futureagi** | `pip install futureagi` | Datasets, prompt versioning, knowledge bases | 3.9+ |
| **ai-evaluation** | `pip install ai-evaluation` | 76+ local metrics + 100+ cloud templates, guardrails, streaming eval | 3.10+ |
| **fi-instrumentation-otel** | `pip install fi-instrumentation-otel` | OpenTelemetry tracing for AI apps | 3.9+ |
| **traceai-\*** | `pip install traceai-openai` | Auto-instrumentation for 45+ frameworks | 3.9+ |
| **agent-opt** | `pip install agent-opt` | Prompt optimization (6 algorithms) | 3.10+ |
| **agent-simulate** | `pip install agent-simulate` | Simulate voice AI agents at scale | 3.10+ |

```
futureagi                    ← standalone base layer
  └── ai-evaluation          ← installs futureagi automatically
        └── agent-opt        ← installs ai-evaluation automatically

fi-instrumentation-otel      ← standalone tracing layer
  ├── traceai-*              ← each installs fi-instrumentation-otel
  └── agent-simulate         ← installs fi-instrumentation-otel
```

<Tip>
  You don't need to install dependencies manually. `pip install ai-evaluation` gives you `futureagi` too. `pip install traceai-openai` gives you `fi-instrumentation-otel` too.
</Tip>
```

---

## Example 2: `/docs/quickstart/setup-observability/` — Setup Observability

**Why it's good:** Steps component turns a multi-step setup into a linear, unambiguous workflow. Every step has a concrete, copy-pasteable code block in Python and TypeScript. Configuration parameters are documented inline after the code — no hunting. The final step tells you exactly what to look at in the dashboard, not just "you're done." Description is specific and keyword-rich.

```mdx
---
title: "Setup Observability"
description: "Set up Future AGI Observe for production monitoring. Configure auto-instrumented tracing for OpenAI, Anthropic, LangChain, and other LLM frameworks."
---

## About

**Observe** is Future AGI's observability product. It gives you full visibility into how your AI application behaves in production by capturing every LLM call, tool use, and agent decision as a trace. You can monitor performance, detect anomalies, track costs, and debug issues without changing your application logic.

Observe supports auto-instrumentation for OpenAI, Anthropic, LangChain, LlamaIndex, CrewAI and [30+ other frameworks](/docs/integrations). By the end of this guide, you'll have traces flowing into your Future AGI dashboard.

---

<Steps>
  <Step title="Install the SDK">
    Install the Future AGI instrumentation package and the OpenAI integration (used in this example).

    <CodeGroup titles={["Python", "JS/TS"]}>
    ```bash Python
    pip install fi-instrumentation traceAI-openai openai
    ```

    ```bash JS/TS
    npm install @traceai/fi-core @traceai/openai openai
    ```
    </CodeGroup>
  </Step>
  <Step title="Configure Your Environment">
    Set up your environment variables to connect to Future AGI. Get your API keys [here](https://app.futureagi.com/dashboard/keys).

    <CodeGroup titles={["Python", "JS/TS"]}>
    ```python Python
    import os
    os.environ["FI_API_KEY"] = "YOUR_API_KEY"
    os.environ["FI_SECRET_KEY"] = "YOUR_SECRET_KEY"
    os.environ["OPENAI_API_KEY"] = "YOUR_OPENAI_API_KEY"
    ```

    ```typescript JS/TS
    process.env.FI_API_KEY = "YOUR_API_KEY";
    process.env.FI_SECRET_KEY = "YOUR_SECRET_KEY";
    process.env.OPENAI_API_KEY = "YOUR_OPENAI_API_KEY";
    ```
    </CodeGroup>
  </Step>
  <Step title="Register Your Observe Project">
    Register your project with the necessary configuration.

    <CodeGroup titles={["Python", "JS/TS"]}>
    ```python Python
    from fi_instrumentation import register, Transport
    from fi_instrumentation.fi_types import ProjectType

    trace_provider = register(
        project_type=ProjectType.OBSERVE,
        project_name="my-llm-app",
        transport=Transport.GRPC,
    )
    ```

    ```typescript JS/TS
    import { register, ProjectType } from "@traceai/fi-core";

    const traceProvider = register({
        project_type: ProjectType.OBSERVE,
        project_name: "my-llm-app",
    });
    ```
    </CodeGroup>

    **Configuration Parameters:**
    - **project_type**: Set as `ProjectType.OBSERVE` for observe
    - **project_name**: A descriptive name for your project
    - **transport** (optional): Set the transport for your traces. The available options are `GRPC` and `HTTP`.
  </Step>
  <Step title="Instrument and Run">
    There are 2 ways to implement tracing in your project:

    1. **Auto Instrumentor**: Automatically captures all LLM calls. Recommended for most use cases.
    2. **Manual Tracing**: Gives you full control over what gets traced using OpenTelemetry. [Learn more](/docs/observe/features/manual-tracing/set-up-tracing)

    Here's a complete example using auto-instrumentation with OpenAI:

    <CodeGroup titles={["Python", "JS/TS"]}>
    ```python Python
    from traceai_openai import OpenAIInstrumentor
    from openai import OpenAI

    # Enable auto-instrumentation
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)

    # Use OpenAI as normal
    client = OpenAI()

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Write a one-sentence bedtime story about a unicorn."}]
    )

    print(completion.choices[0].message.content)
    ```

    ```typescript JS/TS
    import { OpenAIInstrumentation } from "@traceai/openai";
    import { OpenAI } from "openai";

    const openaiInstrumentation = new OpenAIInstrumentation({
        tracerProvider: traceProvider,
    });

    const client = new OpenAI();

    const completion = await client.chat.completions.create({
        model: "gpt-4o",
        messages: [{ role: "user", content: "Write a one-sentence bedtime story about a unicorn." }],
    });

    console.log(completion.choices[0].message.content);
    ```
    </CodeGroup>
  </Step>
  <Step title="View Your Traces">
    Open your [Future AGI dashboard](https://app.futureagi.com) and navigate to the **Observe** tab. You should see your project listed with the trace from the OpenAI call above.

    Each trace shows the full request and response, latency, token usage, and cost. From here you can set up alerts, track sessions, and add inline evaluations.
  </Step>
</Steps>

<div class="docs-section-title">Next Steps</div>

- [Add more integrations](/docs/integrations) for Anthropic, LangChain, LlamaIndex, and others
- [Set up manual tracing](/docs/observe/features/manual-tracing/set-up-tracing) for custom spans and attributes
- [Add inline evaluations](/docs/observe/features/manual-tracing/in-line-evals) to evaluate traces as they come in
```

---

## Example 3: `/docs/annotations/` — Annotations Overview

**Why it's good:** The three-primitives table (Labels / Queues / Scores) gives readers an instant mental model before they dive into feature pages. Supported source types as a table with raw entity names (`trace`, `observation_span`) respects developer intelligence — no hand-wavy abstractions. Key capabilities use a tight bullet list, not paragraphs. The use-case table maps real-world tasks to concrete label types and examples in one glance.

```mdx
---
title: "Annotations"
description: "Add human feedback to your AI outputs with annotation labels, queues, and scores across traces, datasets, prototypes, and simulations."
---

## About

Annotations are human labels applied to AI outputs -- traces, spans, sessions, dataset rows, prototype runs, and simulation executions. They capture subjective judgments (sentiment, quality, helpfulness) and factual assessments (correctness, safety, relevance) that automated evals alone cannot provide.

Human-in-the-loop (HITL) feedback is essential for GenAI systems because:

- **Quality control** -- Catch hallucinations, off-topic responses, and policy violations before they reach users.
- **Feedback loops** -- Route human judgments back into prompt tuning, guardrail configuration, and model selection.
- **Fine-tuning data** -- Build high-quality labeled datasets from production traffic to improve your models.
- **Safety and compliance** -- Document human review for regulated or high-stakes use cases.

## Architecture

Annotations are built on three primitives:

| Primitive | Purpose |
|-----------|---------|
| **Labels** | Reusable annotation templates (categorical, numeric, text, star rating, thumbs up/down) shared across your organization. |
| **Queues** | Managed annotation campaigns that assign items to annotators, track progress, and enforce review workflows. |
| **Scores** | The unified data record created each time an annotator (or automation) applies a label to a source. |

Labels define *what* you measure. Queues organize *how* the work gets done. Scores store *every individual annotation*.

## Supported source types

| Source Type | Description |
|-------------|-------------|
| `trace` | An LLM trace from Observe |
| `observation_span` | A specific span within a trace |
| `trace_session` | A conversation session (group of traces) |
| `dataset_row` | A row in a dataset |
| `call_execution` | A simulation call execution |
| `prototype_run` | A prototype/experiment run |

## How it works

The typical annotation workflow follows three steps:

1. **Define labels** -- Create the annotation templates your team will use (e.g. a "Sentiment" categorical label or a "Quality" star rating).
2. **Set up a queue** -- Build an annotation campaign by choosing labels, adding annotators, and configuring assignment rules.
3. **Annotate and review** -- Add items (traces, dataset rows, etc.) to the queue. Annotators score each item. Reviewers optionally approve results.

Annotations can also be created **inline** -- directly from any trace, session, or dataset view -- without a queue, for ad-hoc feedback.

## Key capabilities

- **5 label types** -- Categorical, numeric, free-text, star rating, and thumbs up/down to cover any feedback need.
- **Managed queues** -- Round-robin, load-balanced, or manual assignment strategies with reservation timeouts.
- **Inline annotations** -- Annotate directly from trace detail, session grid, or dataset views without opening a queue.
- **Multi-annotator support** -- Require 1-10 annotators per item for inter-annotator agreement.
- **Review workflows** -- Route completed items through a reviewer before finalizing.
- **Export to dataset** -- Turn annotated data into training or eval datasets.
- **Python and JS SDK** -- Create labels, manage queues, and submit scores programmatically.

## Common use cases

| Use Case | Label Type | Example |
|----------|------------|---------|
| Sentiment classification | Categorical | Positive / Negative / Neutral |
| Factual accuracy | Thumbs up/down | Correct vs. hallucinated |
| Toxicity screening | Categorical | Safe / Borderline / Toxic |
| Response relevance | Numeric (1-10) | How relevant was the answer? |
| Grammar and style | Text | Free-form correction notes |
| Prompt A vs. B comparison | Star rating | Rate each variant 1-5 stars |

## Get started

<CardGroup cols={2}>
  <Card title="Quickstart" icon="rocket" href="/docs/annotations/quickstart">
    Create a label, set up a queue, and annotate your first item in 5 minutes.
  </Card>
  <Card title="Annotation Labels" icon="tags" href="/docs/annotations/features/labels">
    Understand the five label types and when to use each one.
  </Card>
  <Card title="Queues & Workflow" icon="list-check" href="/docs/annotations/features/queues">
    Learn how queues organize work with assignment strategies and review workflows.
  </Card>
  <Card title="Scores" icon="chart-simple" href="/docs/annotations/concepts/scores">
    Dive into the unified Score model that powers all annotation data.
  </Card>
</CardGroup>
```
