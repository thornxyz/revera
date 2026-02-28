import { useState, useRef, useCallback, useEffect } from 'react';
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
import { AGENT_MESSAGES } from '@/lib/constants';

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
        const sessionIdRef = useRef<string | null>(null);
        const pollAbortRef = useRef<AbortController | null>(null);

    // Abort any in-flight verification poll on unmount
    useEffect(() => {
        return () => {
            pollAbortRef.current?.abort();
        };
    }, []);

    // Store actions
    const {
        currentChatId,
        setCurrentChat,
        setMessages,
        setChats,
        updateChatTitle,
        updateMessageVerification,
        addChat,
        addOptimisticMessage,
        removeOptimisticMessage,
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

        // Add optimistic message to store
        const optimisticId = addOptimisticMessage(chatId, query);

        // --- Frame-based update buffering ---
        // Buffers incoming characters and flushes them on the next animation frame
        // to prevent React state update waterfalls on every tiny chunk.
        let answerBuffer = "";
        let thoughtsBuffer = "";
        let animationFrameId: number | null = null;

        const flushBuffers = () => {
            if (answerBuffer) {
                const chunk = answerBuffer;
                answerBuffer = "";
                setStreamingAnswer((prev) => prev + chunk);
            }
            if (thoughtsBuffer) {
                const chunk = thoughtsBuffer;
                thoughtsBuffer = "";
                setStreamingThoughts((prev) => prev + chunk);
            }
            animationFrameId = null;
        };

        const scheduleFlush = () => {
            if (animationFrameId === null) {
                animationFrameId = requestAnimationFrame(flushBuffers);
            }
        };

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
                    onAnswerChunk: (content) => {
                        answerBuffer += content;
                        scheduleFlush();
                    },
                    onThoughtChunk: (content) => {
                        thoughtsBuffer += content;
                        scheduleFlush();
                    },
                    onSources: (sources) => setStreamingSources((prev) => [...prev, ...sources]),
                    onTitleUpdated: (title, updatedChatId) => updateChatTitle(updatedChatId, title),
                    onVerificationPending: (sessionId) => {
                        sessionIdRef.current = sessionId;
                    },
                    onComplete: async (data) => {
                        // Ensure final chunks are flushed before completion
                        if (animationFrameId) cancelAnimationFrame(animationFrameId);
                        flushBuffers();

                        // Parallel fetch: messages and chat list at the same time
                        const [fetchedMessages, updatedChats] = await Promise.all([
                            getChatMessages(chatId!),
                            listChats(),
                        ]);

                        // Apply state changes synchronously — React 18 batches
                        // these into one render.
                        resetStreamingState();
                        if (fetchedMessages) {
                            // Remove optimistic message and set real messages
                            removeOptimisticMessage(optimisticId);
                            setMessages(fetchedMessages);
                        }
                        if (updatedChats) setChats(updatedChats);

                        const duration = ((Date.now() - streamStartTimeRef.current.getTime()) / 1000).toFixed(1);
                        toast.success("Research complete", {
                            description: `Answer generated in ${duration}s with ${data.sources?.length || 0} sources`,
                        });

                        // Poll verification if pending (async critic mode)
                        const verificationSessionId = sessionIdRef.current || data.session_id;
                        if (data.confidence === "pending" && verificationSessionId) {
                            pollAbortRef.current?.abort();
                            pollAbortRef.current = new AbortController();
                            pollVerificationStatus(
                                chatId!,
                                verificationSessionId,
                                (verification, newConfidence) => {
                                    updateMessageVerification(verificationSessionId, verification, newConfidence);
                                    toast.success("Verification complete", {
                                        description: `Confidence: ${newConfidence}`,
                                    });
                                },
                                pollAbortRef.current.signal
                            ).catch(console.error);
                        }
                    },
                     onError: (message) => {
                         if (animationFrameId) cancelAnimationFrame(animationFrameId);
                         setError(message);
                         removeOptimisticMessage(optimisticId);
                         resetStreamingState();
                         toast.error("Research failed", { description: message });
                     },
                }
            );
        } catch (err) {
            if (animationFrameId) cancelAnimationFrame(animationFrameId);
            const errorMessage = err instanceof Error ? err.message : "Research failed";
            setError(errorMessage);
            removeOptimisticMessage(optimisticId);
            resetStreamingState();
            toast.error("Research failed", { description: errorMessage });
        }
    }, [currentChatId, setCurrentChat, setMessages, setChats, updateChatTitle, updateMessageVerification, addChat, addOptimisticMessage, removeOptimisticMessage, resetStreamingState]);

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
