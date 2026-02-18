"use client";

import { useRef } from "react";
import { User, Bot, ExternalLink, Loader2 } from "lucide-react";
import { StreamMarkdown } from "./stream-markdown";
import { Message, Source } from "@/lib/api";
import { cn } from "@/lib/utils";
import { MessageThinking } from "./message-thinking";

interface MessageListProps {
    messages: Message[];
    isLoading?: boolean;
    className?: string;
}

export function MessageList({ messages, isLoading = false, className }: MessageListProps) {
    const containerRef = useRef<HTMLDivElement>(null);

    if (messages.length === 0 && !isLoading) {
        return (
            <div className={cn("flex items-center justify-center h-full text-slate-500 py-12", className)}>
                <div className="text-center space-y-2">
                    <Bot className="h-12 w-12 mx-auto text-slate-300" />
                    <p className="text-sm">No messages yet. Start a conversation!</p>
                </div>
            </div>
        );
    }

    return (
        <div ref={containerRef} className={cn("max-w-4xl mx-auto space-y-8 p-6", className)}>
            {messages.map((message, index) => (
                <div key={message.id} className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
                    {/* User Query */}
                    <div className="flex flex-col items-end gap-2 pr-2 sm:pr-4">
                        <div className="flex items-center gap-2 mb-1">
                            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">You</span>
                            <div className="h-6 w-6 rounded-lg bg-slate-100 flex items-center justify-center border border-slate-200/50">
                                <User className="h-3 w-3 text-slate-500" />
                            </div>
                        </div>
                        <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-tr-none bg-slate-900 text-slate-50 px-5 py-3.5 shadow-sm premium-shadow">
                            <p className="text-[14px] leading-relaxed whitespace-pre-wrap">{message.query}</p>
                        </div>
                    </div>

                    {/* Assistant Answer */}
                    <div className="flex flex-col items-start gap-2 pl-2 sm:pl-4">
                        <div className="flex items-center gap-2 mb-1">
                            <div className="h-6 w-6 rounded-lg bg-emerald-100/80 flex items-center justify-center border border-emerald-200/50">
                                <Bot className="h-3 w-3 text-emerald-600" />
                            </div>
                            <span className="text-[10px] font-bold text-emerald-600/80 uppercase tracking-widest">Assistant</span>
                        </div>
                        <div className="w-full sm:max-w-[90%] rounded-2xl rounded-tl-none bg-white border border-slate-200/60 px-6 py-5 shadow-sm premium-shadow ring-1 ring-slate-100/50">
                            <MessageThinking
                                thinking={message.thinking}
                                timeline={message.agent_timeline}
                                isStreaming={isLoading && index === messages.length - 1}
                            />

                            <div className="prose prose-slate prose-sm max-w-none">
                                <StreamMarkdown content={message.answer} isStreaming={false} />
                            </div>

                            {/* Sources and Metrics */}
                            {(message.sources?.length > 0 || message.confidence) && (
                                <div className="mt-6 pt-6 border-t border-slate-100 space-y-4">
                                    {/* Sources */}
                                    {message.sources && message.sources.length > 0 && (
                                        <div className="space-y-3">
                                            <div className="flex items-center gap-2">
                                                <div className="h-px flex-1 bg-slate-100" />
                                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                                                    Sources ({message.sources.length})
                                                </span>
                                                <div className="h-px flex-1 bg-slate-100" />
                                            </div>
                                            <div className="grid gap-3 grid-cols-1 sm:grid-cols-2">
                                                {message.sources.map((source, idx) => (
                                                    <SourceCard key={idx} source={source} index={idx + 1} />
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Confidence Badge with Score */}
                                    {message.confidence && (
                                        <div className="flex items-center justify-between gap-3 pt-2">
                                            <div className="flex items-center gap-2">
                                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Confidence</span>
                                                {message.confidence === "pending" ? (
                                                    <div className="flex items-center gap-1.5 text-xs text-blue-600">
                                                        <Loader2 className="h-3 w-3 animate-spin" />
                                                        <span className="text-[10px] font-medium">Verifying...</span>
                                                    </div>
                                                ) : (
                                                    <span
                                                        className={cn(
                                                            "text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wide",
                                                            (message.confidence === "verified" || message.confidence === "high") && "bg-emerald-100 text-emerald-700",
                                                            message.confidence === "medium" && "bg-amber-100 text-amber-700",
                                                            (message.confidence === "low" || message.confidence === "error") && "bg-rose-100 text-rose-700 font-bold"
                                                        )}
                                                    >
                                                        {message.confidence === "verified" ? "✓ Verified" : message.confidence}
                                                    </span>
                                                )}
                                            </div>

                                            {/* Numeric score meter */}
                                            {message.verification?.confidence_score !== undefined && message.confidence !== "pending" && (
                                                <div className="flex items-center gap-3">
                                                    <div className="w-24 h-1.5 bg-slate-100 rounded-full overflow-hidden ring-1 ring-slate-200/50">
                                                        <div
                                                            className={cn(
                                                                "h-full rounded-full transition-all duration-1000",
                                                                message.verification.confidence_score >= 0.8 && "bg-emerald-500",
                                                                message.verification.confidence_score >= 0.5 && message.verification.confidence_score < 0.8 && "bg-amber-500",
                                                                message.verification.confidence_score < 0.5 && "bg-rose-500"
                                                            )}
                                                            style={{ width: `${Math.round(message.verification.confidence_score * 100)}%` }}
                                                        />
                                                    </div>
                                                    <span className="text-[10px] font-bold text-slate-500 w-8 tabular-nums">
                                                        {Math.round(message.verification.confidence_score * 100)}%
                                                    </span>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            ))}

            {isLoading && (
                <div className="flex flex-col items-start gap-2 pl-2 sm:pl-4 animate-in fade-in duration-1000">
                    <div className="flex items-center gap-2 mb-1">
                        <div className="h-6 w-6 rounded-lg bg-emerald-100/80 flex items-center justify-center border border-emerald-200/50">
                            <Bot className="h-3 w-3 text-emerald-600 animate-pulse" />
                        </div>
                        <span className="text-[10px] font-bold text-emerald-600/80 uppercase tracking-widest">Assistant</span>
                    </div>
                    <div className="w-full sm:max-w-100 rounded-2xl rounded-tl-none bg-white border border-slate-200/60 px-6 py-5 shadow-sm premium-shadow ring-1 ring-slate-100/50">
                        <div className="flex items-center gap-3">
                            <div className="flex gap-1.5">
                                <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-bounce" />
                                <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-bounce [animation-delay:0.2s]" />
                                <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-bounce [animation-delay:0.4s]" />
                            </div>
                            <span className="text-xs font-medium text-slate-400 italic">Thinking...</span>
                        </div>
                    </div>
                </div>
            )}

        </div>
    );
}

function SourceCard({ source, index }: { source: Source; index: number }) {
    const isWeb = source.type === "web";
    const isImage = source.type === "image";

    return (
        <div className="group rounded-xl border border-slate-200/60 bg-slate-50/50 p-3.5 text-sm hover:bg-white hover:border-emerald-200/60 hover:shadow-md hover:shadow-emerald-500/5 transition-all duration-300">
            <div className="flex items-start gap-3">
                <span className="shrink-0 text-[10px] font-bold text-emerald-600/60 mt-0.5">
                    {index.toString().padStart(2, '0')}
                </span>
                <div className="flex-1 min-w-0 space-y-2">
                    {source.title && (
                        <div className="flex items-center justify-between gap-2">
                            <p className="font-bold text-slate-700 line-clamp-1 text-[13px] group-hover:text-emerald-700 transition-colors uppercase tracking-tight">{source.title}</p>
                            {isWeb && source.url && (
                                <a
                                    href={source.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="shrink-0 text-slate-400 hover:text-emerald-600 transition-colors bg-white p-1 rounded-md border border-slate-100 shadow-sm"
                                    title="Open in new tab"
                                >
                                    <ExternalLink className="h-3 w-3" />
                                </a>
                            )}
                        </div>
                    )}
                    <p className="text-[12px] text-slate-500 line-clamp-2 leading-relaxed italic">{source.content}</p>
                    <div className="flex items-center gap-2 pt-1">
                        <span
                            className={cn(
                                "px-2 py-0.5 rounded text-[8px] font-bold uppercase tracking-widest",
                                isWeb ? "bg-blue-50 text-blue-600 border border-blue-100" :
                                    isImage ? "bg-emerald-50 text-emerald-600 border border-emerald-100" :
                                        "bg-purple-50 text-purple-600 border border-purple-100"
                            )}
                        >
                            {isWeb ? "Web" : isImage ? "Image" : "Document"}
                        </span>
                        {source.score !== undefined && (
                            <span className="text-[9px] font-medium text-slate-400 tabular-nums">REL: {(source.score * 100).toFixed(1)}%</span>
                        )}
                        {isImage && (
                            <span className="text-[9px] font-bold text-emerald-500 uppercase tracking-tighter">AI Generated</span>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
