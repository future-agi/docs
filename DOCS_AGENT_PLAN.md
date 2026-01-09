# Future AGI Documentation Agent - Implementation Plan

A custom AI agent for documentation with MCP server support and suggested follow-up questions.

---

## Tech Stack

| Layer | Technology | License/Type | Notes |
|-------|------------|--------------|-------|
| **Vector DB** | PostgreSQL + pgvector | Apache 2.0 | Open-source, self-hosted or managed |
| **Embeddings** | OpenAI `text-embedding-3-small` | Paid API | No model deployment needed |
| **Reranker** | Cohere Rerank | Paid API | No model deployment needed |
| **LLM** | Claude API | Paid API | Best for technical docs |
| **Observability** | Future AGI | - | Traces, evals, hallucination detection |
| **API Framework** | Hono | MIT | Open-source, runs on Node/Bun/Edge |
| **MCP SDK** | @modelcontextprotocol/sdk | MIT | Official TypeScript SDK |

---

## Architecture Overview

```
                              CLIENTS
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ Chat Widget  │   │  MCP Client  │   │   REST API   │
│   (React)    │   │(Claude/Cursor)│   │   Consumer   │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       └──────────────────┴──────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│              API LAYER (Hono + Node/Bun)            │
│  POST /chat  │  POST /search  │  MCP SSE /sse      │
└─────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Claude API   │  │ OpenAI API   │  │ Cohere API   │
│ (LLM)        │  │ (Embeddings) │  │ (Reranking)  │
└──────────────┘  └──────────────┘  └──────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                AGENT ORCHESTRATOR                    │
│                                                     │
│  ┌─────────┐  ┌────────┐  ┌───────────┐  ┌──────┐ │
│  │Classifier│→│ Router │→│Specialists│→│Synth. │ │
│  └─────────┘  └────────┘  └───────────┘  └──────┘ │
│                                              │     │
│                                              ▼     │
│                                    ┌─────────────┐ │
│                                    │ Suggestions │ │
│                                    │  Generator  │ │
│                                    └─────────────┘ │
└─────────────────────────────────────────────────────┘
        │                                     │
        ▼                                     ▼
┌──────────────────────┐          ┌──────────────────────┐
│  PostgreSQL +        │          │    FUTURE AGI        │
│  pgvector            │          │   (Observability)    │
│                      │          │                      │
│  • Vector embeddings │          │  • Traces            │
│  • Full-text search  │          │  • Evaluations       │
│  • Metadata          │          │  • Hallucination     │
│  • Doc graph         │          │    Detection         │
└──────────────────────┘          └──────────────────────┘
        ▲
        │
┌─────────────────────────────────────────────────────┐
│               INDEXING PIPELINE                      │
│  MDX → Parse → Chunk → OpenAI Embed → pgvector     │
│                                                     │
│  Triggered by: GitHub Actions on push (automatic)  │
└─────────────────────────────────────────────────────┘
```

---

## Automatic Index Refresh (No Manual Updates)

The vector database automatically stays in sync with your documentation through GitHub Actions.

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    Git Repository                            │
│                                                             │
│  src/content/                                               │
│  ├── getting-started.md  (modified)                         │
│  ├── authentication.md   (unchanged)                        │
│  └── new-feature.md      (added)                            │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ git push to main
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 GitHub Actions Workflow                      │
│                                                             │
│  1. Detect changed MD/MDX files (git diff)                  │
│  2. Detect deleted files                                    │
│  3. Trigger incremental indexer                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 Incremental Indexer                          │
│                                                             │
│  For each changed file:                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. Parse MD/MDX → extract content + frontmatter     │   │
│  │ 2. Compute content hash (SHA-256)                   │   │
│  │ 3. Compare with existing hash in DB                 │   │
│  │ 4. If changed:                                      │   │
│  │    a. Delete old chunks for this doc                │   │
│  │    b. Re-chunk the content                          │   │
│  │    c. Generate embeddings (OpenAI API)              │   │
│  │    d. Upsert to pgvector                            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  For deleted files:                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. Delete document record                           │   │
│  │ 2. CASCADE deletes all chunks + embeddings          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   PostgreSQL + pgvector                      │
│                                                             │
│  ✓ Index updated automatically                              │
│  ✓ Only changed docs re-embedded (cost efficient)          │
│  ✓ Deleted docs cleaned up                                  │
└─────────────────────────────────────────────────────────────┘
```

### GitHub Actions Workflow

```yaml
# .github/workflows/index-docs.yml
name: Index Documentation

