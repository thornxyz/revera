import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import { Message, ChatWithPreview, Verification } from '@/lib/api';

interface ChatState {
    // Chat list
    chats: ChatWithPreview[];
    chatsLoading: boolean;

    // Active chat
    currentChatId: string | null;
    messages: Message[];
    messagesLoading: boolean;

    // Preloaded messages cache (for hover preload)
    preloadedMessages: Record<string, Message[]>;

    // Actions
    setChats: (chats: ChatWithPreview[]) => void;
    setChatsLoading: (loading: boolean) => void;
    setCurrentChat: (chatId: string | null) => void;
    setMessages: (messages: Message[]) => void;
    setMessagesLoading: (loading: boolean) => void;
    updateChatTitle: (chatId: string, title: string) => void;
    updateMessageVerification: (messageId: string, verification: Verification, confidence: string) => void;
    addChat: (chat: ChatWithPreview) => void;
    removeChat: (chatId: string) => void;
    clearChat: () => void;

    // Optimistic actions
    addOptimisticMessage: (chatId: string, query: string) => string;
    removeOptimisticMessage: (messageId: string) => void;

    // Preload actions
    setPreloadedMessages: (chatId: string, messages: Message[]) => void;
    getPreloadedMessages: (chatId: string) => Message[] | undefined;
}

export const useChatStore = create<ChatState>()(
    devtools(
        (set, get) => ({
            // Initial state
            chats: [],
            chatsLoading: true,
            currentChatId: null,
            messages: [],
            messagesLoading: false,
            preloadedMessages: {},

            // Actions
            setChats: (chats) => set({ chats, chatsLoading: false }),
            setChatsLoading: (loading) => set({ chatsLoading: loading }),
            setCurrentChat: (chatId) => {
                const preloaded = chatId ? get().preloadedMessages[chatId] : undefined;
                set({
                    currentChatId: chatId,
                    messages: preloaded || [],
                    messagesLoading: !!chatId && !preloaded,
                });
            },
            setMessages: (messages) => set({ messages, messagesLoading: false }),
            setMessagesLoading: (loading) => set({ messagesLoading: loading }),
            updateChatTitle: (chatId, title) => set((state) => ({
                chats: state.chats.map(chat =>
                    chat.id === chatId
                        ? { ...chat, title, updated_at: new Date().toISOString() }
                        : chat
                )
            })),
            updateMessageVerification: (messageId, verification, confidence) => set((state) => ({
                messages: state.messages.map(msg =>
                    msg.id === messageId
                        ? { ...msg, verification, confidence }
                        : msg
                ) as Message[]
            })),
            addChat: (chat) => set((state) => ({
                chats: [chat, ...state.chats]
            })),
            removeChat: (chatId) => set((state) => {
                const isCurrentChat = state.currentChatId === chatId;
                // eslint-disable-next-line @typescript-eslint/no-unused-vars
                const { [chatId]: _removed, ...remainingPreloaded } = state.preloadedMessages;
                return {
                    chats: state.chats.filter(c => c.id !== chatId),
                    currentChatId: isCurrentChat ? null : state.currentChatId,
                    messages: isCurrentChat ? [] : state.messages,
                    preloadedMessages: remainingPreloaded,
                };
            }),
            clearChat: () => set({ currentChatId: null, messages: [] }),

            // Optimistic actions
            addOptimisticMessage: (chatId, query) => {
                const optimisticId = `optimistic-${Date.now()}`;
                const optimisticMsg: Message = {
                    id: optimisticId,
                    chat_id: chatId,
                    role: 'user',
                    query,
                    answer: null,
                    sources: [],
                    verification: null,
                    confidence: 'pending',
                    created_at: new Date().toISOString(),
                };
                set((state) => ({
                    messages: [...state.messages, optimisticMsg],
                }));
                return optimisticId;
            },
            removeOptimisticMessage: (messageId) => set((state) => ({
                messages: state.messages.filter(m => m.id !== messageId),
            })),

            // Preload actions
            setPreloadedMessages: (chatId, messages) => {
                set((state) => ({
                    preloadedMessages: { ...state.preloadedMessages, [chatId]: messages },
                }));
            },
            getPreloadedMessages: (chatId) => get().preloadedMessages[chatId],
        }),
        { name: 'chat-store' }
    )
);
