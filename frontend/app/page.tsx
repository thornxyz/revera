"use client";

import { useState, useRef, useEffect } from "react";
import { Upload, Sparkles, Loader2, Brain, ChevronDown, ChevronUp, Send } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { DocumentsPanel } from "@/components/documents-panel";
import { UploadDialog } from "@/components/upload-dialog";
import { ChatsSidebar } from "@/components/chats-sidebar";
import { MessageList } from "@/components/message-list";
import { AgentTimelinePanel } from "@/components/agent-timeline";
import {
  createChat,
  getChatMessages,
  sendChatMessageStream,
  pollVerificationStatus,
  Message,
  Source
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useChatContext } from "@/lib/chat-context";
import { ResizableLayout } from "@/components/resizable-layout";
import { LoginPage } from "@/components/login-page";
import { AgentProgress, ActivityLogItem } from "@/components/agent-progress";

export default function ResearchPage() {
  const { user, loading, signOut } = useAuth();
  const { updateChatTitle } = useChatContext();
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);

  // Chat State
  const [activeTab, setActiveTab] = useState<"chat" | "documents" | "timeline">("chat");
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [documentsRefreshToken, setDocumentsRefreshToken] = useState(0);
  const [chatsRefreshToken, setChatsRefreshToken] = useState(0);

  // Streaming State
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamingThoughts, setStreamingThoughts] = useState("");
  const [currentAgent, setCurrentAgent] = useState<string | null>(null);
  const [streamingSources, setStreamingSources] = useState<Source[]>([]);
  const [activityLog, setActivityLog] = useState<ActivityLogItem[]>([]);
  const [isReasoningExpanded, setIsReasoningExpanded] = useState(true);
  const [currentMessageId, setCurrentMessageId] = useState<string | null>(null);
  const streamStartTimeRef = useRef<Date>(new Date());
  const activityLogCounterRef = useRef<number>(0);
  const streamingEndRef = useRef<HTMLDivElement>(null);
  const userScrolledAwayRef = useRef(false);

  // Track if user has scrolled away during streaming
  useEffect(() => {
    const chatArea = document.querySelector('.flex-1.overflow-y-auto');
    if (!chatArea) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = chatArea;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      userScrolledAwayRef.current = !isNearBottom;
    };

    chatArea.addEventListener('scroll', handleScroll);
    return () => chatArea.removeEventListener('scroll', handleScroll);
  }, []);

  // Auto-scroll during streaming (only if user hasn't scrolled away)
  useEffect(() => {
    if (isStreaming && !userScrolledAwayRef.current && streamingEndRef.current) {
      streamingEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [isStreaming, streamingAnswer, streamingThoughts]);

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

    // Auto-create chat if none selected
    let chatId = currentChatId;
    if (!chatId) {
      try {
        const newChat = await createChat();
        chatId = newChat.id;
        setCurrentChatId(chatId);
        toast.success("New chat created", {
          description: "Ready to start your research",
        });
      } catch (err) {
        setError("Failed to create chat");
        toast.error("Failed to create chat", {
          description: err instanceof Error ? err.message : "Please try again",
        });
        return;
      }
    }

    setIsLoading(true);
    setIsStreaming(true);
    setStreamingAnswer("");
    setStreamingThoughts("");
    setCurrentAgent(null);
    setStreamingSources([]);
    setActivityLog([]);
    setIsReasoningExpanded(true);
    setCurrentMessageId(null);
    streamStartTimeRef.current = new Date();
    activityLogCounterRef.current = 0;
    setError(null);

    const currentQuery = query;
    setQuery("");

    try {
      await sendChatMessageStream(
        chatId,
        {
          query: currentQuery,
          use_web: true,
          document_ids: selectedDocumentIds.length ? selectedDocumentIds : undefined,
        },
        {
          onMessageId: (messageId) => {
            setCurrentMessageId(messageId);
          },
          onAgentStatus: (node, status) => {
            if (status === "complete") {
              setCurrentAgent(null);
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
          onTitleUpdated: (title, chatId) => {
            // Update chat title in sidebar using context
            updateChatTitle(chatId, title);
          },
          onComplete: (data) => {
            // Streaming complete - refresh messages
            if (chatId) {
              loadChatMessages(chatId);
            }
            setIsStreaming(false);
            setIsLoading(false);
            setStreamingAnswer("");
            setStreamingThoughts("");
            setStreamingSources([]);

            // Show success notification
            const duration = ((new Date().getTime() - streamStartTimeRef.current.getTime()) / 1000).toFixed(1);
            toast.success("Research complete", {
              description: `Answer generated in ${duration}s with ${data.sources?.length || 0} sources`,
            });

            // Start polling if confidence is "pending"
            if (data.confidence === "pending" && data.session_id && chatId) {
              console.log("[Research] Starting verification polling for message:", data.session_id);
              
              pollVerificationStatus(
                chatId,
                data.session_id,
                (verification, newConfidence) => {
                  // Update the message in state
                  setMessages(prev => prev.map(msg => 
                    msg.id === data.session_id
                      ? { ...msg, verification, confidence: newConfidence }
                      : msg
                  ));
                  
                  // Show toast notification
                  toast.success("Verification complete", {
                    description: `Confidence: ${newConfidence}`,
                  });
                }
              ).catch(err => {
                console.error("[Research] Verification polling error:", err);
              });
            }
          },
          onError: (message) => {
            setError(message);
            setIsStreaming(false);
            setIsLoading(false);
            setCurrentAgent(null);
            toast.error("Research failed", {
              description: message,
            });
          },
        }
      );
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Research failed";
      setError(errorMessage);
      setIsStreaming(false);
      setIsLoading(false);
      toast.error("Research failed", {
        description: errorMessage,
      });
    }
  };

  const loadChatMessages = async (chatId: string) => {
    try {
      const chatMessages = await getChatMessages(chatId);
      setMessages(chatMessages);
    } catch (err) {
      console.error("Failed to load messages:", err);
      setError("Failed to load chat messages");
    }
  };

  const handleChatSelect = async (chatId: string) => {
    setCurrentChatId(chatId);
    setError(null);
    setMessages([]);
    setIsLoading(true);

    try {
      await loadChatMessages(chatId);
    } catch (err) {
      setError("Failed to load chat");
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setQuery("");
    setCurrentChatId(null);
    setError(null);
    setStreamingAnswer("");
    setStreamingThoughts("");
    setActivityLog([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
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
                <ChatsSidebar
                  currentChatId={currentChatId}
                  refreshToken={chatsRefreshToken}
                  onChatSelect={handleChatSelect}
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
                  <div className="flex-1 overflow-hidden">
                    <DocumentsPanel
                      chatId={currentChatId}
                      onDocumentSelect={setSelectedDocumentIds}
                      refreshToken={documentsRefreshToken}
                    />
                  </div>
                </div>
              ) : (
                <div className="h-full flex flex-col">
                  <div className="p-4 border-b border-slate-200/70">
                    <p className="text-sm font-medium text-slate-700">Agent Timeline</p>
                    <p className="text-xs text-slate-500 mt-1">
                      Track each agent step for the current message.
                    </p>
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <AgentTimelinePanel sessionId={currentMessageId} />
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
                <p className="text-sm text-slate-700 break-all sm:break-normal">
                  {user.email}
                </p>
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

          {/* Chat Area */}
          <div className="flex-1 min-h-0 flex flex-col">
            {error && (
              <div className="m-4 p-4 rounded-lg border-rose-200 bg-rose-50/80 backdrop-blur-sm">
                <p className="text-sm text-rose-600">{error}</p>
              </div>
            )}

            {/* Messages or Welcome Screen */}
            {!currentChatId && messages.length === 0 && !isStreaming ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
                <div className="relative">
                  <div className="absolute inset-0 bg-linear-to-r from-emerald-400 to-sky-400 blur-3xl opacity-20 rounded-full"></div>
                  <div className="relative text-7xl sm:text-8xl mb-6">🔬</div>
                </div>
                <h2 className="text-2xl font-semibold text-slate-800 mb-3">
                  Start Your Research
                </h2>
                <p className="text-slate-500 max-w-md leading-relaxed">
                  Ask a question to search your documents and the web. Get verified, cited
                  answers with full transparency.
                </p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto">
                <MessageList messages={messages} isLoading={isLoading && !isStreaming} />

                {/* Streaming Content */}
                {isStreaming && (
                  <div className="space-y-6 p-6">
                    {/* Agent Progress */}
                    <AgentProgress activityLog={activityLog} currentAgent={currentAgent} />

                    {/* Reasoning/Thoughts */}
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
                          <div className="prose prose-sm max-w-none">
                            <p className="text-slate-700 whitespace-pre-wrap">
                              {streamingAnswer}
                              <span className="inline-block w-2 h-5 bg-emerald-500 animate-pulse ml-0.5 rounded-sm" />
                            </p>
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {/* Invisible marker for auto-scroll during streaming */}
                    <div ref={streamingEndRef} />
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Input Area */}
          <div className="border-t border-slate-200/70 p-4 sm:p-5 backdrop-blur-sm bg-white/80">
            <div className="max-w-5xl mx-auto">
              <div className="flex gap-3">
                <Textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    currentChatId
                      ? "Continue the conversation..."
                      : "Ask a research question to start a new chat..."
                  }
                  className="min-h-17.5 max-h-35 bg-white border-slate-200/70 resize-none text-base focus:border-emerald-400/70 focus:ring-emerald-200 transition-colors"
                  disabled={isLoading}
                />
                <Button
                  onClick={handleSubmit}
                  disabled={isLoading || !query.trim()}
                  className="bg-linear-to-r from-emerald-500 to-teal-500 hover:from-emerald-500 hover:to-teal-400 px-6 shadow-sm shadow-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isLoading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <Send className="h-5 w-5" />
                  )}
                </Button>
              </div>
              {selectedDocumentIds.length > 0 && (
                <p className="text-xs text-slate-500 mt-2">
                  {selectedDocumentIds.length} document
                  {selectedDocumentIds.length > 1 ? "s" : ""} selected for context
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Upload Dialog */}
        <UploadDialog
          open={uploadDialogOpen}
          chatId={currentChatId}
          onOpenChange={setUploadDialogOpen}
          onUploadSuccess={() => {
            setDocumentsRefreshToken((prev) => prev + 1);
          }}
          onChatCreated={(newChatId, title) => {
            // Refresh chat list and set as active
            setChatsRefreshToken((prev) => prev + 1);
            setCurrentChatId(newChatId);
            // Note: Toast will be shown when we implement sonner
          }}
        />
      </ResizableLayout>
    </div>
  );
}