on:
  push:
    paths:
      - 'src/content/**/*.md'
      - 'src/content/**/*.mdx'
    branches:
      - main

jobs:
  index:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2  # Need previous commit for diff

      - uses: pnpm/action-setup@v2
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - run: pnpm install

      # Get changed files
      - name: Get changed files
        id: changed
        run: |
          CHANGED=$(git diff --name-only HEAD~1 HEAD -- 'src/content/**/*.md' 'src/content/**/*.mdx' | tr '\n' ' ')
          echo "files=$CHANGED" >> $GITHUB_OUTPUT
          echo "Changed files: $CHANGED"

      # Get deleted files
      - name: Get deleted files
        id: deleted
        run: |
          DELETED=$(git diff --name-only --diff-filter=D HEAD~1 HEAD -- 'src/content/**/*.md' 'src/content/**/*.mdx' | tr '\n' ' ')
          echo "files=$DELETED" >> $GITHUB_OUTPUT
          echo "Deleted files: $DELETED"

      # Index changed docs
      - name: Index changed docs
        if: steps.changed.outputs.files != ''
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: pnpm --filter @futureagi/indexer index --files "${{ steps.changed.outputs.files }}"

      # Remove deleted docs from index
      - name: Remove deleted docs
        if: steps.deleted.outputs.files != ''
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: pnpm --filter @futureagi/indexer index --delete "${{ steps.deleted.outputs.files }}"

      # Log results
      - name: Summary
        run: |
          echo "### Indexing Complete" >> $GITHUB_STEP_SUMMARY
          echo "- Changed: ${{ steps.changed.outputs.files || 'none' }}" >> $GITHUB_STEP_SUMMARY
          echo "- Deleted: ${{ steps.deleted.outputs.files || 'none' }}" >> $GITHUB_STEP_SUMMARY
```

### Incremental Indexer Implementation

```typescript
// packages/indexer/src/incremental.ts
import crypto from 'crypto';
import fs from 'fs/promises';
import path from 'path';
import { glob } from 'glob';
import { db } from '@futureagi/core/db';
import { documents, chunks } from '@futureagi/core/db/schema';
import { eq } from 'drizzle-orm';
import { EmbeddingService } from './embedder';
import { parseMarkdown, chunkContent } from './parser';

export interface IndexResult {
  added: string[];
  updated: string[];
  deleted: string[];
  unchanged: string[];
}

export async function incrementalIndex(
  docsDir: string,
  options: { dryRun?: boolean } = {}
): Promise<IndexResult> {
  const embedder = new EmbeddingService();
  const mdFiles = await glob(`${docsDir}/**/*.{md,mdx}`);

  const result: IndexResult = {
    added: [],
    updated: [],
    deleted: [],
    unchanged: [],
  };

  // Get current hashes from DB
  const existingDocs = await db.query.documents.findMany({
    columns: { path: true, contentHash: true }
  });
  const existingMap = new Map(existingDocs.map(d => [d.path, d.contentHash]));

  // Process each file
  for (const file of mdFiles) {
    const content = await fs.readFile(file, 'utf-8');
    const hash = crypto.createHash('sha256').update(content).digest('hex');
    const relativePath = path.relative(docsDir, file);

    if (!existingMap.has(relativePath)) {
      // New file
      result.added.push(file);
      if (!options.dryRun) {
        await indexFile(file, relativePath, content, hash, embedder);
      }
    } else if (existingMap.get(relativePath) !== hash) {
      // Modified file
      result.updated.push(file);
      if (!options.dryRun) {
        await updateFile(file, relativePath, content, hash, embedder);
      }
    } else {
      // Unchanged
      result.unchanged.push(file);
    }

    existingMap.delete(relativePath);
  }

  // Remaining in map = deleted files
  for (const deletedPath of existingMap.keys()) {
    result.deleted.push(deletedPath);
    if (!options.dryRun) {
      await deleteFromIndex(deletedPath);
    }
  }

  return result;
}

