"use client";

import { Loader2, Send, Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatInputAreaProps {
  query: string;
  setQuery: (value: string) => void;
  isLoading: boolean;
  onSubmit: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onUploadClick: () => void;
  currentChatId: string | null;
}

export function ChatInputArea({
  query,
  setQuery,
  isLoading,
  onSubmit,
  onKeyDown,
  onUploadClick,
  currentChatId,
}: ChatInputAreaProps) {
  return (
    <div className="px-4 sm:px-6 py-3 sm:py-4 bg-transparent shrink-0">
      <div className="max-w-4xl mx-auto w-full">
        <div
          className={cn(
            "input-pill-container transition-all duration-500",
            "glass-morphism bg-white/70 ring-1 ring-slate-200/50",
            "premium-shadow"
          )}
        >
          <div className="flex items-center gap-1 pl-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={onUploadClick}
              className="h-10 w-10 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100/50 transition-all duration-300"
              title="Upload Documents"
            >
              <Upload className="h-5 w-5" />
            </Button>
          </div>

          <div className="flex-1 relative">
            <Textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={
                currentChatId
                  ? "Continue the conversation..."
                  : "Ask a research question..."
              }
              className="h-11 min-h-11 max-h-35 bg-transparent border-0 ring-0 focus-visible:ring-0 focus-visible:ring-offset-0 px-2 py-3 text-sm resize-none"
              disabled={isLoading}
            />
          </div>

          <div className="pr-1.5 flex items-center">
            <Button
              size="icon"
              onClick={onSubmit}
              disabled={isLoading || !query.trim()}
              className="h-9 w-9 rounded-xl transition-all duration-300 shadow-sm bg-slate-900 hover:bg-slate-800 text-white"
            >
              {isLoading ? (
                <Loader2 className="h-4.5 w-4.5 animate-spin" />
              ) : (
                <Send className="h-4.5 w-4.5" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
