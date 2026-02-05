"use client";

import { useState } from "react";
import { Upload, File, X, CheckCircle, AlertCircle, ImageIcon } from "lucide-react";
import { toast } from "sonner";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { uploadDocument } from "@/lib/api";

// Supported file types
const SUPPORTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"];
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".gif"];

interface UploadDialogProps {
    open: boolean;
    chatId: string | null;
    onOpenChange: (open: boolean) => void;
    onUploadSuccess?: () => void;
    onChatCreated?: (chatId: string, title: string) => void;
}

export function UploadDialog({ open, chatId, onOpenChange, onUploadSuccess, onChatCreated }: UploadDialogProps) {
    const [file, setFile] = useState<File | null>(null);
    const [imagePreview, setImagePreview] = useState<string | null>(null);
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    const getFileExtension = (filename: string): string => {
        const parts = filename.toLowerCase().split('.');
        return parts.length > 1 ? `.${parts.pop()}` : '';
    };

    const isImageFile = (filename: string): boolean => {
        return IMAGE_EXTENSIONS.includes(getFileExtension(filename));
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = e.target.files?.[0];
        if (selectedFile) {
            const ext = getFileExtension(selectedFile.name);
            const isImage = IMAGE_EXTENSIONS.includes(ext);

            // Validate file type
            if (!SUPPORTED_EXTENSIONS.includes(ext)) {
                setError(`Unsupported file type. Supported: ${SUPPORTED_EXTENSIONS.join(', ')}`);
                toast.error("Invalid file type", {
                    description: "Supported formats: PDF, PNG, JPG, JPEG, WebP, GIF",
                });
                return;
            }

            // Validate file size (50MB for PDFs, 10MB for images)
            const maxSize = isImage ? 10 * 1024 * 1024 : 50 * 1024 * 1024;
            if (selectedFile.size > maxSize) {
                const maxMB = maxSize / (1024 * 1024);
                setError(`File size must be less than ${maxMB}MB`);
                toast.error("File too large", {
                    description: `Maximum size is ${maxMB}MB for ${isImage ? 'images' : 'PDFs'}`,
                });
                return;
            }

            setFile(selectedFile);
            setError(null);

            // Generate preview for images
            if (isImage) {
                const reader = new FileReader();
                reader.onloadend = () => {
                    setImagePreview(reader.result as string);
                };
                reader.readAsDataURL(selectedFile);
            } else {
                setImagePreview(null);
            }
        }
    };

    const handleUpload = async () => {
        if (!file) return;

        setUploading(true);
        setError(null);

        try {
            // Upload with optional chatId (backend will auto-create if not provided)
            const result = await uploadDocument(file, chatId || undefined);

            // If chat was auto-created, notify parent
            const isImage = isImageFile(result.filename);
            const displayName = result.filename.replace(/\.(pdf|png|jpg|jpeg|webp|gif)$/i, '');

            if (!chatId && result.chat_id) {
                onChatCreated?.(result.chat_id, result.filename);
                toast.success("New chat created", {
                    description: `Chat created with: ${displayName}`,
                });
            } else {
                // Regular upload to existing chat
                toast.success(isImage ? "Image uploaded" : "Document uploaded", {
                    description: `${result.filename} has been processed and indexed`,
                });
            }

            setSuccess(true);
            setTimeout(() => {
                onUploadSuccess?.();
                handleClose();
            }, 1500);
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : "Upload failed";
            setError(errorMessage);
            toast.error("Upload failed", {
                description: errorMessage,
            });
        } finally {
            setUploading(false);
        }
    };

    const handleClose = () => {
        setFile(null);
        setImagePreview(null);
        setError(null);
        setSuccess(false);
        setUploading(false);
        onOpenChange(false);
    };

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="bg-white border-slate-200 text-slate-900">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Upload className="h-5 w-5 text-emerald-500" />
                        Upload Document or Image
                    </DialogTitle>
                    <DialogDescription className="text-slate-500">
                        {chatId
                            ? "Upload a PDF or image to add to this chat's knowledge base."
                            : "Upload a PDF or image. A new chat will be created automatically."
                        }
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                    {/* File Input */}
                    {!file && !success && (
                        <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-slate-200 rounded-lg cursor-pointer hover:border-emerald-400 transition-colors">
                            <div className="flex flex-col items-center justify-center pt-5 pb-6">
                                <Upload className="h-8 w-8 text-slate-400 mb-2" />
                                <p className="text-sm text-slate-600">
                                    <span className="font-semibold">Click to upload</span> or drag and drop
                                </p>
                                <p className="text-xs text-slate-500 mt-1">
                                    PDF, PNG, JPG, WebP, GIF (max 50MB PDF / 10MB images)
                                </p>
                            </div>
                            <input
                                type="file"
                                className="hidden"
                                accept=".pdf,.png,.jpg,.jpeg,.webp,.gif"
                                onChange={handleFileChange}
                            />
                        </label>
                    )}

                    {/* Selected File */}
                    {file && !success && (
                        <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
                            {imagePreview ? (
                                <img
                                    src={imagePreview}
                                    alt="Preview"
                                    className="h-12 w-12 rounded object-cover"
                                />
                            ) : isImageFile(file.name) ? (
                                <ImageIcon className="h-8 w-8 text-blue-500" />
                            ) : (
                                <File className="h-8 w-8 text-emerald-500" />
                            )}
                            <div className="flex-1 min-w-0">
                                <p
                                    className="text-sm font-medium break-all leading-snug text-slate-700"
                                    title={file.name}
                                >
                                    {file.name}
                                </p>
                                <p className="text-xs text-slate-500">
                                    {(file.size / 1024 / 1024).toFixed(2)} MB • {isImageFile(file.name) ? 'Image' : 'PDF'}
                                </p>
                            </div>
                            <button
                                onClick={() => {
                                    setFile(null);
                                    setImagePreview(null);
                                }}
                                className="text-slate-400 hover:text-slate-600"
                                disabled={uploading}
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                    )}

                    {/* Success State */}
                    {success && (
                        <div className="flex items-center gap-3 p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
                            <CheckCircle className="h-6 w-6 text-emerald-600" />
                            <div>
                                <p className="text-sm font-medium text-emerald-700">
                                    Upload successful!
                                </p>
                                <p className="text-xs text-slate-500">
                                    Your document is being processed...
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Error Message */}
                    {error && (
                        <div className="flex items-center gap-3 p-3 bg-rose-50 border border-rose-200 rounded-lg">
                            <AlertCircle className="h-5 w-5 text-rose-500" />
                            <p className="text-sm text-rose-600">{error}</p>
                        </div>
                    )}

                    {/* Actions */}
                    {file && !success && (
                        <div className="flex gap-2 justify-end">
                            <Button
                                variant="ghost"
                                onClick={handleClose}
                                disabled={uploading}
                                className="text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={handleUpload}
                                disabled={uploading}
                                className="bg-emerald-500 hover:bg-emerald-600"
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