async function indexFile(
  filePath: string,
  relativePath: string,
  content: string,
  hash: string,
  embedder: EmbeddingService
) {
  const { frontmatter, body } = parseMarkdown(content);
  const docChunks = chunkContent(body, { maxTokens: 500, overlap: 50 });

  // Insert document
  const [doc] = await db.insert(documents).values({
    path: relativePath,
    title: frontmatter.title || path.basename(relativePath, path.extname(relativePath)),
    content: body,
    frontmatter,
    contentHash: hash,
    parentPath: path.dirname(relativePath),
  }).returning();

  // Generate embeddings for all chunks
  const embeddings = await embedder.embed(docChunks.map(c => c.content));

  // Insert chunks with embeddings
  await db.insert(chunks).values(
    docChunks.map((chunk, i) => ({
      documentId: doc.id,
      content: chunk.content,
      heading: chunk.heading,
      chunkIndex: i,
      embedding: embeddings[i],
    }))
  );

  console.log(`Indexed: ${relativePath} (${docChunks.length} chunks)`);
}

async function updateFile(
  filePath: string,
  relativePath: string,
  content: string,
  hash: string,
  embedder: EmbeddingService
) {
  // Delete existing chunks (will cascade)
  await db.delete(documents).where(eq(documents.path, relativePath));

  // Re-index
  await indexFile(filePath, relativePath, content, hash, embedder);
  console.log(`Updated: ${relativePath}`);
}

async function deleteFromIndex(relativePath: string) {
  await db.delete(documents).where(eq(documents.path, relativePath));
  console.log(`Deleted: ${relativePath}`);
}
```

### CLI Tool

```typescript
// packages/indexer/src/cli.ts
import { Command } from 'commander';
import { incrementalIndex, fullIndex, indexFiles, deleteFiles } from './index';

const program = new Command();

program
  .name('docs-indexer')
  .description('Index documentation into pgvector');

program
  .command('index')
  .option('--full', 'Full reindex of all documents')
  .option('--incremental', 'Only process changed files (default)')
  .option('--files <paths>', 'Index specific files (space-separated)')
  .option('--delete <paths>', 'Delete specific paths from index')
  .option('--dry-run', 'Show what would be indexed without making changes')
  .option('--dir <path>', 'Docs directory', 'src/content')
  .action(async (options) => {
    console.log('🔍 Starting indexer...\n');

    if (options.delete) {
      const paths = options.delete.split(' ').filter(Boolean);
      console.log(`🗑️  Deleting ${paths.length} documents...`);
      if (!options.dryRun) {
        await deleteFiles(paths);
      }
      console.log('✅ Done');
      return;
    }

    if (options.files) {
      const files = options.files.split(' ').filter(Boolean);
      console.log(`📄 Indexing ${files.length} specific files...`);
      if (!options.dryRun) {
        await indexFiles(files);
      }
      console.log('✅ Done');
      return;
    }

    if (options.full) {
      console.log('🔄 Running full reindex...');
      if (!options.dryRun) {
        await fullIndex(options.dir);
      }
      console.log('✅ Done');
      return;
    }

    // Default: incremental
    console.log('📊 Running incremental index...\n');
    const result = await incrementalIndex(options.dir, { dryRun: options.dryRun });

    console.log(`
📈 Results:
   ✅ Added:     ${result.added.length} documents
   🔄 Updated:   ${result.updated.length} documents
   🗑️  Deleted:   ${result.deleted.length} documents
   ⏭️  Unchanged: ${result.unchanged.length} documents
    `);

    if (options.dryRun) {
      console.log('(Dry run - no changes made)');
    }
  });

program.parse();
```

### CLI Commands

```bash
# Full reindex (first time setup or recovery)
pnpm index --full

# Incremental (compare hashes, only process changes)
pnpm index --incremental

# Index specific files (used by CI/CD)
pnpm index --files "src/content/auth.md src/content/api.md"

# Delete specific paths from index
pnpm index --delete "src/content/deprecated.md"

