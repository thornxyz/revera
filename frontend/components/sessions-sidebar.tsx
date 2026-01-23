"use client";

import { useEffect, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Plus, Trash2, Loader2 } from "lucide-react";
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
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [pendingDelete, setPendingDelete] = useState<Session | null>(null);

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

    const requestDelete = (e: React.MouseEvent, session: Session) => {
        e.stopPropagation();
        setPendingDelete(session);
        setConfirmOpen(true);
    };

    const handleDelete = async () => {
        if (!pendingDelete) return;

        setDeletingId(pendingDelete.id);
        try {
            await deleteSession(pendingDelete.id);
            setSessions((prev) => prev.filter((s) => s.id !== pendingDelete.id));
            if (currentSessionId === pendingDelete.id) {
                onNewChat();
            }
        } catch (error) {
            console.error("Failed to delete session:", error);
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
        <div className="h-full flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-200">
                <Button
                    onClick={onNewChat}
                    className="w-full bg-emerald-500 hover:bg-emerald-600 text-white shadow-sm shadow-emerald-500/20"
                >
                    <Plus className="h-4 w-4 mr-2" />
                    New Chat
                </Button>
            </div>

            <ScrollArea className="flex-1 w-full overflow-x-hidden">
                <div className="p-3 space-y-2 w-full">
                    {isLoading ? (
                        <div className="flex justify-center p-4">
                            <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
                        </div>
                    ) : sessions.length === 0 ? (
                        <p className="text-center text-sm text-slate-500 p-4">
                            No chat history
                        </p>
                    ) : (
                        sessions.map((session) => (
                            <div
                                key={session.id}
                                onClick={() => onSessionSelect(session.id)}
                                className={cn(
                                    "group flex w-full min-w-0 items-center gap-2 rounded-lg border px-3 py-2.5 cursor-pointer transition-all hover:bg-slate-100 overflow-hidden",
                                    currentSessionId === session.id
                                        ? "bg-emerald-50 border-emerald-200"
                                        : "border-slate-200"
                                )}
                            >
                                <div className="flex min-w-0 flex-1 flex-col gap-1">
                                    <p className={cn(
                                        "text-sm font-medium truncate",
                                        currentSessionId === session.id ? "text-emerald-700" : "text-slate-700"
                                    )}>
                                        {session.query}
                                    </p>
                                    <p className="text-[11px] text-slate-500 truncate">
                                        {formatDistanceToNow(new Date(session.created_at), { addSuffix: true })}
                                    </p>
                                </div>

                                <div className="flex shrink-0 items-center gap-1">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-7 w-7 text-slate-400 hover:text-rose-500 hover:bg-rose-50"
                                        onClick={(e) => requestDelete(e, session)}
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
                            This removes the chat and its saved result. This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    {pendingDelete && (
                        <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                            {pendingDelete.query}
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
