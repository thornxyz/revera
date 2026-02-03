"use client";

import { useEffect, useRef } from "react";
import { Check, Loader2, Search, FileText, Globe, Sparkles, ShieldCheck, Zap } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

export interface ActivityLogItem {
    id: string;
    timestamp: Date;
    agent: string;
    status: "running" | "complete";
    message: string;
}

interface AgentProgressProps {
    activityLog: ActivityLogItem[];
    currentAgent: string | null;
}

const AGENT_CONFIG: Record<string, { icon: React.ElementType; label: string; color: string; runningMessage: string }> = {
    planning: {
        icon: Zap,
        label: "Planner",
        color: "text-violet-500",
        runningMessage: "Analyzing query & planning strategy...",
    },
    retrieval: {
        icon: FileText,
        label: "Retrieval",
        color: "text-sky-500",
        runningMessage: "Querying internal knowledge base...",
    },
    web_search: {
        icon: Globe,
        label: "Web Search",
        color: "text-teal-500",
        runningMessage: "Searching external sources...",
    },
    synthesis: {
        icon: Sparkles,
        label: "Synthesis",
        color: "text-lime-600",
        runningMessage: "Drafting response...",
    },
    critic: {
        icon: ShieldCheck,
        label: "Verification",
        color: "text-amber-500",
        runningMessage: "Verifying claims and citations...",
    },
};

function formatRelativeTime(date: Date, referenceDate: Date): string {
    const diffMs = date.getTime() - referenceDate.getTime();
    const diffSec = Math.max(0, diffMs / 1000);
    if (diffSec < 60) {
        return `${diffSec.toFixed(1)}s`;
    }
    const diffMin = Math.floor(diffSec / 60);
    const remainingSec = (diffSec % 60).toFixed(0);
    return `${diffMin}m ${remainingSec}s`;
}

export function AgentProgress({ activityLog, currentAgent }: AgentProgressProps) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const startTime = activityLog.length > 0 ? activityLog[0].timestamp : new Date();

    // Auto-scroll to bottom when new items arrive
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [activityLog, currentAgent]);

    return (
        <div className="bg-white/90 backdrop-blur-sm rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 bg-slate-50/50">
                <div className="flex items-center gap-2">
                    <Search className="h-4 w-4 text-emerald-500" />
                    <span className="text-sm font-medium text-slate-700">Research Activity</span>
                    {(activityLog.length > 0 || currentAgent) && (
                        <span className="ml-auto text-xs text-slate-400">
                            {formatRelativeTime(new Date(), startTime)} elapsed
                        </span>
                    )}
                </div>
            </div>

            <ScrollArea className="max-h-48">
                <div ref={scrollRef} className="p-3 space-y-2">
                    {activityLog.length === 0 && !currentAgent && (
                        <div className="flex items-center gap-2 text-sm text-slate-400 py-2">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span>Initializing research agents...</span>
                        </div>
                    )}

                    {/* Completed items */}
                    {activityLog.map((item) => {
                        const config = AGENT_CONFIG[item.agent] || {
                            icon: Zap,
                            label: item.agent,
                            color: "text-slate-500",
                            runningMessage: "Processing...",
                        };
                        const Icon = config.icon;

                        return (
                            <div
                                key={item.id}
                                className="flex items-start gap-3 text-sm animate-in fade-in slide-in-from-bottom-2 duration-300"
                            >
                                <div className="flex items-center justify-center w-6 h-6 rounded-full bg-emerald-100 shrink-0 mt-0.5">
                                    <Check className="h-3.5 w-3.5 text-emerald-600" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <Icon className={`h-4 w-4 ${config.color}`} />
                                        <span className="font-medium text-slate-700">{config.label}</span>
                                        <span className="text-slate-400">completed</span>
                                    </div>
                                    <p className="text-xs text-slate-500 mt-0.5 truncate">
                                        {item.message}
                                    </p>
                                </div>
                                <span className="text-xs text-slate-400 tabular-nums shrink-0">
                                    {formatRelativeTime(item.timestamp, startTime)}
                                </span>
                            </div>
                        );
                    })}

                    {/* Currently running agent */}
                    {currentAgent && (
                        <div className="flex items-start gap-3 text-sm animate-in fade-in slide-in-from-bottom-2 duration-300">
                            <div className="flex items-center justify-center w-6 h-6 rounded-full bg-sky-100 shrink-0 mt-0.5">
                                <Loader2 className="h-3.5 w-3.5 text-sky-600 animate-spin" />
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                    {(() => {
                                        const config = AGENT_CONFIG[currentAgent] || {
                                            icon: Zap,
                                            label: currentAgent,
                                            color: "text-slate-500",
                                            runningMessage: "Processing...",
                                        };
                                        const Icon = config.icon;
                                        return (
                                            <>
                                                <Icon className={`h-4 w-4 ${config.color}`} />
                                                <span className="font-medium text-slate-700">{config.label}</span>
                                                <span className="text-sky-500">running</span>
                                            </>
                                        );
                                    })()}
                                </div>
                                <p className="text-xs text-slate-500 mt-0.5">
                                    {AGENT_CONFIG[currentAgent]?.runningMessage || "Processing..."}
                                </p>
                            </div>
                            <span className="text-xs text-slate-400 tabular-nums shrink-0">
                                now
                            </span>
                        </div>
                    )}
                </div>
            </ScrollArea>
        </div>
    );
}
