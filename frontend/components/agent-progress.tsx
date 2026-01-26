"use client";

import { Check, Loader2 } from "lucide-react";

const AGENT_STEPS = [
    { id: "planning", label: "Planning", icon: "📋" },
    { id: "retrieval", label: "Retrieval", icon: "📚" },
    { id: "web_search", label: "Web Search", icon: "🌐" },
    { id: "synthesis", label: "Synthesis", icon: "✨" },
    { id: "critic", label: "Verification", icon: "✅" },
];

interface AgentProgressProps {
    completedAgents: string[];
    currentAgent: string | null;
}

export function AgentProgress({ completedAgents, currentAgent }: AgentProgressProps) {
    return (
        <div className="bg-white/90 backdrop-blur-sm rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="flex items-center justify-between gap-2">
                {AGENT_STEPS.map((step, index) => {
                    const isComplete = completedAgents.includes(step.id);
                    const isCurrent = currentAgent === step.id;
                    const isPending = !isComplete && !isCurrent;

                    return (
                        <div key={step.id} className="flex items-center flex-1">
                            {/* Step indicator */}
                            <div className="flex flex-col items-center gap-1 flex-1">
                                <div
                                    className={`
                                        w-10 h-10 rounded-full flex items-center justify-center text-lg
                                        transition-all duration-300
                                        ${isComplete ? "bg-emerald-100 text-emerald-600 ring-2 ring-emerald-500" : ""}
                                        ${isCurrent ? "bg-sky-100 text-sky-600 ring-2 ring-sky-500 animate-pulse" : ""}
                                        ${isPending ? "bg-slate-100 text-slate-400" : ""}
                                    `}
                                >
                                    {isComplete ? (
                                        <Check className="w-5 h-5 text-emerald-600" />
                                    ) : isCurrent ? (
                                        <Loader2 className="w-5 h-5 animate-spin" />
                                    ) : (
                                        <span>{step.icon}</span>
                                    )}
                                </div>
                                <span
                                    className={`
                                        text-xs font-medium transition-colors
                                        ${isComplete ? "text-emerald-600" : ""}
                                        ${isCurrent ? "text-sky-600" : ""}
                                        ${isPending ? "text-slate-400" : ""}
                                    `}
                                >
                                    {step.label}
                                </span>
                            </div>

                            {/* Connector line */}
                            {index < AGENT_STEPS.length - 1 && (
                                <div
                                    className={`
                                        h-0.5 flex-1 mx-2 transition-colors duration-300
                                        ${isComplete ? "bg-emerald-400" : "bg-slate-200"}
                                    `}
                                />
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
