"use client";

import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { ChatWithPreview } from "@/lib/api";

interface ChatContextType {
    chats: ChatWithPreview[];
    setChats: (chats: ChatWithPreview[] | ((prev: ChatWithPreview[]) => ChatWithPreview[])) => void;
    updateChatTitle: (chatId: string, title: string) => void;
    refreshChats: () => Promise<void>;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export function ChatProvider({ children }: { children: ReactNode }) {
    const [chats, setChats] = useState<ChatWithPreview[]>([]);
    
    const updateChatTitle = useCallback((chatId: string, title: string) => {
        console.log(`[ChatContext] Updating title for chat ${chatId}:`, title);
        setChats(prev => prev.map(chat =>
            chat.id === chatId
                ? { ...chat, title, updated_at: new Date().toISOString() }
                : chat
        ));
    }, []);
    
    const refreshChats = useCallback(async () => {
        try {
            const { listChats } = await import("@/lib/api");
            const updatedChats = await listChats();
            setChats(updatedChats);
        } catch (error) {
            console.error("[ChatContext] Failed to refresh chats:", error);
        }
    }, []);
    
    return (
        <ChatContext.Provider value={{ chats, setChats, updateChatTitle, refreshChats }}>
            {children}
        </ChatContext.Provider>
    );
}

export function useChatContext() {
    const context = useContext(ChatContext);
    if (!context) {
        throw new Error("useChatContext must be used within ChatProvider");
    }
    return context;
}