# Dry run (show what would change without making changes)
pnpm index --incremental --dry-run
```

### Benefits of This Approach

| Benefit | Description |
|---------|-------------|
| **Zero Manual Work** | Happens automatically on every git push |
| **Cost Efficient** | Only re-embeds changed files (minimizes OpenAI API calls) |
| **Fast** | Incremental updates take seconds, not minutes |
| **Reliable** | Content hash ensures actual changes are detected |
| **Clean** | Deleted docs automatically removed from index |
| **Auditable** | GitHub Actions logs show exactly what changed |

---

## Suggested Questions Feature

The agent generates 3 contextually relevant follow-up questions after each response.

### Generation Strategies

1. **LLM-based** - Claude analyzes query + answer + retrieved context
2. **Doc-graph based** - Uses document hierarchy (siblings/children)
3. **Analytics-based** - Tracks popular follow-up patterns from Future AGI

### Question Types

| Type | Description | Example |
|------|-------------|---------|
| **Deepening** | Go deeper on current topic | "How do I rotate API keys?" |
| **Broadening** | Explore related topics | "What's the difference between API keys and OAuth?" |
| **Practical** | Implementation & examples | "Can you show me a code example?" |

### UI Preview

```
┌─────────────────────────────────────────────────────────┐
│  Q: How do I authenticate API requests?                 │
│                                                         │
│  A: To authenticate API requests, use Bearer tokens     │
│     in the Authorization header...                      │
│                                                         │
│  📎 Sources: [API Auth Guide] [SDK Reference]          │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │ Suggested next questions:                         │ │
│  │                                                   │ │
│  │  [How do I refresh expired tokens?]              │ │
│  │  [What are the rate limits?]                     │ │
│  │  [Show me a Python authentication example]       │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Docker Compose

```yaml
version: '3.8'

services:
  # PostgreSQL with pgvector extension
  postgres:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=docsagent
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=docsagent
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U docsagent"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Docs Agent API
  docs-agent:
    build: ./packages/api
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://docsagent:${POSTGRES_PASSWORD}@postgres:5432/docsagent
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - COHERE_API_KEY=${COHERE_API_KEY}
      - FUTUREAGI_API_KEY=${FUTUREAGI_API_KEY}
      - FUTUREAGI_HOST=${FUTUREAGI_HOST:-https://api.futureagi.com}
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
```

---

## Database Schema

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Documents table
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  path TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  frontmatter JSONB DEFAULT '{}',
  content_hash TEXT NOT NULL,           -- For change detection
  parent_path TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks table with embeddings
CREATE TABLE chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  heading TEXT,
  chunk_index INTEGER NOT NULL,
  embedding vector(1536),               -- OpenAI text-embedding-3-small
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_chunks_embedding ON chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_documents_path ON documents(path);
CREATE INDEX idx_documents_parent ON documents(parent_path);
CREATE INDEX idx_documents_hash ON documents(content_hash);

-- Full-text search
ALTER TABLE chunks ADD COLUMN fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX idx_chunks_fts ON chunks USING GIN(fts);

-- Doc graph view (for suggested questions)
CREATE VIEW doc_graph AS
SELECT
  d.id,
  d.path,
  d.title,
  d.parent_path,
  ARRAY_AGG(DISTINCT s.path) FILTER (WHERE s.id IS NOT NULL) AS sibling_paths,
  ARRAY_AGG(DISTINCT c.path) FILTER (WHERE c.id IS NOT NULL) AS child_paths
FROM documents d
LEFT JOIN documents s ON s.parent_path = d.parent_path AND s.id != d.id
LEFT JOIN documents c ON c.parent_path = d.path
GROUP BY d.id, d.path, d.title, d.parent_path;

-- Analytics for popular follow-ups
CREATE TABLE query_analytics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query TEXT NOT NULL,
  doc_path TEXT,
  follow_up_clicked TEXT,
  session_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_analytics_doc ON query_analytics(doc_path);
