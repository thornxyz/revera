"use client";

import { useState, useRef } from "react";
import { Upload, Sparkles, Loader2, Brain, ChevronDown, ChevronUp, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { DocumentsPanel } from "@/components/documents-panel";
import { UploadDialog } from "@/components/upload-dialog";
import { SessionsSidebar } from "@/components/sessions-sidebar";
import { AgentTimelinePanel } from "@/components/agent-timeline";
import { getSession, researchStream, ResearchResponse, Source } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { ResizableLayout } from "@/components/resizable-layout";
import { LoginPage } from "@/components/login-page";
import { StreamMarkdown } from "@/components/stream-markdown";
import { AgentProgress, ActivityLogItem } from "@/components/agent-progress";

export default function ResearchPage() {
  const { user, loading, signOut } = useAuth();
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);

  // Multiple Chats State
  const [activeTab, setActiveTab] = useState<"chat" | "documents" | "timeline">(
    "chat"
  );
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [documentsRefreshToken, setDocumentsRefreshToken] = useState(0);

  // Streaming State
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamingThoughts, setStreamingThoughts] = useState("");
  const [currentAgent, setCurrentAgent] = useState<string | null>(null);
  const [streamingSources, setStreamingSources] = useState<Source[]>([]);
  const [activityLog, setActivityLog] = useState<ActivityLogItem[]>([]);
  const [isReasoningExpanded, setIsReasoningExpanded] = useState(true);
  const streamStartTimeRef = useRef<Date>(new Date());
  const activityLogCounterRef = useRef<number>(0);

  // Show loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-linear-to-br from-slate-50 via-white to-emerald-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-emerald-500"></div>
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
    setIsStreaming(true);
    setStreamingAnswer("");
    setStreamingThoughts("");
    setCurrentAgent(null);
    setStreamingSources([]);
    setActivityLog([]);
    setIsReasoningExpanded(true);
    streamStartTimeRef.current = new Date();
    activityLogCounterRef.current = 0;
    setError(null);
    setResult(null);

    const currentQuery = query;
    setQuery("");

    try {
      await researchStream(
        currentQuery,
        true,
        selectedDocumentIds.length ? selectedDocumentIds : undefined,
        {
          onAgentStatus: (node, status) => {
            if (status === "complete") {
              setCurrentAgent(null);
              // Add to activity log
              const agentMessages: Record<string, string> = {
                planning: "Strategy determined",
                retrieval: "Internal documents searched",
                web_search: "External sources fetched",
                synthesis: "Response drafted",
                critic: "Claims verified",
              };
              setActivityLog((prev) => [
                ...prev,
                {
                  id: `${node}-${activityLogCounterRef.current++}`,
                  timestamp: new Date(),
                  agent: node,
                  status: "complete",
                  message: agentMessages[node] || "Step completed",
                },
              ]);
            } else {
              setCurrentAgent(node);
            }
          },
          onAnswerChunk: (content) => {
            setStreamingAnswer((prev) => prev + content);
          },
          onThoughtChunk: (content) => {
            setStreamingThoughts((prev) => prev + content);
          },
          onSources: (sources) => {
            setStreamingSources((prev) => [...prev, ...sources]);
          },
          onComplete: (data) => {
            // Use streamingSources as fallback if data.sources is empty
            const finalSources = (data.sources && data.sources.length > 0)
              ? data.sources
              : streamingSources;

            setResult({
              session_id: data.session_id,
              query: currentQuery,
              answer: streamingAnswer, // Use the accumulated streaming answer
              sources: finalSources,
              verification: data.verification || {
                verification_status: data.confidence || "unknown",
                confidence_score: 0,
                verified_claims: [],
                unsupported_claims: [],
                overall_assessment: "",
              },
              confidence: data.confidence || "unknown",
              total_latency_ms: data.total_latency_ms || 0,
            });
            setCurrentSessionId(data.session_id);
            setIsStreaming(false);
            setIsLoading(false); // Ensure loading state is cleared
          },
          onError: (message) => {
            setError(message);
            setIsStreaming(false);
            setIsLoading(false);
            setCurrentAgent(null);
          },
        }
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research failed");
      setIsStreaming(false);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSessionSelect = async (sessionId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const session = await getSession(sessionId);
      if (session.result) {
        const resolvedQuery = session.result.query?.trim() || session.query;
        const normalizedSources = session.result.sources ?? [];
        const normalizedAnswer = session.result.answer || "";
        setResult({
          ...session.result,
          query: resolvedQuery,
          sources: normalizedSources,
          answer: normalizedAnswer
        });
      }
      setCurrentSessionId(sessionId);
      // Don't set query, as we want to start fresh or just view result
    } catch (err) {
      setError("Failed to load session");
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = () => {
    setResult(null);
    setQuery("");
    setCurrentSessionId(null);
    setError(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const renderAnswerWithSources = (answer: string | undefined) => {
    // Defensive check for undefined or null answer
    if (!answer || typeof answer !== 'string') {
      return <span className="text-slate-500 italic">No answer available</span>;
    }

    // Pattern to match citations like [Source 1], [Source 1, 2], [Source 1, 4, 5], etc.
    const citationPattern =
      /\[(?:source\s*\d+(?:\s*,\s*(?:source\s*)?\d+)*)\]/gi;
    const parts = answer.split(new RegExp(`(${citationPattern.source})`, "gi"));

    return parts.map((part, index) => {
      if (citationPattern.test(part)) {
        // Extract all source numbers from the citation
        // Handles formats like [Source 1], [Source 1, 2], [Source 1, 4, 5]
        const sourceNumbers = part
          .replace(/[\[\]]/g, '') // Remove brackets
          .split(',')
          .map(s => {
            // Extract just the number, handling "Source 1" or just "1"
            const match = s.trim().match(/\d+/);
            return match ? parseInt(match[0]) : null;
          })
          .filter((n): n is number => n !== null);

        return (
          <sup
            key={`source-${index}`}
            className="ml-0.5 text-emerald-600 font-medium cursor-pointer hover:text-emerald-700"
            onClick={() => setShowSources(true)}
            title={`View source${sourceNumbers.length > 1 ? 's' : ''}: ${sourceNumbers.join(', ')}`}
          >
            [{sourceNumbers.join(',')}]
          </sup>
        );
      }

      return <span key={`text-${index}`}>{part}</span>;
    });
  };

  return (
    <div className="flex h-screen bg-linear-to-br from-slate-50 via-white to-emerald-50 text-slate-900">
      <ResizableLayout
        sidebar={
          <div className="h-full flex flex-col overflow-x-auto overflow-y-hidden">
            {/* Sidebar Tabs */}
            <div className="flex border-b border-slate-200/70 bg-white/80">
              <button
                onClick={() => setActiveTab("chat")}
                className={`flex-1 py-3 text-sm font-medium transition-colors ${activeTab === "chat"
                  ? "text-emerald-700 border-b-2 border-emerald-500 bg-emerald-50"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                  }`}
              >
                Chats
              </button>
              <button
                onClick={() => setActiveTab("documents")}
                className={`flex-1 py-3 text-sm font-medium transition-colors ${activeTab === "documents"
                  ? "text-emerald-700 border-b-2 border-emerald-500 bg-emerald-50"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                  }`}
              >
                Documents
              </button>
              <button
                onClick={() => setActiveTab("timeline")}
                className={`flex-1 py-3 text-sm font-medium transition-colors ${activeTab === "timeline"
                  ? "text-emerald-700 border-b-2 border-emerald-500 bg-emerald-50"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                  }`}
              >
                Timeline
              </button>
            </div>

            {/* Sidebar Content */}
            <div className="flex-1 overflow-hidden relative">
              {activeTab === "chat" ? (
                <SessionsSidebar
                  currentSessionId={currentSessionId}
                  onSessionSelect={handleSessionSelect}
                  onNewChat={handleNewChat}
                />
              ) : activeTab === "documents" ? (
                <div className="h-full flex flex-col">
                  <div className="p-4 border-b border-slate-200/70">
                    <Button
                      onClick={() => setUploadDialogOpen(true)}
                      className="w-full bg-linear-to-r from-emerald-500 to-teal-500 hover:from-emerald-500 hover:to-teal-400 shadow-sm shadow-emerald-500/20"
                    >
                      <Upload className="h-4 w-4 mr-2" />
                      Upload Document
                    </Button>
                  </div>
                  <div className="flex-1 overflow-hidden p-4">
                    <DocumentsPanel
                      onDocumentSelect={setSelectedDocumentIds}
                      refreshToken={documentsRefreshToken}
                    />
                  </div>
                </div>
              ) : (
                <div className="h-full flex flex-col">
                  <div className="p-4 border-b border-slate-200/70">
                    <p className="text-sm font-medium text-slate-700">
                      Agent Timeline
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      Track each agent step for the current session.
                    </p>
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <AgentTimelinePanel sessionId={currentSessionId} />
                  </div>
                </div>
              )}
            </div>
          </div>
        }
      >
        {/* Main Content */}
        <div className="flex-1 flex flex-col h-full min-h-0 bg-linear-to-br from-white via-slate-50 to-emerald-50">
          {/* Header */}
          <header className="border-b border-slate-200/70 px-4 sm:px-6 py-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between backdrop-blur-sm bg-white/70">
            <div>
              <h1 className="text-3xl font-bold bg-linear-to-r from-emerald-600 via-teal-500 to-sky-500 bg-clip-text text-transparent flex items-center gap-2">
                <Sparkles className="h-6 w-6 text-emerald-500" />
                Revera
              </h1>
              <p className="text-sm text-slate-500 mt-0.5">
                AI-Powered Research Assistant
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
              <div className="text-left sm:text-right">
                <p className="text-xs text-slate-500">Signed in as</p>
                <p className="text-sm text-slate-700 break-all sm:break-normal">{user.email}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={signOut}
                className="text-slate-500 hover:text-slate-700 hover:bg-slate-100"
              >
                Sign Out
              </Button>
            </div>
          </header>

          {/* Research Results */}
          <ScrollArea className="flex-1 min-h-0 p-4 sm:p-6">
            {error && (
              <Card className="mb-4 border-rose-200 bg-rose-50/80 backdrop-blur-sm">
                <CardContent className="pt-4">
                  <p className="text-rose-600">{error}</p>
                </CardContent>
              </Card>
            )}

            {result && (
              <div className="space-y-6 max-w-5xl mx-auto">
                {/* Query */}
                <div className="flex items-start gap-3 text-slate-500 text-sm bg-white/80 backdrop-blur-sm rounded-lg p-4 border border-slate-200">
                  <Sparkles className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
                  <div>
                    <span className="text-slate-400 text-xs">Query:</span>
                    <p className="text-slate-700 mt-1">{result.query}</p>
                  </div>
                </div>

                {/* Answer Card */}
                <Card className="bg-white/90 border-slate-200/80 backdrop-blur-sm shadow-lg">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-xl font-semibold">Research Result</CardTitle>
                      <ConfidenceBadge confidence={result.confidence} />
                    </div>
                  </CardHeader>
                  <CardContent>
                    <StreamMarkdown
                      content={streamingAnswer || result.answer}
                      isStreaming={false}
                    />
                  </CardContent>
                </Card>

                {/* Verification Card */}
                {result.verification && (
                  <Card className="bg-white/90 border-slate-200/80 backdrop-blur-sm">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-medium text-slate-600 flex items-center gap-2">
                        <div className="h-2 w-2 rounded-full bg-emerald-500"></div>
                        Verification
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm text-slate-600 leading-relaxed">
                        {result.verification.overall_assessment}
                      </p>
                      {result.verification.unsupported_claims?.length > 0 && (
                        <div className="mt-3 p-3 rounded-lg bg-amber-50 border border-amber-200">
                          <p className="text-xs font-medium text-amber-600 mb-2">
                            ⚠ Unsupported Claims:
                          </p>
                          <ul className="text-xs text-amber-700/90 space-y-1.5">
                            {result.verification.unsupported_claims.map(
                              (claim, i) => (
                                <li key={i} className="pl-2 border-l-2 border-amber-300">
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
                  className="text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                >
                  {showSources ? "Hide" : "Show"} Sources
                  <Badge variant="secondary" className="ml-2 bg-slate-100 text-slate-600">
                    {result.sources?.length || 0}
                  </Badge>
                </Button>

                {/* Sources List */}
                {showSources && (
                  <div className="space-y-3">
                    {result.sources?.map((source, i) => (
                      <SourceCard key={i} source={source} index={i + 1} />
                    ))}
                  </div>
                )}

                {/* Metadata */}
                <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 px-4">
                  <span className="flex items-center gap-1">
                    <div className="h-1.5 w-1.5 rounded-full bg-emerald-500"></div>
                    Session: {(result.session_id || currentSessionId)?.slice(0, 8)}...
                  </span>
                  <span className="flex items-center gap-1">
                    <div className="h-1.5 w-1.5 rounded-full bg-sky-500"></div>
                    Latency: {result.total_latency_ms || 0}ms
                  </span>
                </div>
              </div>
            )}

            {!result && !isLoading && !isStreaming && (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="relative">
                  <div className="absolute inset-0 bg-linear-to-r from-emerald-400 to-sky-400 blur-3xl opacity-20 rounded-full"></div>
                  <div className="relative text-7xl sm:text-8xl mb-6">🔬</div>
                </div>
                <h2 className="text-2xl font-semibold text-slate-800 mb-3">
                  Start Your Research
                </h2>
                <p className="text-slate-500 max-w-md leading-relaxed">
                  Ask a question to search your documents and the web. Get
                  verified, cited answers with full transparency.
                </p>
              </div>
            )}

            {/* Streaming Content */}
            {isStreaming && (
              <div className="space-y-6 max-w-5xl mx-auto">
                {/* Agent Progress - Activity Feed */}
                <AgentProgress
                  activityLog={activityLog}
                  currentAgent={currentAgent}
                />

                {/* Collapsible Reasoning/Chain of Thought */}
                {streamingThoughts && (
                  <div className="bg-slate-50/80 border border-slate-200 backdrop-blur-sm rounded-xl overflow-hidden">
                    <button
                      onClick={() => setIsReasoningExpanded(!isReasoningExpanded)}
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
                      <div className="p-4 max-h-60 overflow-y-auto">
                        <p className="text-xs font-mono text-slate-600 whitespace-pre-wrap leading-relaxed">
                          {streamingThoughts}
                          <span className="inline-block w-1.5 h-4 bg-violet-400 animate-pulse ml-0.5 align-middle" />
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* Streaming Answer */}
                {streamingAnswer && (
                  <Card className="bg-white/90 border-slate-200/80 backdrop-blur-sm shadow-lg">
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-xl font-semibold">Research Result</CardTitle>
                        <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">
                          Streaming...
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <StreamMarkdown
                        content={streamingAnswer}
                        isStreaming={true}
                      />
                    </CardContent>
                  </Card>
                )}

                {/* Streaming Sources (show as they arrive) */}
                {streamingSources.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-lg font-semibold text-slate-700 flex items-center gap-2">
                        <FileText className="h-5 w-5 text-emerald-500" />
                        Sources
                        <Badge variant="secondary" className="ml-2 bg-slate-100 text-slate-600">
                          {streamingSources.length}
                        </Badge>
                      </h3>
                    </div>
                    {streamingSources.map((source, i) => (
                      <SourceCard key={i} source={source} index={i + 1} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {isLoading && !isStreaming && (
              <div className="flex flex-col items-center justify-center h-full">
                <div className="relative mb-6">
                  <div className="absolute inset-0 bg-emerald-300 blur-2xl opacity-30 rounded-full"></div>
                  <Loader2 className="relative h-16 w-16 text-emerald-500 animate-spin" />
                </div>
                <p className="text-slate-700 text-lg mb-2">Researching...</p>
                <p className="text-sm text-slate-500">
                  Planning → Retrieving → Synthesizing → Verifying
                </p>
              </div>
            )}
          </ScrollArea>

          {/* Input Area */}
          <div className="border-t border-slate-200/70 p-4 sm:p-5 backdrop-blur-sm bg-white/80">
            <div className="max-w-5xl mx-auto">
              <div className="flex flex-col gap-3 sm:flex-row">
                <Textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a research question..."
                  className="min-h-17.5 max-h-35 bg-white border-slate-200/70 resize-none text-base focus:border-emerald-400/70 focus:ring-emerald-200 transition-colors"
                  disabled={isLoading}
                />
                <Button
                  onClick={handleSubmit}
                  disabled={isLoading || !query.trim()}
                  className="bg-linear-to-r from-emerald-500 to-teal-500 hover:from-emerald-500 hover:to-teal-400 px-8 shadow-sm shadow-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed w-full sm:w-auto"
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
            setDocumentsRefreshToken((prev) => prev + 1);
          }}
        />
      </ResizableLayout>
    </div>
  );
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const config: Record<string, { bg: string; text: string; border: string; label: string }> = {
    verified: {
      bg: "bg-emerald-100",
      text: "text-emerald-700",
      border: "border-emerald-200",
      label: "✓ Verified"
    },
    partial: {
      bg: "bg-amber-100",
      text: "text-amber-700",
      border: "border-amber-200",
      label: "⚠ Partial"
    },
    unverified: {
      bg: "bg-rose-100",
      text: "text-rose-700",
      border: "border-rose-200",
      label: "✗ Unverified"
    },
    unknown: {
      bg: "bg-slate-100",
      text: "text-slate-600",
      border: "border-slate-200",
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
    <Card className="bg-white/80 border-slate-200/80 backdrop-blur-sm hover:border-slate-300 transition-all">
      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          <div className="shrink-0 flex flex-col items-center gap-1">
            <span className="text-xs font-mono bg-linear-to-br from-emerald-500 to-teal-500 text-white px-2.5 py-1 rounded-md shadow-sm">
              {index}
            </span>
            <span className="text-[10px] text-slate-500">
              {(source.score * 100).toFixed(0)}%
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <Badge
                className={`text-[10px] px-2 py-0.5 ${source.type === "internal"
                  ? "bg-sky-100 text-sky-700 border-sky-200"
                  : "bg-emerald-100 text-emerald-700 border-emerald-200"
                  }`}
              >
                {source.type === "internal" ? "📄 Internal" : "🌐 Web"}
              </Badge>
              {source.url && (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-emerald-600 hover:text-emerald-500 hover:underline truncate transition-colors"
                >
                  {source.title || source.url}
                </a>
              )}
            </div>
            <p className="text-sm text-slate-600 line-clamp-3 leading-relaxed">
              {source.content.slice(0, 250)}
              {source.content.length > 250 && "..."}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
