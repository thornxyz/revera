# Revera - Multi-Agent Research Tool

A research system combining **Triple Hybrid RAG** (Dense + Sparse + ColBERT), live web search, and multi-agent orchestration powered by **LangGraph**. Leverages **Gemini 3** with native thinking mode, **Reciprocal Rank Fusion (RRF)**, and parallel execution for fast, accurate research answers with transparent reasoning.

## Architecture

```mermaid
flowchart TB
    subgraph Frontend["Frontend (Next.js + React)"]
        UI[Research UI]
        Timeline[Agent Timeline]
        DocPanel[Documents Panel]
        ChatList[Chat Management]
    end

    subgraph API["API Layer (FastAPI)"]
        ResearchAPI["/api/research/*"]
        DocumentsAPI["/api/documents/*<br/>(PDF + Images)"]
        HistoryAPI["/api/research/history/*"]
        ChatsAPI["/api/chats/*<br/>(Query + CRUD)"]
    end

    subgraph LangGraph["LangGraph Workflow (Orchestrator)"]
        Planner["🎯 Planning<br/>(Query Analysis)"]
        Retrieval["📚 Retrieval<br/>(Hybrid RAG)"]
        WebSearch["🌐 Web Search<br/>(Tavily)"]
        Synthesis["✍️ Synthesis<br/>(Multimodal Answer)"]
        Critic["🔍 Critic<br/>(Verify & Rate)"]
        
        Planner --> Retrieval
        Retrieval --> WebSearch
        Retrieval --> Synthesis
        WebSearch --> Synthesis
        Synthesis --> Critic
        Critic -->|needs refinement| Synthesis
        Critic -->|verified| End[END]
    end

    subgraph Services["Core Services"]
        Ingestion["Document Ingestion<br/>(PDF → Chunks)"]
        ImageIngest["Image Ingestion<br/>(Vision → Embeddings)"]
        HybridRAG["Triple Hybrid Search<br/>(Dense + Sparse + ColBERT)"]
        TitleGen["Title Generator<br/>(Auto-naming)"]
        Cleanup["Chat Cleanup<br/>(Cascade Delete)"]
    end

    subgraph External["External APIs"]
        Gemini["Google Gemini<br/>(Embeddings + LLM + Vision)"]
        Tavily["Tavily API<br/>(Web Search)"]
    end

    subgraph Data["Data Layer"]
        Supabase[(Supabase<br/>Auth & Metadata)]
        Storage[(Supabase Storage<br/>Images)]
        Qdrant[(Qdrant<br/>Vector DB)]
        Memory[(InMemoryStore<br/>Agent Memories)]
    end

    UI --> ResearchAPI
    UI --> ChatsAPI
    DocPanel --> DocumentsAPI
    Timeline --> ResearchAPI
    ChatList --> ChatsAPI
    
    ResearchAPI --> Planner
    ChatsAPI --> Planner
    DocumentsAPI --> Ingestion
    DocumentsAPI --> ImageIngest
    ChatsAPI --> Cleanup
    
    Planner --> Gemini
    Retrieval --> HybridRAG
    WebSearch --> Tavily
    Synthesis --> Gemini
    Critic --> Gemini
    
    HybridRAG --> Qdrant
    Ingestion --> Gemini
    Ingestion --> Qdrant
    Ingestion --> Supabase
    ImageIngest --> Gemini
    ImageIngest --> Storage
    ImageIngest --> Qdrant
    ImageIngest --> Supabase
    Synthesis --> Storage
    Planner --> Memory
    Synthesis --> Memory
    TitleGen --> Gemini
    
    Cleanup --> Supabase
    Cleanup --> Storage
    Cleanup --> Qdrant
    Cleanup --> Memory
    ResearchAPI --> Supabase
    ChatsAPI --> Supabase
```

## Key Features

- **🔍 Triple Hybrid RAG**: Combines Dense (semantic), Sparse (keyword), and ColBERT (late interaction) retrieval with **Reciprocal Rank Fusion (RRF)** for superior accuracy
- **🧠 Thinking Mode**: Gemini 3's native thinking capability streams reasoning tokens in real-time for transparency
- **🖼️ Image Context**: Upload images alongside PDFs - Gemini 3 Vision analyzes images for multimodal research answers
- **🤖 Multi-Agent Orchestration**: LangGraph workflow with planning, retrieval, web search, synthesis, and critic agents
- **🌐 Live Web Search**: Tavily API integration with conditional routing based on information needs
- **♻️ Iterative Refinement**: Critic agent verifies answers and triggers re-synthesis for low-confidence results
- **⚡ Parallel Execution**: Async operations and concurrent embedding generation (~3x speedup)
- **📊 Real-Time Streaming**: SSE for live agent progress, answer chunks, and reasoning tokens
- **📚 Document Management**: Upload, index, and search PDFs and images with triple embeddings
- **💬 Chat Management**: Multi-turn conversations with comprehensive data cleanup on deletion
- **🔐 Secure Authentication**: Google OAuth via Supabase with row-level security

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui |
| **Backend** | FastAPI, Python 3.12+, asyncio |
| **Orchestration** | LangGraph (state-based agent workflow) |
| **Vector Database** | Qdrant (Triple Hybrid: Dense + Sparse + ColBERT) |
| **Agent Memory** | LangGraph InMemoryStore (episodic/semantic memory) |
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
| POST | `/api/documents/upload?chat_id={id}` | Upload PDF or image (PNG/JPG/WebP/GIF) - auto-creates chat if no `chat_id` |
| GET | `/api/documents/?chat_id={id}` | List documents (optional chat filter) |
| DELETE | `/api/documents/{id}` | Delete document and embeddings |

### Chat Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/chats/` | List all chats for user |
| POST | `/api/chats/` | Create new chat |
| GET | `/api/chats/{id}` | Get chat details |
| PUT | `/api/chats/{id}` | Update chat (e.g., title) |
| DELETE | `/api/chats/{id}` | **Comprehensive deletion** (see below) |
| GET | `/api/chats/{id}/messages` | Get all messages in chat |
| GET | `/api/chats/{id}/messages/{msg_id}/verification` | Poll verification status |
| POST | `/api/chats/{id}/query` | Send query within chat (non-streaming) |
| POST | `/api/chats/{id}/query/stream` | Send query with SSE streaming |
| GET | `/api/chats/{id}/memory` | Get agent memory context |
| GET | `/api/chats/{id}/memory/{agent}` | Get memory for specific agent |



