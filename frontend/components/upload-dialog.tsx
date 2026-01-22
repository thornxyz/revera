"use client";

import { useState } from "react";
import { Upload, File, X, CheckCircle, AlertCircle } from "lucide-react";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { uploadDocument } from "@/lib/api";

interface UploadDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onUploadSuccess?: () => void;
}

export function UploadDialog({ open, onOpenChange, onUploadSuccess }: UploadDialogProps) {
    const [file, setFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = e.target.files?.[0];
        if (selectedFile) {
            // Validate file type
            if (!selectedFile.name.toLowerCase().endsWith('.pdf')) {
                setError("Only PDF files are supported");
                return;
            }
            // Validate file size (50MB limit)
            if (selectedFile.size > 50 * 1024 * 1024) {
                setError("File size must be less than 50MB");
                return;
            }
            setFile(selectedFile);
            setError(null);
        }
    };

    const handleUpload = async () => {
        if (!file) return;

        setUploading(true);
        setError(null);

        try {
            await uploadDocument(file);
            setSuccess(true);
            setTimeout(() => {
                onUploadSuccess?.();
                handleClose();
            }, 1500);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Upload failed");
        } finally {
            setUploading(false);
        }
    };

    const handleClose = () => {
        setFile(null);
        setError(null);
        setSuccess(false);
        setUploading(false);
        onOpenChange(false);
    };

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="bg-neutral-900 border-neutral-800 text-neutral-50">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Upload className="h-5 w-5 text-violet-400" />
                        Upload Document
                    </DialogTitle>
                    <DialogDescription className="text-neutral-400">
                        Upload a PDF document to add to your research knowledge base.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                    {/* File Input */}
                    {!file && !success && (
                        <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-neutral-700 rounded-lg cursor-pointer hover:border-violet-500 transition-colors">
                            <div className="flex flex-col items-center justify-center pt-5 pb-6">
                                <Upload className="h-8 w-8 text-neutral-500 mb-2" />
                                <p className="text-sm text-neutral-400">
                                    <span className="font-semibold">Click to upload</span> or drag and drop
                                </p>
                                <p className="text-xs text-neutral-500 mt-1">
                                    PDF files only (max 50MB)
                                </p>
                            </div>
                            <input
                                type="file"
                                className="hidden"
                                accept=".pdf"
                                onChange={handleFileChange}
                            />
                        </label>
                    )}

                    {/* Selected File */}
                    {file && !success && (
                        <div className="flex items-center gap-3 p-3 bg-neutral-800 rounded-lg">
                            <File className="h-8 w-8 text-violet-400" />
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium truncate">{file.name}</p>
                                <p className="text-xs text-neutral-500">
                                    {(file.size / 1024 / 1024).toFixed(2)} MB
                                </p>
                            </div>
                            <button
                                onClick={() => setFile(null)}
                                className="text-neutral-400 hover:text-neutral-200"
                                disabled={uploading}
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                    )}

                    {/* Success State */}
                    {success && (
                        <div className="flex items-center gap-3 p-4 bg-green-900/20 border border-green-700 rounded-lg">
                            <CheckCircle className="h-6 w-6 text-green-400" />
                            <div>
                                <p className="text-sm font-medium text-green-400">
                                    Upload successful!
                                </p>
                                <p className="text-xs text-neutral-400">
                                    Your document is being processed...
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Error Message */}
                    {error && (
                        <div className="flex items-center gap-3 p-3 bg-red-900/20 border border-red-700 rounded-lg">
                            <AlertCircle className="h-5 w-5 text-red-400" />
                            <p className="text-sm text-red-400">{error}</p>
                        </div>
                    )}

                    {/* Actions */}
                    {file && !success && (
                        <div className="flex gap-2 justify-end">
                            <Button
                                variant="ghost"
                                onClick={handleClose}
                                disabled={uploading}
                                className="text-neutral-400"
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={handleUpload}
                                disabled={uploading}
                                className="bg-violet-600 hover:bg-violet-500"
                            >
                                {uploading ? "Uploading..." : "Upload"}
                            </Button>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
