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
}

export const useChatStore = create<ChatState>()(
    devtools(
        (set) => ({
            // Initial state
            chats: [],
            chatsLoading: true,
            currentChatId: null,
            messages: [],
            messagesLoading: false,

            // Actions
            setChats: (chats) => set({ chats, chatsLoading: false }),
            setChatsLoading: (loading) => set({ chatsLoading: loading }),
            setCurrentChat: (chatId) => set({ currentChatId: chatId, messages: [], messagesLoading: !!chatId }),
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
            removeChat: (chatId) => set((state) => ({
                chats: state.chats.filter(c => c.id !== chatId),
                currentChatId: state.currentChatId === chatId ? null : state.currentChatId,
                messages: state.currentChatId === chatId ? [] : state.messages,
            })),
            clearChat: () => set({ currentChatId: null, messages: [] }),
        }),
        { name: 'chat-store' }
    )
);