CREATE INDEX idx_analytics_created ON query_analytics(created_at);
```

---

## Implementation Phases

### Phase 0: Foundation ✅ COMPLETE
- [x] Set up monorepo (Turborepo + pnpm)
- [x] Configure TypeScript
- [x] Create Docker Compose for PostgreSQL + pgvector
- [x] Set up database schema (Drizzle ORM)
- [x] Set up CI/CD pipeline (GitHub Actions)

**Files Created:**
```
docs-agent/
├── package.json                 # Root package with scripts
├── pnpm-workspace.yaml          # Workspace config
├── turbo.json                   # Turborepo config
├── tsconfig.json                # Root TS config
├── tsconfig.base.json           # Shared TS config
├── docker-compose.yml           # PostgreSQL + pgvector
├── .env.example                 # Environment template
├── .gitignore
├── scripts/
│   └── init-db.sql              # DB initialization
├── .github/workflows/
│   ├── ci.yml                   # Build & typecheck
│   └── index-docs.yml           # Auto-indexing
└── packages/
    ├── core/                    # DB schema, types
    │   ├── package.json
    │   ├── tsconfig.json
    │   ├── drizzle.config.ts
    │   └── src/
    │       ├── index.ts
    │       ├── types.ts
    │       └── db/
    │           ├── index.ts
    │           └── schema.ts
    ├── indexer/                 # (structure ready)
    ├── rag/                     # (structure ready)
    ├── agent/                   # (structure ready)
    ├── api/                     # (structure ready)
    ├── mcp-server/              # (structure ready)
    └── chat-widget/             # (structure ready)
```

### Phase 1: Indexing Pipeline ✅ COMPLETE
- [x] MDX/MD parser (frontmatter + content extraction)
- [x] Semantic chunker (split by headings, 500 token chunks with overlap)
- [x] OpenAI embedding client (text-embedding-3-small, batched requests)
- [x] PostgreSQL/pgvector client (Drizzle ORM, lazy connection)
- [x] Incremental indexer with content hashing (SHA-256)
- [x] CLI tool (`pnpm index` with --full, --incremental, --files, --delete, --dry-run)
- [x] GitHub Actions workflow for auto-indexing (already in Phase 0)

**Files Created:**
```
packages/indexer/src/
├── parser.ts        # MDX/MD parsing with gray-matter, content cleaning
├── chunker.ts       # Semantic chunking by headings, token limits
├── embedder.ts      # OpenAI embedding client with batching
├── indexer.ts       # Incremental/full indexing with hash comparison
├── cli.ts           # Commander CLI interface
├── index.ts         # Module exports
└── test.ts          # Test script for validation
```

**Test Results (218 MDX files found):**
- Parser correctly extracts frontmatter, title, headings
- Chunker generates avg 3.4 chunks/file with ~370 tokens/file
- All TypeScript types check successfully

### Phase 2: RAG Engine ✅ COMPLETE
- [x] Hybrid search (pgvector + full-text tsvector with RRF fusion)
- [x] Cohere reranker client (rerank-v3.5)
- [x] Query preprocessing (intent detection, keyword extraction, entities)
- [x] Context assembly + formatting (numbered citations, source tracking)
- [x] Unified RAG Engine class (combines all components)

**Files Created:**
```
packages/rag/src/
├── retriever.ts     # Hybrid search with vector + FTS + RRF fusion
├── reranker.ts      # Cohere reranker client
├── preprocessor.ts  # Query intent detection, keyword extraction
├── context.ts       # Context assembly with citations
├── engine.ts        # Unified RAG Engine
├── index.ts         # Module exports
└── test.ts          # Test script
```

**Test Results:**
- Hybrid search working with ~500-1000ms latency
- Query intent detection: how_to, what_is, troubleshoot, example, api_reference, general
- Context assembly with numbered citations and source tracking
- All TypeScript types check successfully

### Phase 3: Agent Core ✅ COMPLETE
- [x] Query classifier (intent + entity extraction, rule-based + optional LLM)
- [x] Router (deterministic specialist selection with confidence threshold)
- [x] Base specialist agent (ReAct loop with tool use)
- [x] API specialist agent (API docs, endpoints, SDK methods)
- [x] Concept specialist agent (explanations, definitions, comparisons)
- [x] Tutorial specialist agent (how-to guides, step-by-step, code examples)
- [x] Debug specialist agent (errors, troubleshooting, fixes)
- [x] General specialist agent (fallback for uncategorized queries)
- [x] Response synthesizer (formatting, citations, suggested questions)
- [x] Suggestions generator (rule-based + optional LLM)
- [x] Agent orchestrator (full pipeline coordination, streaming support)

**Files Created:**
```
packages/agent/src/
├── classifier.ts      # Query classifier (rule-based + LLM modes)
├── router.ts          # Specialist router with confidence threshold
├── synthesizer.ts     # Response formatting with citations
├── suggestions.ts     # Follow-up question generation
├── orchestrator.ts    # Full agent pipeline orchestration
├── specialists/
│   ├── base.ts        # Base ReAct agent with tool use
│   ├── api.ts         # API reference specialist
│   ├── concept.ts     # Concept explanation specialist
│   ├── tutorial.ts    # Tutorial/how-to specialist
│   ├── debug.ts       # Debug/troubleshooting specialist
│   ├── general.ts     # General fallback specialist
│   └── index.ts       # Specialist exports
├── index.ts           # Module exports
└── test.ts            # Test script
```

**Test Results:**
- Query classifier correctly identifies 6 specialist types
- Router selects appropriate specialist with confidence scoring
- Specialists use ReAct loop with search, get_document, find_related tools
- Response synthesizer formats answers with numbered citations
- Suggestions generator provides contextual follow-up questions
- Streaming support for real-time UI updates
- All TypeScript types check successfully

### Phase 4: Suggested Questions ✅ PARTIALLY COMPLETE (merged into Phase 3)
- [x] LLM-based suggestion generator (Claude) - in suggestions.ts
- [x] Rule-based suggestions (specialist-specific, entity-based, query-based)
- [ ] Doc-graph based suggestions (PostgreSQL query) - pending
- [ ] Analytics-based popular follow-ups - pending
- [x] Suggestion merger + ranker - in suggestions.ts
- [x] Integration into response pipeline - in orchestrator.ts

*Note: Core suggestions functionality implemented in Phase 3. Doc-graph and analytics features can be added later.*

### Phase 5: API Layer ✅ COMPLETE
- [x] Hono API setup (Node.js with @hono/node-server)
- [x] REST endpoints (chat, search, suggestions, health)
- [x] Streaming SSE for chat responses
- [x] Rate limiting middleware (in-memory, configurable)
- [x] API key auth middleware (optional, configurable)
- [ ] OpenAPI spec generation (pending)

**Files Created:**
```
packages/api/src/
├── index.ts              # Main entry, app setup, server start
├── config.ts             # Environment-based configuration
├── embedder.ts           # OpenAI embedder service
├── middleware/
│   ├── auth.ts           # API key authentication
│   └── rateLimit.ts      # Rate limiting (60 req/min default)
└── routes/
    ├── index.ts          # Route exports
    ├── chat.ts           # POST /chat with streaming support
    ├── search.ts         # POST/GET /search
    ├── suggestions.ts    # POST /suggestions
    └── health.ts         # GET /health, /health/ready
