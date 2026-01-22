"use client";

import { useState } from "react";
import { Upload, Sparkles, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { research, ResearchResponse, Source } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { LoginPage } from "@/components/login-page";
import { DocumentsPanel } from "@/components/documents-panel";
import { UploadDialog } from "@/components/upload-dialog";

export default function ResearchPage() {
  const { user, loading, signOut } = useAuth();
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);

  // Show loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-neutral-950 via-neutral-900 to-neutral-950 flex items-center justify-center">
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
    <div className="flex h-screen bg-gradient-to-br from-neutral-950 via-neutral-900 to-neutral-950 text-neutral-50">
      {/* Sidebar with Documents */}
      <div className="w-80 border-r border-neutral-800/50 flex flex-col backdrop-blur-sm">
        <div className="p-4 border-b border-neutral-800/50">
          <Button
            onClick={() => setUploadDialogOpen(true)}
            className="w-full bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 shadow-lg shadow-violet-500/20"
          >
            <Upload className="h-4 w-4 mr-2" />
            Upload Document
          </Button>
        </div>
        <div className="flex-1 overflow-hidden p-4">
          <DocumentsPanel />
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="border-b border-neutral-800/50 px-6 py-4 flex items-center justify-between backdrop-blur-sm bg-neutral-900/30">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-violet-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent flex items-center gap-2">
              <Sparkles className="h-6 w-6 text-violet-400" />
              Revera
            </h1>
            <p className="text-sm text-neutral-400 mt-0.5">
              AI-Powered Research Assistant
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-xs text-neutral-500">Signed in as</p>
              <p className="text-sm text-neutral-300">{user.email}</p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={signOut}
              className="text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800"
            >
              Sign Out
            </Button>
          </div>
        </header>

        {/* Research Results */}
        <ScrollArea className="flex-1 p-6">
          {error && (
            <Card className="mb-4 border-red-900/50 bg-red-950/30 backdrop-blur-sm">
              <CardContent className="pt-4">
                <p className="text-red-400">{error}</p>
              </CardContent>
            </Card>
          )}

          {result && (
            <div className="space-y-6 max-w-5xl mx-auto">
              {/* Query */}
              <div className="flex items-start gap-3 text-neutral-400 text-sm bg-neutral-900/50 backdrop-blur-sm rounded-lg p-4 border border-neutral-800/50">
                <Sparkles className="h-4 w-4 text-violet-400 mt-0.5 flex-shrink-0" />
                <div>
                  <span className="text-neutral-500 text-xs">Query:</span>
                  <p className="text-neutral-200 mt-1">{result.query}</p>
                </div>
              </div>

              {/* Answer Card */}
              <Card className="bg-gradient-to-br from-neutral-900/90 to-neutral-900/50 border-neutral-800/50 backdrop-blur-sm shadow-xl">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-xl font-semibold">Research Result</CardTitle>
                    <ConfidenceBadge confidence={result.confidence} />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="prose prose-invert prose-sm max-w-none">
                    <p className="whitespace-pre-wrap leading-relaxed text-neutral-200">
                      {result.answer}
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Verification Card */}
              {result.verification && (
                <Card className="bg-neutral-900/70 border-neutral-800/50 backdrop-blur-sm">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium text-neutral-300 flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full bg-violet-400"></div>
                      Verification
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-neutral-300 leading-relaxed">
                      {result.verification.overall_assessment}
                    </p>
                    {result.verification.unsupported_claims?.length > 0 && (
                      <div className="mt-3 p-3 rounded-lg bg-amber-950/40 border border-amber-900/50">
                        <p className="text-xs font-medium text-amber-400 mb-2">
                          ⚠ Unsupported Claims:
                        </p>
                        <ul className="text-xs text-amber-300/90 space-y-1.5">
                          {result.verification.unsupported_claims.map(
                            (claim, i) => (
                              <li key={i} className="pl-2 border-l-2 border-amber-700">
                                {claim.claim}
                              </li>
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
                className="text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50"
              >
                {showSources ? "Hide" : "Show"} Sources
                <Badge variant="secondary" className="ml-2 bg-neutral-800">
                  {result.sources.length}
                </Badge>
              </Button>

              {/* Sources List */}
              {showSources && (
                <div className="space-y-3">
                  {result.sources.map((source, i) => (
                    <SourceCard key={i} source={source} index={i + 1} />
                  ))}
                </div>
              )}

              {/* Metadata */}
              <div className="flex items-center gap-6 text-xs text-neutral-500 px-4">
                <span className="flex items-center gap-1">
                  <div className="h-1.5 w-1.5 rounded-full bg-violet-500"></div>
                  Session: {result.session_id.slice(0, 8)}...
                </span>
                <span className="flex items-center gap-1">
                  <div className="h-1.5 w-1.5 rounded-full bg-cyan-500"></div>
                  Latency: {result.total_latency_ms}ms
                </span>
              </div>
            </div>
          )}

          {!result && !isLoading && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="relative">
                <div className="absolute inset-0 bg-gradient-to-r from-violet-600 to-cyan-600 blur-3xl opacity-20 rounded-full"></div>
                <div className="relative text-8xl mb-6">🔬</div>
              </div>
              <h2 className="text-2xl font-semibold text-neutral-200 mb-3">
                Start Your Research
              </h2>
              <p className="text-neutral-400 max-w-md leading-relaxed">
                Ask a question to search your documents and the web. Get
                verified, cited answers with full transparency.
              </p>
            </div>
          )}

          {isLoading && (
            <div className="flex flex-col items-center justify-center h-full">
              <div className="relative mb-6">
                <div className="absolute inset-0 bg-violet-600 blur-2xl opacity-30 rounded-full"></div>
                <Loader2 className="relative h-16 w-16 text-violet-400 animate-spin" />
              </div>
              <p className="text-neutral-300 text-lg mb-2">Researching...</p>
              <p className="text-sm text-neutral-500">
                Planning → Retrieving → Synthesizing → Verifying
              </p>
            </div>
          )}
        </ScrollArea>

        {/* Input Area */}
        <div className="border-t border-neutral-800/50 p-4 backdrop-blur-sm bg-neutral-900/30">
          <div className="max-w-5xl mx-auto">
            <div className="flex gap-3">
              <Textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a research question..."
                className="min-h-[70px] max-h-[140px] bg-neutral-900/70 border-neutral-700/50 resize-none text-base backdrop-blur-sm focus:border-violet-500/50 transition-colors"
                disabled={isLoading}
              />
              <Button
                onClick={handleSubmit}
                disabled={isLoading || !query.trim()}
                className="bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 px-8 shadow-lg shadow-violet-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : "Research"}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Upload Dialog */}
      <UploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onUploadSuccess={() => {
          // Refresh documents if needed
        }}
      />
    </div>
  );
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const config: Record<string, { bg: string; text: string; border: string; label: string }> = {
    verified: {
      bg: "bg-green-900/40",
      text: "text-green-400",
      border: "border-green-700/50",
      label: "✓ Verified"
    },
    partial: {
      bg: "bg-amber-900/40",
      text: "text-amber-400",
      border: "border-amber-700/50",
      label: "⚠ Partial"
    },
    unverified: {
      bg: "bg-red-900/40",
      text: "text-red-400",
      border: "border-red-700/50",
      label: "✗ Unverified"
    },
    unknown: {
      bg: "bg-neutral-800/50",
      text: "text-neutral-400",
      border: "border-neutral-700/50",
      label: "Unknown"
    },
  };

  const style = config[confidence] || config.unknown;

  return (
    <Badge
      className={`${style.bg} ${style.text} border ${style.border} shadow-sm`}
    >
      {style.label}
    </Badge>
  );
}

function SourceCard({ source, index }: { source: Source; index: number }) {
  return (
    <Card className="bg-neutral-900/60 border-neutral-800/50 backdrop-blur-sm hover:border-neutral-700/50 transition-all">
      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          <div className="flex-shrink-0 flex flex-col items-center gap-1">
            <span className="text-xs font-mono bg-gradient-to-br from-violet-600 to-purple-600 text-white px-2.5 py-1 rounded-md shadow-sm">
              {index}
            </span>
            <span className="text-[10px] text-neutral-500">
              {(source.score * 100).toFixed(0)}%
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <Badge
                className={`text-[10px] px-2 py-0.5 ${source.type === "internal"
                  ? "bg-blue-900/50 text-blue-400 border-blue-700/50"
                  : "bg-purple-900/50 text-purple-400 border-purple-700/50"
                  }`}
              >
                {source.type === "internal" ? "📄 Internal" : "🌐 Web"}
              </Badge>
              {source.url && (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-violet-400 hover:text-violet-300 hover:underline truncate transition-colors"
                >
                  {source.title || source.url}
                </a>
              )}
            </div>
            <p className="text-sm text-neutral-300 line-clamp-3 leading-relaxed">
              {source.content.slice(0, 250)}
              {source.content.length > 250 && "..."}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
