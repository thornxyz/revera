# Revera - Multi-Agent Research Tool

A research system combining **Triple Hybrid RAG** (Dense + Sparse + ColBERT), live web search, and multi-agent orchestration powered by **LangGraph**. Leverages **Gemini 3** with native thinking mode, **Reciprocal Rank Fusion (RRF)**, and parallel execution for fast, accurate research answers with transparent reasoning.

## Architecture

```mermaid
flowchart TB
    subgraph Frontend["Frontend (Next.js + React)"]
        UI[Research UI]
        Timeline[Agent Timeline]
        DocPanel[Documents Panel]
    end

    subgraph API["API Layer (FastAPI)"]
        ResearchAPI["/api/research/query<br/>/api/research/query/stream"]
        DocumentsAPI["/api/documents/*"]
        HistoryAPI["/api/research/history/*"]
    end

    subgraph LangGraph["LangGraph Workflow"]
        Planner["🎯 Planning<br/>(Query Analysis)"]
        Retrieval["📚 Retrieval<br/>(Hybrid RAG)"]
        WebSearch["🌐 Web Search<br/>(Tavily)"]
        Synthesis["✍️ Synthesis<br/>(Generate Answer)"]
        Critic["🔍 Critic<br/>(Verify & Rate)"]
        
        Planner --> Retrieval
        Retrieval -->|parallel| WebSearch
        Retrieval --> Synthesis
        WebSearch --> Synthesis
        Synthesis --> Critic
        Critic -->|low confidence| Synthesis
        Critic -->|verified| End[END]
    end

    subgraph Services["Core Services"]
        Ingestion["Document Ingestion<br/>(PDF → Chunks)"]
        HybridRAG["Triple Hybrid Search<br/>(Dense + Sparse + ColBERT)"]
    end

    subgraph External["External APIs"]
        Gemini["Google Gemini<br/>(Embeddings + LLM w/ Thinking)"]
        Tavily["Tavily API<br/>(Web Search)"]
    end

    subgraph Data["Data Layer"]
        Supabase[(Supabase<br/>Auth & Metadata)]
        Qdrant[(Qdrant<br/>Vector DB)]
    end

    UI --> ResearchAPI
    DocPanel --> DocumentsAPI
    Timeline --> ResearchAPI
    
    ResearchAPI --> Planner
    DocumentsAPI --> Ingestion
    
    Retrieval --> HybridRAG
    WebSearch --> Tavily
    
    HybridRAG --> Qdrant
    Ingestion --> Gemini
    Ingestion --> Qdrant
    Synthesis --> Gemini
    Critic --> Gemini
    
    Supabase --> Ingestion
    ResearchAPI --> Supabase
```

## Key Features

- **🔍 Triple Hybrid RAG**: Combines Dense (semantic), Sparse (keyword), and ColBERT (late interaction) retrieval with **Reciprocal Rank Fusion (RRF)** for superior accuracy
- **🧠 Thinking Mode**: Gemini 3's native thinking capability streams reasoning tokens in real-time for transparency
- **🤖 Multi-Agent Orchestration**: LangGraph workflow with planning, retrieval, web search, synthesis, and critic agents
- **🌐 Live Web Search**: Tavily API integration with conditional routing based on information needs
- **♻️ Iterative Refinement**: Critic agent verifies answers and triggers re-synthesis for low-confidence results
- **⚡ Parallel Execution**: Async operations and concurrent embedding generation (~3x speedup)
- **📊 Real-Time Streaming**: SSE for live agent progress, answer chunks, and reasoning tokens
- **📚 Document Management**: Upload, index, and search PDF documents with triple embeddings
- **🔐 Secure Authentication**: Google OAuth via Supabase with row-level security

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui |
| **Backend** | FastAPI, Python 3.12+, asyncio |
| **Orchestration** | LangGraph (state-based agent workflow) |
| **Vector Database** | Qdrant (Triple Hybrid: Dense + Sparse + ColBERT) |
| **Embeddings** | Gemini 3 (3072d dense), FastEmbed (BM25, ColBERT) |
| **LLM** | Gemini 3 Flash Preview (with native thinking mode) |
| **Web Search** | Tavily API |
| **Auth & Metadata** | Supabase (PostgreSQL, JWT) |
| **UI Components** | shadcn/ui, Radix UI, lucide-react icons |

### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Copy environment template and add your API keys
cp example.env .env
# Install dependencies
uv sync

# Run the server (starts on http://localhost:8000)
uv run main.py
```

### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Copy environment template
cp example.env .env.local

# Install dependencies
pnpm install
# Start development server (runs on http://localhost:3000)
pnpm dev
```

### Environment Variables

**Backend (.env)**:
```
# Application
DEBUG=false

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Google Gemini
GEMINI_API_KEY=your-gemini-api-key

# Tavily 
TAVILY_API_KEY=your-tavily-api-key

# Qdrant
QDRANT_URL=https://your-cluster.qdrant.tech
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_UPSERT_BATCH_SIZE=50

```

**Frontend (.env.local)**:
```
# Backend API
NEXT_PUBLIC_API_URL=http://localhost:8000

# Supabase
NEXT_PUBLIC_SUPABASE_URL=your-project-url.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key

```

## API Endpoints

### Research Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/research/query` | Execute research query (non-streaming) |
| POST | `/api/research/query/stream` | Execute research query with SSE streaming |
| GET | `/api/research/{id}/timeline` | Get agent execution timeline |

### Session History

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/research/history/` | List all research sessions |
| GET | `/api/research/history/{id}` | Get session details |
| DELETE | `/api/research/history/{id}` | Delete a session |

### Document Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/documents/upload` | Upload PDF document |
| GET | `/api/documents/` | List all documents |
| DELETE | `/api/documents/{id}` | Delete document |

### Request/Response Examples

**Research Query (POST /api/research/query)**:
```json
{
  "query": "Your research question",
  "use_web": true,
  "document_ids": ["id1", "id2"]
}
```

**Research Response**:
```json
{
  "session_id": "uuid",
  "query": "Your research question",
  "answer": "Comprehensive answer with citations",
  "sources": [{"title": "...", "url": "...", "content": "..."}],
  "verification": {"status": "verified", "confidence": 0.95},
  "confidence": "high",
  "total_latency_ms": 5000
}
```

