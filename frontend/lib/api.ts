import { createClient } from "@/lib/supabase/client";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEBUG = process.env.NODE_ENV === "development";


export interface Source {
    chunk_id?: string;
    document_id?: string;
    url?: string;
    title?: string;
    content: string;
    score: number;
    type: "internal" | "web" | "image";
    // Image-specific fields
    filename?: string;
    storage_path?: string;
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

export interface Document {
    id: string;
    filename: string;
    type: "pdf" | "image";
    chat_id: string | null;
    image_url: string | null;
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


export async function uploadDocument(file: File, chatId?: string): Promise<Document> {
    const headers = (await getAuthHeaders()) as Record<string, string>;
    delete headers["Content-Type"]; // Let browser set boundary for FormData

    const formData = new FormData();
    formData.append("file", file);

    // Build URL with optional chat_id parameter
    const url = chatId
        ? `${API_BASE_URL}/api/documents/upload?chat_id=${chatId}`
        : `${API_BASE_URL}/api/documents/upload`;

    const response = await fetch(url, {
        method: "POST",
        headers,
        body: formData,
    });

    if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
    }

    return response.json();
}

export async function listDocuments(chatId?: string): Promise<{
    documents: Document[];
    total: number;
}> {
    const headers = await getAuthHeaders();
    const url = chatId
        ? `${API_BASE_URL}/api/documents/?chat_id=${chatId}`
        : `${API_BASE_URL}/api/documents/`;
    const response = await fetch(url, { headers });

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



// Chat Types and Functions
export interface Chat {
    id: string;
    user_id: string;
    title: string;
    thread_id: string;
    created_at: string;
    updated_at: string;
}

export interface ChatWithPreview extends Chat {
    last_message_preview: string | null;
    message_count: number;
}

export interface Message {
    id: string;
    chat_id: string;
    user_id: string;
    query: string;
    answer: string;
    thinking?: string;
    agent_timeline?: AgentStep[];
    sources: Source[];
    verification: Verification;
    confidence: string;
    created_at: string;
}

export interface AgentStep {
    agent: string;
    latency_ms: number;
    events: Record<string, any>;
}

export interface ChatQueryRequest {
    query: string;
    use_web?: boolean;
    document_ids?: string[];
    generate_image?: boolean;
}

export interface ChatQueryResponse {
    message_id: string;
    query: string;
    answer: string;
    sources: Source[];
    verification: Verification;
    confidence: string;
}

export async function listChats(): Promise<ChatWithPreview[]> {
    if (DEBUG) console.log('[API] Listing chats');
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/chats/`, { headers });

    if (!response.ok) {
        console.error(`[API] Failed to list chats: ${response.statusText}`);
        throw new Error(`Failed to list chats: ${response.statusText}`);
    }

    const chats = await response.json();
    if (DEBUG) console.log(`[API] Retrieved ${chats.length} chats`);
    return chats;
}

export async function createChat(title?: string): Promise<Chat> {
    if (DEBUG) console.log(`[API] Creating chat with title: ${title || 'None'}`);
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/chats/`, {
        method: "POST",
        headers,
        body: JSON.stringify({ title }),
    });

    if (!response.ok) {
        console.error(`[API] Failed to create chat: ${response.statusText}`);
        throw new Error(`Failed to create chat: ${response.statusText}`);
    }

    const chat = await response.json();
    if (DEBUG) console.log(`[API] Created chat: id=${chat.id}, title=${chat.title}`);
    return chat;
}

export async function deleteChat(chatId: string): Promise<void> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/chats/${chatId}`, {
        method: "DELETE",
        headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to delete chat: ${response.statusText}`);
    }
}