```

**API Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | / | API info and endpoint list |
| POST | /chat | Chat with agent (supports streaming) |
| GET | /chat/specialists | List available specialists |
| POST | /search | Search documentation |
| GET | /search?q= | Quick search via query params |
| POST | /suggestions | Generate follow-up questions |
| GET | /health | Basic health check |
| GET | /health/ready | Readiness check with DB |

**Test Results:**
- All endpoints responding correctly
- Chat returns confidence 0.82, proper citations, suggestions
- Search returns ranked results with scores
- Health check includes DB, OpenAI, Anthropic status
- Rate limiting headers present (X-RateLimit-*)

### Phase 6: MCP Server
- [ ] MCP server setup (TypeScript SDK)
- [ ] Tool: `ask_docs` (full agent query)
- [ ] Tool: `search_docs` (direct search)
- [ ] Tool: `get_page` (fetch doc page)
- [ ] Tool: `get_suggestions` (follow-up questions)
- [ ] Resources: `docs://pages/*`
- [ ] SSE transport for remote connections
- [ ] npm package (`npx @futureagi/docs-mcp`)

### Phase 7: Chat Widget
- [ ] React chat component (headless)
- [ ] Suggested questions UI (clickable chips)
- [ ] Source citations display
- [ ] Markdown rendering
- [ ] Theming + customization API
- [ ] npm package (`@futureagi/docs-chat`)
- [ ] Embed script for non-React sites

