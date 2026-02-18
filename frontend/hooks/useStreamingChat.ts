import { useState, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import {
    sendChatMessageStream,
    pollVerificationStatus,
    createChat,
    getChatMessages,
    listChats,
    Source,
    ChatWithPreview,
} from '@/lib/api';
import { useChatStore } from '@/store/chat-store';
import { ActivityLogItem } from '@/components/agent-progress';

const AGENT_MESSAGES: Record<string, string> = {
    planning: "Strategy determined",
    retrieval: "Internal documents searched",
    web_search: "External sources fetched",
    synthesis: "Response drafted",
    critic: "Claims verified",
    image_gen: "Image generated",
};

export function useStreamingChat() {
    // Streaming state
    const [isStreaming, setIsStreaming] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [streamingAnswer, setStreamingAnswer] = useState("");
    const [streamingThoughts, setStreamingThoughts] = useState("");
    const [currentAgent, setCurrentAgent] = useState<string | null>(null);
    const [streamingSources, setStreamingSources] = useState<Source[]>([]);
    const [activityLog, setActivityLog] = useState<ActivityLogItem[]>([]);
    const [error, setError] = useState<string | null>(null);

    // Refs
    const streamStartTimeRef = useRef<Date>(new Date());
    const activityLogCounterRef = useRef<number>(0);

    // Store actions
    const {
        currentChatId,
        setCurrentChat,
        setMessages,
        setChats,
        updateChatTitle,
        updateMessageVerification,
        addChat,
    } = useChatStore();

    const resetStreamingState = useCallback(() => {
        setIsStreaming(false);
        setIsLoading(false);
        setStreamingAnswer("");
        setStreamingThoughts("");
        setCurrentAgent(null);
        setStreamingSources([]);
    }, []);

    const sendMessage = useCallback(async (
        query: string,
        options?: { useWeb?: boolean }
    ) => {
        if (!query.trim()) return;

        // Auto-create chat if none selected
        let chatId = currentChatId;
        if (!chatId) {
            try {
                const newChat = await createChat();
                chatId = newChat.id;
                setCurrentChat(chatId);
                // Add to chat list with preview structure
                const chatWithPreview: ChatWithPreview = {
                    ...newChat,
                    last_message_preview: null,
                    message_count: 0,
                };
                addChat(chatWithPreview);
                toast.success("New chat created");
            } catch (err) {
                setError("Failed to create chat");
                toast.error("Failed to create chat");
                return;
            }
        }

        // Initialize streaming state
        setIsLoading(true);
        setIsStreaming(true);
        setStreamingAnswer("");
        setStreamingThoughts("");
        setCurrentAgent(null);
        setStreamingSources([]);
        setActivityLog([]);
        setError(null);
        streamStartTimeRef.current = new Date();
        activityLogCounterRef.current = 0;

        try {
            await sendChatMessageStream(
                chatId,
                {
                    query,
                    use_web: options?.useWeb ?? true,
                },
                {
                    onAgentStatus: (node, status) => {
                        if (status === "complete") {
                            setCurrentAgent(null);
                            setActivityLog((prev) => [
                                ...prev,
                                {
                                    id: `${node}-${activityLogCounterRef.current++}`,
                                    timestamp: new Date(),
                                    agent: node,
                                    status: "complete",
                                    message: AGENT_MESSAGES[node] || "Step completed",
                                },
                            ]);
                        } else {
                            setCurrentAgent(node);
                        }
                    },
                    onAnswerChunk: (content) => setStreamingAnswer((prev) => prev + content),
                    onThoughtChunk: (content) => setStreamingThoughts((prev) => prev + content),
                    onSources: (sources) => setStreamingSources((prev) => [...prev, ...sources]),
                    onTitleUpdated: (title, updatedChatId) => updateChatTitle(updatedChatId, title),
                    onComplete: async (data) => {
                        // Fetch messages first (async), then apply all state
                        // changes synchronously so React can batch them into
                        // a single render pass.
                        let fetchedMessages;
                        try {
                            fetchedMessages = await getChatMessages(chatId!);
                        } catch (err) {
                            console.error("Failed to refresh messages:", err);
                        }

                        // Apply state changes synchronously — React 18 batches
                        // these into one render, preventing the scroll jump
                        // that occurred when streaming UI unmounted separately.
                        resetStreamingState();
                        if (fetchedMessages) setMessages(fetchedMessages);

                        // Refresh sidebar chat list (message count, preview, etc.)
                        try {
                            const updatedChats = await listChats();
                            setChats(updatedChats);
                        } catch (err) {
                            console.error("Failed to refresh chat list:", err);
                        }

                        const duration = ((Date.now() - streamStartTimeRef.current.getTime()) / 1000).toFixed(1);
                        toast.success("Research complete", {
                            description: `Answer generated in ${duration}s with ${data.sources?.length || 0} sources`,
                        });

                        // Poll verification if pending
                        if (data.confidence === "pending" && data.session_id) {
                            pollVerificationStatus(
                                chatId!,
                                data.session_id,
                                (verification, newConfidence) => {
                                    updateMessageVerification(data.session_id, verification, newConfidence);
                                    toast.success("Verification complete", {
                                        description: `Confidence: ${newConfidence}`,
                                    });
                                }
                            ).catch(console.error);
                        }
                    },
                    onError: (message) => {
                        setError(message);
                        resetStreamingState();
                        toast.error("Research failed", { description: message });
                    },
                }
            );
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : "Research failed";
            setError(errorMessage);
            resetStreamingState();
            toast.error("Research failed", { description: errorMessage });
        }
    }, [currentChatId, setCurrentChat, setMessages, setChats, updateChatTitle, updateMessageVerification, addChat, resetStreamingState]);

    return {
        // State
        isStreaming,
        isLoading,
        streamingAnswer,
        streamingThoughts,
        currentAgent,
        streamingSources,
        activityLog,
        error,

        // Actions
        sendMessage,
        resetStreamingState,
        setError,
        setActivityLog,
    };
}
