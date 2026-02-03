"use client";

import { useEffect, useRef } from "react";
import { User, Bot, ExternalLink } from "lucide-react";
import { StreamMarkdown } from "./stream-markdown";
import { Message, Source } from "@/lib/api";
import { cn } from "@/lib/utils";

interface MessageListProps {
    messages: Message[];
    isLoading?: boolean;
    className?: string;
}

export function MessageList({ messages, isLoading = false, className }: MessageListProps) {
    const endOfMessagesRef = useRef<HTMLDivElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const userHasScrolledRef = useRef(false);
    const lastScrollTopRef = useRef(0);

    // Track if user has manually scrolled up
    useEffect(() => {
        const container = containerRef.current?.parentElement;
        if (!container) return;

        const handleScroll = () => {
            const { scrollTop, scrollHeight, clientHeight } = container;
            const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
            
            // If user scrolled up, mark it
            if (scrollTop < lastScrollTopRef.current) {
                userHasScrolledRef.current = true;
            }
            
            // If user scrolled back to bottom, allow auto-scroll again
            if (isAtBottom) {
                userHasScrolledRef.current = false;
            }
            
            lastScrollTopRef.current = scrollTop;
        };

        container.addEventListener("scroll", handleScroll);
        return () => container.removeEventListener("scroll", handleScroll);
    }, []);

    // Auto-scroll to bottom when new messages arrive (only if user hasn't scrolled up)
    useEffect(() => {
        if (!userHasScrolledRef.current && endOfMessagesRef.current) {
            endOfMessagesRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages]);

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
        <div ref={containerRef} className={cn("space-y-6 p-6", className)}>
            {messages.map((message) => (
                <div key={message.id} className="space-y-4">
                    {/* User Query */}
                    <div className="flex gap-3">
                        <div className="shrink-0 mt-1">
                            <div className="h-8 w-8 rounded-full bg-slate-200 flex items-center justify-center">
                                <User className="h-4 w-4 text-slate-600" />
                            </div>
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-slate-900 mb-1">You</p>
                            <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3">
                                <p className="text-sm text-slate-700 whitespace-pre-wrap">{message.query}</p>
                            </div>
                        </div>
                    </div>

                    {/* Assistant Answer */}
                    <div className="flex gap-3">
                        <div className="shrink-0 mt-1">
                            <div className="h-8 w-8 rounded-full bg-emerald-100 flex items-center justify-center">
                                <Bot className="h-4 w-4 text-emerald-600" />
                            </div>
                        </div>
                        <div className="flex-1 min-w-0 space-y-3">
                            <p className="text-sm font-medium text-slate-900">Assistant</p>
                            <div className="rounded-lg bg-white border border-slate-200 px-4 py-3">
                                <StreamMarkdown content={message.answer} isStreaming={false} />
                            </div>

                            {/* Sources */}
                            {message.sources && message.sources.length > 0 && (
                                <div className="space-y-2">
                                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                                        Sources ({message.sources.length})
                                    </p>
                                    <div className="grid gap-2">
                                        {message.sources.map((source, idx) => (
                                            <SourceCard key={idx} source={source} index={idx + 1} />
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Confidence Badge */}
                            {message.confidence && (
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-slate-500">Confidence:</span>
                                    <span
                                        className={cn(
                                            "text-xs font-medium px-2 py-0.5 rounded-full",
                                            message.confidence === "high" && "bg-emerald-100 text-emerald-700",
                                            message.confidence === "medium" && "bg-amber-100 text-amber-700",
                                            message.confidence === "low" && "bg-rose-100 text-rose-700"
                                        )}
                                    >
                                        {message.confidence}
                                    </span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            ))}

            {isLoading && (
                <div className="flex gap-3">
                    <div className="shrink-0 mt-1">
                        <div className="h-8 w-8 rounded-full bg-emerald-100 flex items-center justify-center">
                            <Bot className="h-4 w-4 text-emerald-600 animate-pulse" />
                        </div>
                    </div>
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-900 mb-2">Assistant</p>
                        <div className="rounded-lg bg-white border border-slate-200 px-4 py-3">
                            <div className="flex items-center gap-2 text-slate-500">
                                <div className="h-2 w-2 rounded-full bg-emerald-500 animate-bounce" />
                                <div className="h-2 w-2 rounded-full bg-emerald-500 animate-bounce [animation-delay:0.2s]" />
                                <div className="h-2 w-2 rounded-full bg-emerald-500 animate-bounce [animation-delay:0.4s]" />
                            </div>
                        </div>
                    </div>
                </div>
            )}
            
            {/* Invisible marker for auto-scroll */}
            <div ref={endOfMessagesRef} />
        </div>
    );
}

function SourceCard({ source, index }: { source: Source; index: number }) {
    const isWeb = source.type === "web";

    return (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
            <div className="flex items-start gap-2">
                <span className="shrink-0 text-xs font-semibold text-emerald-600">
                    [{index}]
                </span>
                <div className="flex-1 min-w-0 space-y-1">
                    {source.title && (
                        <div className="flex items-center gap-2">
                            <p className="font-medium text-slate-700 line-clamp-1">{source.title}</p>
                            {isWeb && source.url && (
                                <a
                                    href={source.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="shrink-0 text-slate-400 hover:text-emerald-600 transition-colors"
                                    title="Open in new tab"
                                >
                                    <ExternalLink className="h-3.5 w-3.5" />
                                </a>
                            )}
                        </div>
                    )}
                    <p className="text-xs text-slate-600 line-clamp-2">{source.content}</p>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                        <span
                            className={cn(
                                "px-1.5 py-0.5 rounded text-[10px] font-medium",
                                isWeb ? "bg-blue-100 text-blue-700" : "bg-purple-100 text-purple-700"
                            )}
                        >
                            {isWeb ? "Web" : "Document"}
                        </span>
                        <span>Score: {source.score.toFixed(3)}</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
