"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { listDocuments, uploadDocument, Document } from "@/lib/api";

interface DocumentsPanelProps {
    onDocumentSelect?: (documentIds: string[]) => void;
}

export function DocumentsPanel({ onDocumentSelect }: DocumentsPanelProps) {
    const [documents, setDocuments] = useState<Document[]>([]);
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [isLoading, setIsLoading] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        fetchDocuments();
    }, []);

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

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setIsUploading(true);
        setError(null);

        try {
            const doc = await uploadDocument(file);
            setDocuments((prev) => [doc, ...prev]);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Upload failed");
        } finally {
            setIsUploading(false);
            e.target.value = "";
        }
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
            <div className="p-4 border-b border-neutral-800">
                <h3 className="text-sm font-medium mb-3">Documents</h3>
                <label className="block">
                    <Input
                        type="file"
                        accept=".pdf"
                        onChange={handleUpload}
                        disabled={isUploading}
                        className="hidden"
                        id="file-upload"
                    />
                    <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        disabled={isUploading}
                        onClick={() => document.getElementById("file-upload")?.click()}
                    >
                        {isUploading ? "Uploading..." : "Upload PDF"}
                    </Button>
                </label>
                {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
            </div>

            <ScrollArea className="flex-1">
                <div className="p-4 space-y-2">
                    {isLoading ? (
                        <p className="text-sm text-neutral-500">Loading...</p>
                    ) : documents.length === 0 ? (
                        <p className="text-sm text-neutral-500">No documents uploaded</p>
                    ) : (
                        documents.map((doc) => (
                            <Card
                                key={doc.id}
                                className={`cursor-pointer transition-all ${selectedIds.has(doc.id)
                                        ? "bg-violet-900/30 border-violet-700"
                                        : "bg-neutral-900/50 border-neutral-800 hover:border-neutral-700"
                                    }`}
                                onClick={() => toggleSelect(doc.id)}
                            >
                                <CardContent className="p-3">
                                    <div className="flex items-center gap-2">
                                        <span className="text-lg">📄</span>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium truncate">
                                                {doc.filename}
                                            </p>
                                            <p className="text-xs text-neutral-500">
                                                {new Date(doc.created_at).toLocaleDateString()}
                                            </p>
                                        </div>
                                        {selectedIds.has(doc.id) && (
                                            <span className="text-violet-400">✓</span>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>
                        ))
                    )}
                </div>
            </ScrollArea>

            {selectedIds.size > 0 && (
                <div className="p-4 border-t border-neutral-800">
                    <p className="text-xs text-neutral-400">
                        {selectedIds.size} document{selectedIds.size > 1 ? "s" : ""} selected
                    </p>
                </div>
            )}
        </div>
    );
}
