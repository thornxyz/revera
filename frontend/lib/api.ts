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
