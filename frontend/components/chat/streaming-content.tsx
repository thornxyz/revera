"use client";

import { useRef } from "react";
import { Brain, ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AgentProgress } from "@/components/agent-progress";
import { StreamMarkdown } from "@/components/stream-markdown";
import { ActivityLogItem } from "@/components/agent-progress";

interface StreamingContentProps {
  activityLog: ActivityLogItem[];
  currentAgent: string | null;
  streamingThoughts: string;
  streamingAnswer: string;
  isReasoningExpanded: boolean;
  toggleReasoningExpanded: () => void;
  thinkingBoxRef: React.RefObject<HTMLDivElement | null>;
}

export function StreamingContent({
  activityLog,
  currentAgent,
  streamingThoughts,
  streamingAnswer,
  isReasoningExpanded,
  toggleReasoningExpanded,
  thinkingBoxRef,
}: StreamingContentProps) {
  return (
    <div className="space-y-6 px-6 py-4">
      {/* Agent Progress */}
      <AgentProgress activityLog={activityLog} currentAgent={currentAgent} />

      {/* Reasoning/Thoughts */}
      {streamingThoughts && (
        <div className="bg-slate-50/80 border border-slate-200 backdrop-blur-sm rounded-xl overflow-hidden">
          <button
            onClick={toggleReasoningExpanded}
            className="w-full px-4 py-3 bg-slate-100/50 border-b border-slate-200/50 flex items-center justify-between hover:bg-slate-100 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-violet-500" />
              <span className="text-sm font-medium text-slate-600">
                Internal Monologue
              </span>
              <span className="text-xs text-slate-400">
                (Chain of Thought)
              </span>
            </div>
            {isReasoningExpanded ? (
              <ChevronUp className="h-4 w-4 text-slate-400" />
            ) : (
              <ChevronDown className="h-4 w-4 text-slate-400" />
            )}
          </button>
          {isReasoningExpanded && (
            <div ref={thinkingBoxRef} className="p-4 max-h-60 overflow-y-auto reasoning-box">
              <StreamMarkdown
                content={streamingThoughts}
                isStreaming={true}
                className="text-xs text-slate-600 **:text-xs [&_p]:leading-relaxed [&_code]:text-[10px]"
              />
            </div>
          )}
        </div>
      )}

      {/* Streaming Answer */}
      {streamingAnswer && (
        <Card className="bg-white/90 border-slate-200/80 backdrop-blur-sm shadow-lg">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="h-8 w-8 rounded-full bg-emerald-100 flex items-center justify-center">
                <Sparkles className="h-4 w-4 text-emerald-600" />
              </div>
              <span className="text-sm font-medium text-slate-900">
                Assistant
              </span>
              <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">
                Streaming...
              </Badge>
            </div>
            <StreamMarkdown
              content={streamingAnswer}
              isStreaming={true}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
