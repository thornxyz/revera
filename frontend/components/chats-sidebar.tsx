"use client";

import { useEffect, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Plus, Trash2, Loader2, MessageSquare } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { listChats, deleteChat, ChatWithPreview } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useChatContext } from "@/lib/chat-context";

interface ChatsSidebarProps {
    currentChatId: string | null;
    refreshToken: number;
    onChatSelect: (chatId: string) => void;
    onNewChat: () => void;
}

export function ChatsSidebar({
    currentChatId,
    refreshToken,
    onChatSelect,
    onNewChat,
}: ChatsSidebarProps) {
    const { chats, setChats } = useChatContext();
    const [isLoading, setIsLoading] = useState(true);
    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [pendingDelete, setPendingDelete] = useState<ChatWithPreview | null>(null);

    useEffect(() => {
        fetchChats();
    }, [currentChatId, refreshToken]); // Refresh when chat changes or token bumps

    const fetchChats = async () => {
        try {
            const data = await listChats();
            setChats(data);
        } catch (error) {
            console.error("Failed to fetch chats:", error);
            toast.error("Failed to load chats", {
                description: error instanceof Error ? error.message : "Please try again",
            });
        } finally {
            setIsLoading(false);
        }
    };

    const requestDelete = (e: React.MouseEvent, chat: ChatWithPreview) => {
        e.stopPropagation();
        setPendingDelete(chat);
        setConfirmOpen(true);
    };

    const handleDelete = async () => {
        if (!pendingDelete) return;

        setDeletingId(pendingDelete.id);
        const chatTitle = pendingDelete.title || "Untitled Chat";
        try {
            await deleteChat(pendingDelete.id);
            setChats((prev) => prev.filter((c) => c.id !== pendingDelete.id));
            if (currentChatId === pendingDelete.id) {
                onNewChat();
            }
            toast.success("Chat deleted", {
                description: `"${chatTitle}" has been removed`,
            });
        } catch (error) {
            console.error("Failed to delete chat:", error);
            toast.error("Failed to delete chat", {
                description: error instanceof Error ? error.message : "Please try again",
            });
        } finally {
            setDeletingId(null);
            setConfirmOpen(false);
            setPendingDelete(null);
        }
    };

    const closeConfirm = () => {
        setConfirmOpen(false);
        setPendingDelete(null);
    };

    return (
        <div className="h-full flex flex-col overflow-x-auto overflow-y-hidden">
            <div className="p-4 border-b border-slate-200">
                <Button
                    onClick={onNewChat}
                    className="w-full bg-emerald-500 hover:bg-emerald-600 text-white shadow-sm shadow-emerald-500/20"
                >
                    <Plus className="h-4 w-4 mr-2" />
                    New Chat
                </Button>
            </div>

            <ScrollArea className="flex-1 w-full overflow-x-auto">
                <div className="p-3 space-y-2 w-full">
                    {isLoading ? (
                        <div className="flex justify-center p-4">
                            <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
                        </div>
                    ) : chats.length === 0 ? (
                        <p className="text-center text-sm text-slate-500 p-4">
                            No chats yet
                        </p>
                    ) : (
                        chats.map((chat) => (
                            <div
                                key={chat.id}
                                onClick={() => onChatSelect(chat.id)}
                                className={cn(
                                    "group flex w-full min-w-0 items-start gap-2 rounded-lg border px-3 py-2.5 cursor-pointer transition-all hover:bg-slate-100",
                                    currentChatId === chat.id
                                        ? "bg-emerald-50 border-emerald-200"
                                        : "border-slate-200"
                                )}
                            >
                                <div className="flex min-w-0 flex-1 flex-col gap-1">
                                    <div className="flex items-center gap-2">
                                        <MessageSquare className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                                        <p
                                            className={cn(
                                                "text-sm font-medium leading-snug whitespace-normal wrap-break-word",
                                                currentChatId === chat.id ? "text-emerald-700" : "text-slate-700"
                                            )}
                                        >
                                            {chat.title}
                                        </p>
                                    </div>
                                    {chat.last_message_preview && (
                                        <p className="text-xs text-slate-500 line-clamp-1 pl-5">
                                            {chat.last_message_preview}
                                        </p>
                                    )}
                                    <div className="flex items-center gap-2 pl-5">
                                        <p className="text-[11px] text-slate-500">
                                            {formatDistanceToNow(new Date(chat.updated_at), { addSuffix: true })}
                                        </p>
                                        <span className="text-[11px] text-slate-400">
                                            • {chat.message_count} {chat.message_count === 1 ? "message" : "messages"}
                                        </span>
                                    </div>
                                </div>

                                <div className="flex shrink-0 items-center gap-1">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-7 w-7 text-slate-400 hover:text-rose-500 hover:bg-rose-50"
                                        onClick={(e) => requestDelete(e, chat)}
                                    >
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </ScrollArea>

            <Dialog open={confirmOpen} onOpenChange={(open) => !open && closeConfirm()}>
                <DialogContent className="bg-white border-slate-200 text-slate-900">
                    <DialogHeader>
                        <DialogTitle>Delete chat?</DialogTitle>
                        <DialogDescription className="text-slate-500">
                            This will permanently delete the chat, all its messages, and associated documents.
                            This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    {pendingDelete && (
                        <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                            <p className="text-sm font-medium text-slate-700">{pendingDelete.title}</p>
                            <p className="text-xs text-slate-500 mt-1">
                                {pendingDelete.message_count} {pendingDelete.message_count === 1 ? "message" : "messages"}
                            </p>
                        </div>
                    )}
                    <DialogFooter className="gap-2 sm:gap-0">
                        <Button variant="outline" onClick={closeConfirm} className="border-slate-200 text-slate-600">
                            Cancel
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={handleDelete}
                            disabled={deletingId === pendingDelete?.id}
                        >
                            {deletingId === pendingDelete?.id ? "Deleting..." : "Delete"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