### Phase 8: Production & Observability
- [ ] Future AGI integration (traces, spans)
- [ ] Hallucination detection via Future AGI
- [ ] Error handling + graceful degradation
- [ ] Caching layer (embedding + response cache)
- [ ] Load testing
- [ ] Customer documentation
- [ ] Admin dashboard (analytics, feedback)

---

## Project Structure

```
futureagi-docs-agent/
├── .github/
│   └── workflows/
│       └── index-docs.yml       # Auto-indexing on push
│
├── packages/
│   ├── core/                    # Shared types, utils
│   │   ├── src/
│   │   │   ├── types.ts
│   │   │   ├── utils.ts
│   │   │   └── db/
│   │   │       ├── schema.ts    # Drizzle schema
│   │   │       └── client.ts
│   │   └── package.json
│   │
│   ├── indexer/                 # Indexing pipeline
│   │   ├── src/
│   │   │   ├── parser.ts        # MD/MDX parsing
│   │   │   ├── chunker.ts       # Semantic chunking
│   │   │   ├── embedder.ts      # OpenAI client
│   │   │   ├── graph.ts         # Doc graph builder
│   │   │   ├── incremental.ts   # Incremental indexing
│   │   │   └── cli.ts           # CLI entry
│   │   └── package.json
│   │
│   ├── rag/                     # RAG engine
│   │   ├── src/
│   │   │   ├── retriever.ts     # Hybrid search
│   │   │   ├── reranker.ts      # Cohere client
│   │   │   ├── context.ts       # Context assembly
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── agent/                   # Agent orchestrator
│   │   ├── src/
│   │   │   ├── orchestrator.ts  # Main agent
│   │   │   ├── classifier.ts    # Query classification
│   │   │   ├── router.ts        # Specialist routing
│   │   │   ├── specialists/
│   │   │   │   ├── base.ts      # ReAct loop
│   │   │   │   ├── api.ts
│   │   │   │   ├── concept.ts
│   │   │   │   ├── tutorial.ts
│   │   │   │   └── debug.ts
│   │   │   ├── synthesizer.ts   # Response synthesis
│   │   │   └── suggestions.ts   # Follow-up questions
│   │   └── package.json
│   │
│   ├── api/                     # REST API (Hono)
│   │   ├── src/
│   │   │   ├── routes/
│   │   │   │   ├── chat.ts
│   │   │   │   ├── search.ts
│   │   │   │   └── suggestions.ts
│   │   │   ├── middleware/
│   │   │   │   ├── auth.ts
│   │   │   │   ├── rateLimit.ts
│   │   │   │   └── futureagi.ts
│   │   │   └── index.ts
│   │   ├── Dockerfile
│   │   └── package.json
│   │
│   ├── mcp-server/              # MCP Server
│   │   ├── src/
│   │   │   ├── tools/
│   │   │   │   ├── ask-docs.ts
│   │   │   │   ├── search-docs.ts
│   │   │   │   ├── get-page.ts
│   │   │   │   └── get-suggestions.ts
│   │   │   ├── resources/
│   │   │   │   └── pages.ts
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   └── chat-widget/             # React chat component
│       ├── src/
│       │   ├── components/
│       │   │   ├── ChatWindow.tsx
│       │   │   ├── MessageList.tsx
│       │   │   ├── SuggestedQuestions.tsx
│       │   │   ├── SourceCitations.tsx
│       │   │   └── InputBox.tsx
│       │   ├── hooks/
│       │   │   ├── useChat.ts
│       │   │   └── useStreaming.ts
│       │   ├── styles/
│       │   └── index.ts
│       └── package.json
│
├── drizzle/
│   └── migrations/
│
├── docker-compose.yml
├── turbo.json
├── pnpm-workspace.yaml
└── package.json
```

---

## Key Code Examples

### Hybrid Search with pgvector

