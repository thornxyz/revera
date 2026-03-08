# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
cd backend
uv sync                   # Install dependencies
uv run main.py            # Run dev server (http://localhost:8000)
uv run ruff check .       # Lint
uv run ruff format .      # Format
uv run pytest             # Run all tests
uv run pytest tests/path/to/test.py  # Run single test file
```

### Frontend
```bash
cd frontend
pnpm install              # Install dependencies
pnpm dev                  # Start dev server (http://localhost:3000)
pnpm build                # Production build
pnpm lint                 # Lint
```

## Architecture

### Backend (`backend/`)

**Entry point:** `main.py` → `app/main.py` mounts four routers: `/api/chats`, `/api/documents`, `/api/research`, `/api/history`.

**Agent pipeline** (`app/agents/`):
- `orchestrator.py` — Per-user `Orchestrator` class; compiles and invokes the LangGraph graph, populates `ResearchState`, streams SSE events
- `graph_builder.py` — Builds the LangGraph `StateGraph`; fan-out from `planning` to `retrieval + web_search + image_gen` in parallel, fan-in to `synthesis`, then `critic` (or async critic in background)
- `graph_nodes.py` — One async function per node (`planning_node`, `retrieval_node`, `web_search_node`, `image_gen_node`, `synthesis_node`, `critic_node`)
- `graph_state.py` — `ResearchState` TypedDict; `agent_timeline` uses `Annotated[list, add]` for append-only updates across parallel nodes
- `planner.py`, `retrieval.py`, `synthesis.py`, `critic.py`, `web_search.py` — Agent implementations

**Core infrastructure** (`app/core/`):
- `config.py` — Pydantic settings; models hardcoded (`GEMINI_MODEL = "gemini-3-flash-preview"`, `GEMINI_IMAGE_MODEL`, `GEMINI_EMBEDDING_MODEL`)
- `qdrant.py` — `QdrantService`; Qdrant collection `revera_documents` with three named vectors: `dense` (3072-dim Gemini), `colbert` (128-dim multivector), `sparse` (BM25)
- `checkpointer.py` — LangGraph Postgres checkpointer via `SUPABASE_DB_URL`
- `supabase_memory_store.py` — LangGraph `BaseStore` backed by Supabase `agent_memory` table
- `cache.py`, `circuit_breaker.py` — Utilities for LLM call resilience
- `auth.py` — JWT validation via Supabase; `get_current_user_id` FastAPI dependency

**Services** (`app/services/`):
- `ingestion.py` — PDF/image ingest: PyMuPDF parsing → chunking → triple embeddings (Gemini dense + FastEmbed BM25 + FastEmbed ColBERT) → Qdrant upsert
- `image_ingestion.py` — Image upload path
- `search.py` — Triple Hybrid RAG retrieval with Reciprocal Rank Fusion (RRF)
- `agent_memory.py` — Reads/writes `agent_memory` table via `AgentMemoryService`
- `background_critic.py` — Critic that runs as a background task after streaming completes
- `chat_cleanup.py` — Cascade deletion across Supabase DB, Qdrant, and Supabase Storage
- `title_generator.py` — Auto-generates chat titles after first query

### Frontend (`frontend/`)

**App router** (`app/`): Single root layout with `providers.tsx` (Supabase auth context). Main page renders `ResizableLayout` with `ChatsSidebar` + chat area.

**State** (`store/chat-store.ts`): Single Zustand store with devtools. Manages chat list, active chat, messages, preloaded message cache for hover-preloading.

**Streaming** (`hooks/useStreamingChat.ts`): SSE consumer that handles all event types (`agent_status`, `answer_chunk`, `thought_chunk`, `sources`, `title_updated`, `complete`, `error`).

**API client** (`lib/api.ts`): Typed fetch wrappers for all backend endpoints.

**Rendering** (`components/stream-markdown.tsx`): Uses `streamdown` library for real-time markdown rendering with math (KaTeX) and code highlighting.

### Data Layer

**Supabase** (schema in `supabase/schema.sql`): Tables — `chats`, `messages`, `documents`, `research_sessions`, `agent_logs`, `agent_memory`. Vectors are **not** in Postgres; they live in Qdrant.

**Qdrant** (`revera_documents` collection): Each document chunk stored with `user_id`, `document_id`, `chat_id` payload fields for filtering. Payload indexes on `user_id`, `document_id`, `chat_id`.

**Supabase Storage**: Raw files (PDFs and images) stored per-user.

### Key Design Patterns

- **Async critic**: By default (`async_critic=True`), synthesis streams immediately to the client and the critic runs in a background task. The graph can also run critic inline with `async_critic=False`.
- **Per-user semaphore**: `MAX_STREAMS_PER_USER = 3` concurrent SSE streams enforced in `app/api/chats.py`.
- **Lazy graph compilation**: The `Orchestrator._graph` is compiled on first use (`_ensure_graph()`) because the async checkpointer needs to be awaited.
- **RRF fusion**: `search.py` runs dense, sparse, and ColBERT searches in parallel and merges with Reciprocal Rank Fusion before returning sources to the synthesis agent.