export async function getChatMessages(chatId: string): Promise<Message[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/api/chats/${chatId}/messages`, {
        headers,
    });

    if (!response.ok) {
        throw new Error(`Failed to get messages: ${response.statusText}`);
    }

    return response.json();
}

// Chat Streaming
export interface ChatStreamingCallbacks extends StreamingCallbacks {
    onMessageId?: (messageId: string) => void;
    onTitleUpdated?: (title: string, chatId: string) => void;
}

export async function sendChatMessageStream(
    chatId: string,
    request: ChatQueryRequest,
    callbacks?: ChatStreamingCallbacks,
    signal?: AbortSignal
): Promise<void> {
    if (DEBUG) console.log(`[API] Starting chat message stream for chatId=${chatId}, query="${request.query.substring(0, 50)}..."`);
    const headers = await getAuthHeaders();

    const response = await fetch(`${API_BASE_URL}/api/chats/${chatId}/query/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify(request),
        signal,
    });

    if (!response.ok) {
        console.error(`[API] Chat stream failed: ${response.statusText}`);
        throw new Error(`Chat stream failed: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
        console.error('[API] No response body from stream');
        throw new Error("No response body");
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let streamCompleted = false;

    if (DEBUG) console.log('[API] Stream reader initialized, starting to read events...');

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                if (DEBUG) console.log('[API] Stream reading complete');
                break;
            }

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
                            case "message_id":
                                if (DEBUG) console.log(`[API] Received message_id: ${data.message_id}`);
                                callbacks?.onMessageId?.(data.message_id);
                                break;
                            case "agent_status":
                                if (DEBUG) console.log(`[API] Agent status: ${data.node} - ${data.status}`);
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
                            case "title_updated":
                                if (DEBUG) console.log(`[API] Title updated: ${data.title} for chat ${data.chat_id}`);
                                callbacks?.onTitleUpdated?.(data.title, data.chat_id);
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


/**
 * Poll for verification status with exponential backoff.
 * No timeout - polls indefinitely until verification completes.
 */
export async function pollVerificationStatus(
    chatId: string,
    messageId: string,
    onUpdate: (verification: Verification, confidence: string) => void,
    signal?: AbortSignal
): Promise<void> {
    let attempt = 0;
    let delay = 2000;  // Start with 2s
    const maxDelay = 10000;  // Cap at 10s

    const poll = async () => {
        // Check if aborted before making request
        if (signal?.aborted) {
            return true;  // Stop polling
        }

        try {
            const headers = await getAuthHeaders();
            const response = await fetch(
                `${API_BASE_URL}/api/chats/${chatId}/messages/${messageId}/verification`,
                { headers, signal }
            );

            if (response.status === 200) {
                // Verification complete (either "verified" or "error")
                const data = await response.json();
                if (DEBUG) console.log(`[Polling] Verification complete: confidence=${data.confidence}`);
                onUpdate(data.verification, data.confidence);
                return true;  // Stop polling
            } else if (response.status === 202) {
                // Still pending - continue polling
                if (DEBUG) console.log(`[Polling] Verification pending (attempt ${attempt + 1})`);
                return false;
            } else if (response.status === 401) {
                // Auth issue - token might be refreshing
                console.warn(`[Polling] Auth issue (attempt ${attempt + 1}), will retry...`);
                return false;  // Continue polling
            } else {
                // Other unexpected status - log but continue polling
                console.warn(`[Polling] Unexpected status ${response.status} (attempt ${attempt + 1}), retrying...`);
                return false;  // Continue polling
            }
        } catch (error) {
            console.error("[Polling] Verification poll error:", error);
            // Network errors shouldn't stop polling - critic might still complete
            return false;
        }
    };

    // Infinite polling loop with exponential backoff
    while (true) {
        const done = await poll();

        if (done) {
            if (DEBUG) console.log(`[Polling] Verification complete after ${attempt + 1} attempts`);
            return;
        }

        // Wait before next poll
        await new Promise(resolve => setTimeout(resolve, delay));

        // Exponential backoff: 2s → 4s → 8s → 10s (capped)
        attempt++;
        if (attempt < 3) {  // First 3 attempts use exponential backoff
            delay = Math.min(delay * 2, maxDelay);
        }
        // After that, stay at maxDelay (10s between polls)

        if (DEBUG) console.log(`[Polling] Verification still pending, retry in ${delay / 1000}s (attempt ${attempt + 1})`);
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

