import { createClient } from "@/lib/supabase/client";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ResearchResponse {
    session_id: string;
    query: string;
    answer: string;
    sources: Source[];
    verification: Verification;
    confidence: string;
    total_latency_ms: number;
}

export interface Source {
    chunk_id?: string;
    document_id?: string;
    url?: string;
    title?: string;
    content: string;
    score: number;
    type: "internal" | "web";
}

export interface Verification {
    verification_status: string;
    confidence_score: number;
    verified_claims: Array<{
        claim: string;
        source: number;
        status: string;
    }>;
    unsupported_claims: Array<{
        claim: string;
        reason: string;
    }>;
    overall_assessment: string;
    criticism?: string;
}

export interface AgentTimeline {
    session_id: string;
    timeline: Array<{
        agent: string;
        events: Record<string, unknown>;
        latency_ms: number;
        timestamp: string;
    }>;
}

export interface Document {
    id: string;
    filename: string;
    created_at: string;
}

async function getAuthHeaders(): Promise<HeadersInit> {
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;

    return {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
}

export async function research(
    query: string,
    useWeb: boolean = true,
    documentIds?: string[]
): Promise<ResearchResponse> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/research/query`, {
        method: "POST",
        headers,
        body: JSON.stringify({
            query,
            use_web: useWeb,
            document_ids: documentIds,
        }),
    });

    if (!response.ok) {
        throw new Error(`Research failed: ${response.statusText}`);
    }

    return response.json();
}

export async function getTimeline(sessionId: string): Promise<AgentTimeline> {
    const headers = await getAuthHeaders();
    const response = await fetch(
        `${API_BASE_URL}/api/research/${sessionId}/timeline`,
        { headers }
    );

    if (!response.ok) {
        throw new Error(`Failed to fetch timeline: ${response.statusText}`);
    }

    return response.json();
}

export async function uploadDocument(file: File): Promise<Document> {
    const headers = (await getAuthHeaders()) as Record<string, string>;
    delete headers["Content-Type"]; // Let browser set boundary for FormData

    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
        method: "POST",
        headers,
        body: formData,
    });

    if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
    }

    return response.json();
}

export async function listDocuments(): Promise<{
    documents: Document[];
    total: number;
}> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/documents/`, { headers });

    if (!response.ok) {
        throw new Error(`Failed to list documents: ${response.statusText}`);
    }

    return response.json();
}

export async function deleteDocument(documentId: string): Promise<void> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/documents/${documentId}`, {
        method: "DELETE",
        headers,
    });

    if (!response.ok) {
        throw new Error(`Delete failed: ${response.statusText}`);
    }
}


export interface Session {
    id: string;
    query: string;
    status: "pending" | "running" | "completed" | "failed";
    created_at: string;
}

export async function listSessions(): Promise<Session[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/research/history/`, { headers });

    if (!response.ok) {
        throw new Error(`Failed to list sessions: ${response.statusText}`);
    }

    return response.json();
}

export interface SessionDetail extends Session {
    result: ResearchResponse | null;
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/research/history/${sessionId}`, {
        headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to get session: ${response.statusText}`);
    }

    return response.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/research/history/${sessionId}`, {
        method: "DELETE",
        headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to delete session: ${response.statusText}`);
    }
}


// Streaming Types
export interface StreamChunk {
    type: "agent_status" | "answer_chunk" | "thought_chunk" | "sources" | "complete" | "error";
    node?: string;
    status?: string;
    content?: string;
    sources?: Source[];
    session_id?: string;
    confidence?: string;
    total_latency_ms?: number;
    verification?: Verification;
    message?: string;
}

export interface StreamingCallbacks {
    onAgentStatus?: (node: string, status: string) => void;
    onAnswerChunk?: (content: string) => void;
    onThoughtChunk?: (content: string) => void;
    onSources?: (sources: Source[]) => void;
    onComplete?: (data: {
        session_id: string;
        confidence: string;
        total_latency_ms: number;
        sources: Source[];
        verification?: Verification;
    }) => void;
    onError?: (message: string) => void;
}

/**
 * Execute a research query with streaming responses.
 * 
 * Uses Server-Sent Events to receive real-time updates:
 * - Agent status updates as each node runs
 * - Answer chunks as the LLM generates text
 * - Sources from retrieval
 * - Final complete event with verification
 */
export async function researchStream(
    query: string,
    useWeb: boolean = true,
    documentIds?: string[],
    callbacks?: StreamingCallbacks,
): Promise<void> {
    const headers = await getAuthHeaders();

    const response = await fetch(`${API_BASE_URL}/api/research/query/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({
            query,
            use_web: useWeb,
            document_ids: documentIds,
        }),
    });

    if (!response.ok) {
        throw new Error(`Research stream failed: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
        throw new Error("No response body");
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let streamCompleted = false;

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete SSE messages
            const lines = buffer.split("\n");
            buffer = lines.pop() || ""; // Keep incomplete line in buffer

            let currentEvent = "";
            let currentData = "";

            for (const line of lines) {
                if (line.startsWith("event: ")) {
                    currentEvent = line.slice(7).trim();
                } else if (line.startsWith("data: ")) {
                    currentData = line.slice(6);
                } else if (line === "" && currentEvent && currentData) {
                    // End of event, process it
                    try {
                        const data = JSON.parse(currentData);

                        switch (currentEvent) {
                            case "agent_status":
                                callbacks?.onAgentStatus?.(data.node, data.status);
                                break;
                            case "answer_chunk":
                                callbacks?.onAnswerChunk?.(data.content);
                                break;
                            case "thought_chunk":
                                callbacks?.onThoughtChunk?.(data.content);
                                break;
                            case "sources":
                                callbacks?.onSources?.(data.sources);
                                break;
                            case "complete":
                                callbacks?.onComplete?.(data);
                                streamCompleted = true;
                                break;
                            case "error":
                                callbacks?.onError?.(data.message);
                                streamCompleted = true;
                                break;
                        }
                    } catch (e) {
                        console.error("Failed to parse SSE data:", e, currentData);
                    }

                    currentEvent = "";
                    currentData = "";
                }
            }

            // Exit early if stream is complete
            if (streamCompleted) {
                break;
            }
        }
    } finally {
        reader.releaseLock();
    }
}

