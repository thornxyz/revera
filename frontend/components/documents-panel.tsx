"use client";

import { useState, useEffect } from "react";
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
    onDocumentSelect?: (documentIds: string[]) => void;
    refreshToken?: number;
}

export function DocumentsPanel({ onDocumentSelect, refreshToken }: DocumentsPanelProps) {
    const [documents, setDocuments] = useState<Document[]>([]);
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [isLoading, setIsLoading] = useState(false);
    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [confirmOpen, setConfirmOpen] = useState(false);
    const [pendingDelete, setPendingDelete] = useState<Document | null>(null);

    useEffect(() => {
        fetchDocuments();
    }, [refreshToken]);

    const fetchDocuments = async () => {
        setIsLoading(true);
        try {
            const data = await listDocuments();
            setDocuments(data.documents);
        } catch (err) {
            setError("Failed to load documents");
        } finally {
            setIsLoading(false);
        }
    };

    const requestDelete = (e: React.MouseEvent, doc: Document) => {
        e.stopPropagation(); // Don't trigger selection
        setPendingDelete(doc);
        setConfirmOpen(true);
    };

    const handleDelete = async () => {
        if (!pendingDelete) return;

        setDeletingId(pendingDelete.id);
        try {
            await deleteDocument(pendingDelete.id);
            setDocuments((prev) => prev.filter((d) => d.id !== pendingDelete.id));
            if (selectedIds.has(pendingDelete.id)) {
                const newSelected = new Set(selectedIds);
                newSelected.delete(pendingDelete.id);
                setSelectedIds(newSelected);
                onDocumentSelect?.(Array.from(newSelected));
            }
        } catch (err) {
            setError("Failed to delete document");
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

    const toggleSelect = (id: string) => {
        const newSelected = new Set(selectedIds);
        if (newSelected.has(id)) {
            newSelected.delete(id);
        } else {
            newSelected.add(id);
        }
        setSelectedIds(newSelected);
        onDocumentSelect?.(Array.from(newSelected));
    };

    return (
        <div className="h-full flex flex-col">
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
                        <p className="text-sm text-slate-500">No documents uploaded</p>
                    ) : (
                        documents.map((doc) => (
                            <Card
                                key={doc.id}
                                className={`group cursor-pointer transition-all ${selectedIds.has(doc.id)
                                    ? "bg-emerald-50 border-emerald-200"
                                    : "bg-white/80 border-slate-200 hover:border-slate-300"
                                    }`}
                                onClick={() => toggleSelect(doc.id)}
                            >
                                <CardContent className="p-3">
                                    <div className="flex items-start gap-2">
                                        <span className="text-lg">📄</span>
                                        <div className="flex-1 min-w-0">
                                            <p
                                                className="text-sm font-medium leading-snug whitespace-normal break-words"
                                                title={doc.filename}
                                            >
                                                {doc.filename}
                                            </p>
                                            <p className="text-xs text-slate-500">
                                                {new Date(doc.created_at).toLocaleDateString()}
                                            </p>
                                        </div>
                                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-8 w-8 text-slate-400 hover:text-rose-500 hover:bg-rose-50"
                                                onClick={(e) => requestDelete(e, doc)}
                                                disabled={deletingId === doc.id}
                                            >
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                            {selectedIds.has(doc.id) && (
                                                <span className="text-emerald-600 mr-1">✓</span>
                                            )}
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        ))
                    )}
                </div>
            </ScrollArea>

            {selectedIds.size > 0 && (
                <div className="p-4 border-t border-slate-200">
                    <p className="text-xs text-slate-500">
                        {selectedIds.size} document{selectedIds.size > 1 ? "s" : ""} selected
                    </p>
                </div>
            )}

            <Dialog open={confirmOpen} onOpenChange={(open) => !open && closeConfirm()}>
                <DialogContent className="bg-white border-slate-200 text-slate-900">
                    <DialogHeader>
                        <DialogTitle>Delete document?</DialogTitle>
                        <DialogDescription className="text-slate-500">
                            This removes the document from your workspace. This action cannot be undone.
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
