"use client";

import { useState } from "react";
import { Brain, ChevronDown, ChevronRight, Activity } from "lucide-react";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { AgentStep } from "@/lib/api";
import { cn } from "@/lib/utils";
import { StreamMarkdown } from "./stream-markdown";

interface MessageThinkingProps {
    thinking?: string;
    timeline?: AgentStep[];
    isStreaming?: boolean;
}

const agentColors: Record<string, string> = {
    planner: "bg-emerald-500",
    retrieval: "bg-sky-500",
    web_search: "bg-teal-500",
    synthesis: "bg-lime-500",
    critic: "bg-amber-500",
};

export function MessageThinking({ thinking, timeline, isStreaming }: MessageThinkingProps) {
    const [isOpen, setIsOpen] = useState(false);

    if (!thinking && (!timeline || timeline.length === 0)) {
        return null;
    }

    const totalLatency = timeline?.reduce((sum, step) => sum + step.latency_ms, 0) || 0;



    return (
        <div className="w-full">
            <Collapsible
                open={isOpen}
                onOpenChange={setIsOpen}
                className="w-full mb-2"
            >
                <CollapsibleTrigger asChild>
                    <div className="flex items-center gap-2 px-3 py-2 text-xs text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-md cursor-pointer transition-colors w-fit">
                        {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                        <Brain className="w-3 h-3" />
                        <span className="font-medium">Thinking Process</span>
                        {timeline && timeline.length > 0 && (
                            <span className="text-slate-400">
                                • {timeline.length} steps • {Math.round(totalLatency / 1000)}s
                            </span>
                        )}
                    </div>
                </CollapsibleTrigger>

                <CollapsibleContent>
                    <div className="pl-4 pr-2 py-2 space-y-4">
                        {/* Thinking Text */}
                        {thinking && (
                            <div className="text-sm text-slate-600 bg-slate-50/50 p-3 rounded-lg border border-slate-100">
                                <div className="uppercase text-[10px] font-semibold text-slate-400 mb-1 tracking-wider">
                                    Reasoning
                                </div>
                                <div className="prose prose-sm prose-slate max-w-none text-slate-600">
                                    <StreamMarkdown content={thinking} />
                                </div>
                            </div>
                        )}

                        {/* Timeline Visualization */}
                        {timeline && timeline.length > 0 && (
                            <div className="space-y-2">
                                <div className="uppercase text-[10px] font-semibold text-slate-400 tracking-wider flex items-center gap-2">
                                    <Activity className="w-3 h-3" />
                                    Execution Timeline
                                </div>

                                {/* Bar Chart */}
                                <div className="flex h-2 rounded-full overflow-hidden bg-slate-100 w-full">
                                    {timeline.map((step, idx) => (
                                        <div
                                            key={idx}
                                            className={cn("h-full", agentColors[step.agent] || "bg-slate-400")}
                                            style={{ width: `${(step.latency_ms / totalLatency) * 100}%` }}
                                            title={`${step.agent}: ${step.latency_ms}ms`}
                                        />
                                    ))}
                                </div>

                                {/* Legend / Steps */}
                                <div className="flex flex-wrap gap-2 mt-2">
                                    {timeline.map((step, idx) => (
                                        <div key={idx} className="flex items-center gap-1.5 px-2 py-1 bg-slate-50 rounded border border-slate-100 text-[10px]">
                                            <div className={cn("w-1.5 h-1.5 rounded-full", agentColors[step.agent] || "bg-slate-400")} />
                                            <span className="font-medium capitalize text-slate-700">
                                                {(step.agent || "unknown").replace("_", " ")}
                                            </span>
                                            <span className="text-slate-400 border-l border-slate-200 pl-1.5 ml-0.5">
                                                {step.latency_ms}ms
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </CollapsibleContent>
            </Collapsible>
        </div>
    );
}