```typescript
// packages/rag/src/retriever.ts
export class HybridRetriever {
  constructor(
    private embedder: EmbeddingService,
    private reranker: RerankerService
  ) {}

  async search(query: string, options: { topK?: number } = {}): Promise<SearchResult[]> {
    const topK = options.topK || 5;
    const queryEmbedding = await this.embedder.embedQuery(query);

    // Hybrid search with RRF fusion
    const results = await db.execute(sql`
      WITH vector_search AS (
        SELECT id, content, heading, document_id,
          ROW_NUMBER() OVER (ORDER BY embedding <=> ${queryEmbedding}::vector) as rank
        FROM chunks
        ORDER BY embedding <=> ${queryEmbedding}::vector
        LIMIT 20
      ),
      fts_search AS (
        SELECT id, content, heading, document_id,
          ROW_NUMBER() OVER (ORDER BY ts_rank(fts, plainto_tsquery(${query})) DESC) as rank
        FROM chunks
        WHERE fts @@ plainto_tsquery(${query})
        LIMIT 20
      )
      SELECT DISTINCT ON (COALESCE(v.id, f.id))
        COALESCE(v.id, f.id) as id,
        COALESCE(v.content, f.content) as content,
        COALESCE(1.0/(60+v.rank), 0) + COALESCE(1.0/(60+f.rank), 0) as score
      FROM vector_search v
      FULL OUTER JOIN fts_search f ON v.id = f.id
      ORDER BY score DESC
      LIMIT 20
    `);

    // Rerank with Cohere
    const reranked = await this.reranker.rerank(
      query,
      results.rows.map(r => r.content),
      topK
    );

    return reranked;
  }
}
```

### Suggested Questions Generator

```typescript
// packages/agent/src/suggestions.ts
export class SuggestionsGenerator {
  async generate(ctx: SuggestionContext): Promise<Suggestion[]> {
    const [llm, graph, popular] = await Promise.all([
      this.generateWithLLM(ctx),
      this.generateFromDocGraph(ctx),
      this.getPopularFollowUps(ctx),
    ]);

    return this.mergeAndRank([...llm, ...graph, ...popular]).slice(0, 3);
  }

  private async generateWithLLM(ctx: SuggestionContext): Promise<Suggestion[]> {
    const response = await claude.messages.create({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 500,
      messages: [{
        role: 'user',
        content: `Based on this Q&A, suggest 3 follow-up questions:

Question: "${ctx.query}"
Answer: "${ctx.answer}"

Return JSON: [{"question": "...", "type": "deepening|broadening|practical"}]`
      }]
    });

    return JSON.parse(response.content[0].text);
  }
}
```

### MCP Server

```typescript
// packages/mcp-server/src/index.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

const server = new McpServer({ name: 'futureagi-docs', version: '1.0.0' });

server.tool('ask_docs', 'Ask documentation', { question: z.string() },
  async ({ question }) => {
    const response = await docsAgent.answer(question);
    return { content: [{ type: 'text', text: JSON.stringify(response) }] };
  }
);

server.tool('get_suggestions', 'Get follow-up questions',
  { query: z.string(), answer: z.string() },
  async (ctx) => {
    const suggestions = await suggestionsGen.generate(ctx);
    return { content: [{ type: 'text', text: JSON.stringify(suggestions) }] };
  }
);
```

---

## API Response Format

```json
{
  "answer": "To authenticate API requests, use Bearer tokens...",
  "sources": [
    { "title": "Authentication Guide", "path": "/docs/auth" }
  ],
  "confidence": 0.92,
  "suggestions": [
    { "question": "How do I refresh expired tokens?", "type": "deepening" },
    { "question": "What are the rate limits?", "type": "broadening" },
    { "question": "Show me a Python example", "type": "practical" }
  ]
}
```

---

## MCP Distribution

```json
// Remote (SSE)
{
  "mcpServers": {
    "futureagi-docs": {
      "url": "https://docs-mcp.futureagi.com/sse",
      "transport": "sse"
    }
  }
}
```

```bash
# Local (npx)
npx @futureagi/docs-mcp
```

---

## Cost Estimates (per 1000 queries)

| Service | Cost |
|---------|------|
| OpenAI Embeddings | ~$0.04 |
| Cohere Rerank | ~$1.00 |
| Claude API | ~$3.00 |
| **Total** | **~$4.04** |

---

## References

- [pgvector](https://github.com/pgvector/pgvector)
- [OpenAI Embeddings](https://platform.openai.com/docs/guides/embeddings)
- [Cohere Rerank](https://docs.cohere.com/docs/rerank)
- [MCP SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Hono](https://hono.dev/)
- [Drizzle ORM](https://orm.drizzle.team/)
