"use client";

import { useEffect, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { MessageSquare, Plus, Trash2, MoreHorizontal, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { listSessions, deleteSession, Session } from "@/lib/api";
import { cn } from "@/lib/utils";

interface SessionsSidebarProps {
    currentSessionId: string | null;
    onSessionSelect: (sessionId: string) => void;
    onNewChat: () => void;
}

export function SessionsSidebar({
    currentSessionId,
    onSessionSelect,
    onNewChat,
}: SessionsSidebarProps) {
    const [sessions, setSessions] = useState<Session[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [deletingId, setDeletingId] = useState<string | null>(null);

    useEffect(() => {
        fetchSessions();
    }, [currentSessionId]); // Refresh when session changes (e.g. after new chat)

    const fetchSessions = async () => {
        try {
            const data = await listSessions();
            setSessions(data);
        } catch (error) {
            console.error("Failed to fetch sessions:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleDelete = async (e: React.MouseEvent, id: string) => {
        e.stopPropagation();
        if (!confirm("Delete this chat?")) return;

        setDeletingId(id);
        try {
            await deleteSession(id);
            setSessions((prev) => prev.filter((s) => s.id !== id));
            if (currentSessionId === id) {
                onNewChat();
            }
        } catch (error) {
            console.error("Failed to delete session:", error);
        } finally {
            setDeletingId(null);
        }
    };

    return (
        <div className="h-full flex flex-col overflow-hidden">
            <div className="p-4 border-b border-neutral-800">
                <Button
                    onClick={onNewChat}
                    className="w-full bg-violet-600 hover:bg-violet-700 text-white shadow-lg shadow-violet-900/20"
                >
                    <Plus className="h-4 w-4 mr-2" />
                    New Chat
                </Button>
            </div>

            <ScrollArea className="flex-1 w-full">
                <div className="p-3 space-y-1 w-full">
                    {isLoading ? (
                        <div className="flex justify-center p-4">
                            <Loader2 className="h-5 w-5 animate-spin text-neutral-500" />
                        </div>
                    ) : sessions.length === 0 ? (
                        <p className="text-center text-sm text-neutral-500 p-4">
                            No chat history
                        </p>
                    ) : (
                        sessions.map((session) => (
                            <div
                                key={session.id}
                                onClick={() => onSessionSelect(session.id)}
                                className={cn(
                                    "group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-all hover:bg-neutral-800/50",
                                    currentSessionId === session.id
                                        ? "bg-neutral-800 border border-neutral-700"
                                        : "border border-transparent"
                                )}
                            >
                                <div className="flex-1 min-w-0 overflow-hidden mr-2">
                                    <p className={cn(
                                        "text-sm font-medium truncate",
                                        currentSessionId === session.id ? "text-violet-400" : "text-neutral-300"
                                    )}>
                                        {session.query}
                                    </p>
                                    <p className="text-[10px] text-neutral-500 truncate">
                                        {formatDistanceToNow(new Date(session.created_at), { addSuffix: true })}
                                    </p>
                                </div>

                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity text-neutral-400 hover:text-red-400"
                                    onClick={(e) => handleDelete(e, session.id)}
                                >
                                    <Trash2 className="h-3 w-3" />
                                </Button>

                                <DropdownMenu>
                                    <DropdownMenuTrigger asChild onClick={(e: React.MouseEvent) => e.stopPropagation()}>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity text-neutral-400 hover:text-neutral-200"
                                        >
                                            <MoreHorizontal className="h-3 w-3" />
                                        </Button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="bg-neutral-900 border-neutral-800">
                                        <DropdownMenuItem
                                            className="text-red-400 focus:text-red-300 focus:bg-red-900/20 cursor-pointer"
                                            onClick={(e) => handleDelete(e, session.id)}
                                            disabled={deletingId === session.id}
                                        >
                                            <Trash2 className="h-3 w-3 mr-2" />
                                            Delete
                                        </DropdownMenuItem>
                                    </DropdownMenuContent>
                                </DropdownMenu>
                            </div>
                        ))
                    )}
                </div>
            </ScrollArea>
        </div>
    );
}
