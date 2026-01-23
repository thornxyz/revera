"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getTimeline, AgentTimeline } from "@/lib/api";

interface AgentTimelinePanelProps {
    sessionId: string | null;
}

const agentIcons: Record<string, string> = {
    planner: "🎯",
    retrieval: "📚",
    web_search: "🌐",
    synthesis: "✍️",
    critic: "🔍",
};

const agentColors: Record<string, string> = {
    planner: "border-l-emerald-500",
    retrieval: "border-l-sky-500",
    web_search: "border-l-teal-500",
    synthesis: "border-l-lime-500",
    critic: "border-l-amber-500",
};

export function AgentTimelinePanel({ sessionId }: AgentTimelinePanelProps) {
    const [timeline, setTimeline] = useState<AgentTimeline | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        if (!sessionId) {
            setTimeline(null);
            return;
        }

        const fetchTimeline = async () => {
            setIsLoading(true);
            try {
                const data = await getTimeline(sessionId);
                setTimeline(data);
            } catch (err) {
                console.error("Failed to fetch timeline:", err);
            } finally {
                setIsLoading(false);
            }
        };

        fetchTimeline();
    }, [sessionId]);

    if (!sessionId) {
        return (
            <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                Run a query to see agent activity
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="animate-pulse text-slate-500">Loading timeline...</div>
            </div>
        );
    }

    if (!timeline?.timeline.length) {
        return (
            <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                No agent activity recorded
            </div>
        );
    }

    const totalLatency = timeline.timeline.reduce(
        (sum, step) => sum + step.latency_ms,
        0
    );

    return (
        <ScrollArea className="h-full">
            <div className="p-4 space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-4">
                    <span>Agent Execution Timeline</span>
                    <span>Total: {totalLatency}ms</span>
                </div>

                {timeline.timeline.map((step, index) => (
                    <Card
                        key={index}
                        className={`bg-white/85 border-slate-200 border-l-4 ${agentColors[step.agent] || "border-l-slate-300"
                            }`}
                    >
                        <CardHeader className="py-2 px-3">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <span className="text-lg">
                                        {agentIcons[step.agent] || "⚙️"}
                                    </span>
                                    <CardTitle className="text-sm font-medium capitalize">
                                        {step.agent.replace("_", " ")}
                                    </CardTitle>
                                </div>
                                <span className="text-xs text-slate-500">
                                    {step.latency_ms}ms
                                </span>
                            </div>
                        </CardHeader>
                        <CardContent className="py-2 px-3">
                            <details className="text-xs">
                                <summary className="cursor-pointer text-slate-500 hover:text-slate-700">
                                    View details
                                </summary>
                                <pre className="mt-2 p-2 bg-slate-50 rounded overflow-x-auto text-slate-600 border border-slate-200">
                                    {JSON.stringify(step.events, null, 2).slice(0, 500)}
                                </pre>
                            </details>
                        </CardContent>
                    </Card>
                ))}

                {/* Latency visualization */}
                <div className="mt-4 pt-4 border-t border-slate-200">
                    <div className="text-xs text-slate-500 mb-2">Latency Breakdown</div>
                    <div className="flex h-4 rounded overflow-hidden">
                        {timeline.timeline.map((step, index) => {
                            const width = (step.latency_ms / totalLatency) * 100;
                            const colors: Record<string, string> = {
                                planner: "bg-emerald-500",
                                retrieval: "bg-sky-500",
                                web_search: "bg-teal-500",
                                synthesis: "bg-lime-500",
                                critic: "bg-amber-500",
                            };
                            return (
                                <div
                                    key={index}
                                    className={`${colors[step.agent] || "bg-slate-400"}`}
                                    style={{ width: `${width}%` }}
                                    title={`${step.agent}: ${step.latency_ms}ms`}
                                />
                            );
                        })}
                    </div>
                    <div className="flex flex-wrap gap-2 mt-2">
                        {timeline.timeline.map((step, index) => (
                            <div key={index} className="flex items-center gap-1 text-xs">
                                <div
                                    className={`w-2 h-2 rounded-full ${{
                                            planner: "bg-emerald-500",
                                            retrieval: "bg-sky-500",
                                            web_search: "bg-teal-500",
                                            synthesis: "bg-lime-500",
                                            critic: "bg-amber-500",
                                        }[step.agent] || "bg-slate-400"
                                        }`}
                                />
                                <span className="text-slate-500 capitalize">
                                    {step.agent.replace("_", " ")}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </ScrollArea>
    );
}
