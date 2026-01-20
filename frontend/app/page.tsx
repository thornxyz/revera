"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { research, ResearchResponse, Source } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { LoginPage } from "@/components/login-page";

export default function ResearchPage() {
  const { user, loading, signOut } = useAuth();
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSources, setShowSources] = useState(false);

  // Show loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-violet-500"></div>
      </div>
    );
  }

  // Show login page if not authenticated
  if (!user) {
    return <LoginPage />;
  }

  const handleSubmit = async () => {
    if (!query.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await research(query, true);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex h-screen bg-neutral-950 text-neutral-50">
      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="border-b border-neutral-800 px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent">
              Revera
            </h1>
            <p className="text-sm text-neutral-400">
              Multi-Agent Research Tool
            </p>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-neutral-400">{user.email}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={signOut}
              className="text-neutral-400 hover:text-neutral-200"
            >
              Sign Out
            </Button>
          </div>
        </header>

        {/* Research Results */}
        <ScrollArea className="flex-1 p-6">
          {error && (
            <Card className="mb-4 border-red-900 bg-red-950/20">
              <CardContent className="pt-4">
                <p className="text-red-400">{error}</p>
              </CardContent>
            </Card>
          )}

          {result && (
            <div className="space-y-4 max-w-4xl mx-auto">
              {/* Query */}
              <div className="text-neutral-400 text-sm">
                Query: {result.query}
              </div>

              {/* Answer Card */}
              <Card className="bg-neutral-900 border-neutral-800">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-lg">Research Result</CardTitle>
                    <ConfidenceBadge confidence={result.confidence} />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="prose prose-invert prose-sm max-w-none">
                    <p className="whitespace-pre-wrap leading-relaxed">
                      {result.answer}
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Verification Card */}
              {result.verification && (
                <Card className="bg-neutral-900 border-neutral-800">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-neutral-300">
                      Verification
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-neutral-400">
                      {result.verification.overall_assessment}
                    </p>
                    {result.verification.unsupported_claims?.length > 0 && (
                      <div className="mt-2 p-2 rounded bg-amber-950/30 border border-amber-900/50">
                        <p className="text-xs font-medium text-amber-400 mb-1">
                          Unsupported Claims:
                        </p>
                        <ul className="text-xs text-amber-300/80 space-y-1">
                          {result.verification.unsupported_claims.map(
                            (claim, i) => (
                              <li key={i}>• {claim.claim}</li>
                            )
                          )}
                        </ul>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Sources Toggle */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowSources(!showSources)}
                className="text-neutral-400 hover:text-neutral-200"
              >
                {showSources ? "Hide" : "Show"} Sources ({result.sources.length}
                )
              </Button>

              {/* Sources List */}
              {showSources && (
                <div className="space-y-2">
                  {result.sources.map((source, i) => (
                    <SourceCard key={i} source={source} index={i + 1} />
                  ))}
                </div>
              )}

              {/* Metadata */}
              <div className="text-xs text-neutral-500 flex gap-4">
                <span>Session: {result.session_id.slice(0, 8)}...</span>
                <span>Latency: {result.total_latency_ms}ms</span>
              </div>
            </div>
          )}

          {!result && !isLoading && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="text-6xl mb-4">🔬</div>
              <h2 className="text-xl font-semibold text-neutral-300 mb-2">
                Start Your Research
              </h2>
              <p className="text-neutral-500 max-w-md">
                Ask a question to search your documents and the web. Get
                verified, cited answers with transparency.
              </p>
            </div>
          )}

          {isLoading && (
            <div className="flex flex-col items-center justify-center h-full">
              <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-violet-500 mb-4"></div>
              <p className="text-neutral-400">Researching...</p>
              <p className="text-xs text-neutral-500 mt-1">
                Planning → Retrieving → Synthesizing → Verifying
              </p>
            </div>
          )}
        </ScrollArea>

        {/* Input Area */}
        <div className="border-t border-neutral-800 p-4">
          <div className="max-w-4xl mx-auto flex gap-2">
            <Textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a research question..."
              className="min-h-[60px] max-h-[120px] bg-neutral-900 border-neutral-700 resize-none"
              disabled={isLoading}
            />
            <Button
              onClick={handleSubmit}
              disabled={isLoading || !query.trim()}
              className="bg-violet-600 hover:bg-violet-500 px-6"
            >
              {isLoading ? "..." : "Research"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const colors: Record<string, string> = {
    verified: "bg-green-900/50 text-green-400 border-green-700",
    partial: "bg-amber-900/50 text-amber-400 border-amber-700",
    unverified: "bg-red-900/50 text-red-400 border-red-700",
    unknown: "bg-neutral-800 text-neutral-400 border-neutral-700",
  };

  return (
    <span
      className={`text-xs px-2 py-1 rounded border ${colors[confidence] || colors.unknown}`}
    >
      {confidence}
    </span>
  );
}

function SourceCard({ source, index }: { source: Source; index: number }) {
  return (
    <Card className="bg-neutral-900/50 border-neutral-800">
      <CardContent className="p-3">
        <div className="flex items-start gap-3">
          <span className="text-xs font-mono bg-neutral-800 px-2 py-1 rounded">
            {index}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span
                className={`text-xs px-1.5 py-0.5 rounded ${source.type === "internal"
                  ? "bg-blue-900/50 text-blue-400"
                  : "bg-purple-900/50 text-purple-400"
                  }`}
              >
                {source.type}
              </span>
              {source.url && (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-violet-400 hover:underline truncate"
                >
                  {source.title || source.url}
                </a>
              )}
            </div>
            <p className="text-xs text-neutral-400 line-clamp-2">
              {source.content.slice(0, 200)}...
            </p>
          </div>
          <span className="text-xs text-neutral-500">
            {(source.score * 100).toFixed(0)}%
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
