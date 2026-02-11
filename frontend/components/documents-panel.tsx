"use client";

import { useState, useEffect } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Trash2 } from "lucide-react";
import { listDocuments, deleteDocument, Document } from "@/lib/api";

interface DocumentsPanelProps {
    chatId: string | null;
    refreshToken?: number;
}

export function DocumentsPanel({ chatId, refreshToken }: DocumentsPanelProps) {
    const [documents, setDocuments] = useState<Document[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [pendingDelete, setPendingDelete] = useState<Document | null>(null);
    const [deletingId, setDeletingId] = useState<string | null>(null);

    useEffect(() => {
        if (chatId) {
            fetchDocuments();
        }
    }, [refreshToken, chatId]);

    const fetchDocuments = async () => {
        if (!chatId) return;

        setIsLoading(true);
        try {
            const data = await listDocuments(chatId);
            setDocuments(data.documents);
            setError(null);
        } catch (err) {
            const errorMessage = "Failed to load documents";
            setError(errorMessage);
            toast.error("Failed to load documents", {
                description: err instanceof Error ? err.message : "Please try again",
            });
        } finally {
            setIsLoading(false);
        }
    };

    const requestDelete = (e: React.MouseEvent, doc: Document) => {
        e.stopPropagation();
        setPendingDelete(doc);
        setConfirmOpen(true);
    };

    const handleDelete = async () => {
        if (!pendingDelete) return;

        setDeletingId(pendingDelete.id);
        try {
            await deleteDocument(pendingDelete.id);
            setDocuments((prev) => prev.filter((d) => d.id !== pendingDelete.id));
            toast.success("Document deleted", {
                description: `${pendingDelete.filename} has been removed`,
            });
        } catch (err) {
            const errorMessage = "Failed to delete document";
            setError(errorMessage);
            toast.error("Failed to delete document", {
                description: err instanceof Error ? err.message : "Please try again",
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
        <div className="h-full flex flex-col">
            {!chatId ? (
                <div className="flex items-center justify-center h-full p-4 text-center text-slate-500">
                    <div className="space-y-2">
                        <p className="text-sm">Select or create a chat to manage documents</p>
                    </div>
                </div>
            ) : (
                <>
                    {error && (
                        <div className="p-4 border-b border-slate-200">
                            <p className="text-xs text-rose-600">{error}</p>
                        </div>
                    )}

                    <ScrollArea className="flex-1">
                        <div className="p-4 space-y-2">
                            {isLoading ? (
                                <p className="text-sm text-slate-500">Loading...</p>
                            ) : documents.length === 0 ? (
                                <p className="text-sm text-slate-500">No documents uploaded in this chat</p>
                            ) : (
                                documents.map((doc) => (
                                    <Card
                                        key={doc.id}
                                        className="bg-white/80 border-slate-200"
                                    >
                                        <CardContent className="p-3">
                                            <div className="flex items-start gap-2">
                                                {doc.type === "image" ? (
                                                    <span className="text-lg" title="Image">🖼️</span>
                                                ) : (
                                                    <span className="text-lg" title="PDF Document">📄</span>
                                                )}
                                                <div className="flex-1 min-w-0">
                                                    <p
                                                        className="text-sm font-medium leading-snug whitespace-normal wrap-break-word"
                                                        title={doc.filename}
                                                    >
                                                        {doc.filename}
                                                    </p>
                                                    <p className="text-xs text-slate-500">
                                                        {doc.type === "image" ? "Image" : "PDF"} · {new Date(doc.created_at).toLocaleDateString()}
                                                    </p>
                                                </div>
                                                <div className="flex items-center gap-1">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 text-slate-400 hover:text-rose-500 hover:bg-rose-50"
                                                        onClick={(e) => requestDelete(e, doc)}
                                                        disabled={deletingId === doc.id}
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))
                            )}
                        </div>
                    </ScrollArea>

                    <div className="p-4 border-t border-slate-200 bg-slate-50/50">
                        <p className="text-xs text-slate-500 flex items-center gap-1">
                            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                            All workspace documents are active
                        </p>
                    </div>
                </>
            )}

            <Dialog open={confirmOpen} onOpenChange={(open) => !open && closeConfirm()}>
                <DialogContent className="bg-white border-slate-200 text-slate-900">
                    <DialogHeader>
                        <DialogTitle>Delete document?</DialogTitle>
                        <DialogDescription className="text-slate-500">
                            This removes the document from this chat. This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    {pendingDelete && (
                        <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                            {pendingDelete.filename}
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

