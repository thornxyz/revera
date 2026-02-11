"use client";

import { useState, useRef, useEffect } from "react";
import {
  Send,
  Loader2,
  Sparkles,
  ImagePlus,
  Upload,
  Brain,
  ChevronDown,
  ChevronUp
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DocumentsPanel } from "@/components/documents-panel";
import { UploadDialog } from "@/components/upload-dialog";
import { ChatsSidebar } from "@/components/chats-sidebar";
import { MessageList } from "@/components/message-list";
import { getChatMessages } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useChatStore } from "@/store/chat-store";
import { useStreamingChat } from "@/hooks/useStreamingChat";
import { useUIState } from "@/hooks/useUIState";
import { ResizableLayout } from "@/components/resizable-layout";
import { LoginPage } from "@/components/login-page";
import { AgentProgress } from "@/components/agent-progress";
import { StreamMarkdown } from "@/components/stream-markdown";

export default function ResearchPage() {
  const { user, loading, signOut } = useAuth();

  // Local state for query input
  const [query, setQuery] = useState("");

  // Zustand store for chat state
  const {
    currentChatId,
    messages,
    messagesLoading,
    setCurrentChat,
    setMessages,
    clearChat,
    addChat,
    isImageMode,
    setIsImageMode,
  } = useChatStore();

  // Custom hooks for streaming and UI
  const streaming = useStreamingChat();
  const ui = useUIState();

  // Refs for auto-scroll
  const streamingEndRef = useRef<HTMLDivElement>(null);
  const thinkingBoxRef = useRef<HTMLDivElement>(null);
  const userScrolledAwayRef = useRef(false);
  const chatAreaRef = useRef<HTMLDivElement>(null);

  // Track if user has scrolled away during streaming
  useEffect(() => {
    const chatArea = chatAreaRef.current;
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
    if (streaming.isStreaming && !userScrolledAwayRef.current && streamingEndRef.current) {
      streamingEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [streaming.isStreaming, streaming.streamingAnswer, streaming.streamingThoughts]);

  // Auto-scroll thinking box to bottom when new thoughts arrive
  useEffect(() => {
    if (thinkingBoxRef.current && streaming.streamingThoughts) {
      thinkingBoxRef.current.scrollTop = thinkingBoxRef.current.scrollHeight;
    }
  }, [streaming.streamingThoughts]);

  // Scroll to bottom when switching chats or loading new messages
  useEffect(() => {
    const chatArea = chatAreaRef.current;
    if (chatArea) {
      // Use requestAnimationFrame to wait for DOM to render the messages
      requestAnimationFrame(() => {
        chatArea.scrollTop = chatArea.scrollHeight;
      });
    }
  }, [currentChatId, messages]);

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
    const currentQuery = query;
    setQuery("");
    // Reset image mode after sending so the next message defaults to research
    if (isImageMode) setIsImageMode(false);
    await streaming.sendMessage(currentQuery);
  };

  const loadChatMessages = async (chatId: string) => {
    try {
      const chatMessages = await getChatMessages(chatId);
      setMessages(chatMessages);
    } catch (err) {
      console.error("Failed to load messages:", err);
      streaming.setError("Failed to load chat messages");
    }
  };

  const handleChatSelect = async (chatId: string) => {
    setCurrentChat(chatId);
    streaming.setError(null);
    await loadChatMessages(chatId);
  };

  const handleNewChat = () => {
    clearChat();
    setQuery("");
    streaming.resetStreamingState();
    streaming.setActivityLog([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isLoading = streaming.isLoading || messagesLoading;

  return (
    <div className="flex h-screen bg-linear-to-br from-slate-50 via-white to-emerald-50 text-slate-900">
      <ResizableLayout
        sidebar={
          <div className="h-full flex flex-col overflow-x-auto overflow-y-hidden">
            {/* Sidebar Tabs */}
            <div className="flex border-b border-slate-200/70 bg-white/80">
              <button
                onClick={() => ui.setActiveTab("chat")}
                className={`flex-1 py-3 text-sm font-medium transition-colors ${ui.activeTab === "chat"
                  ? "text-emerald-700 border-b-2 border-emerald-500 bg-emerald-50"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                  }`}
              >
                Chats
              </button>
              <button
                onClick={() => ui.setActiveTab("documents")}
                className={`flex-1 py-3 text-sm font-medium transition-colors ${ui.activeTab === "documents"
                  ? "text-emerald-700 border-b-2 border-emerald-500 bg-emerald-50"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                  }`}
              >
                Documents
              </button>
            </div>

            {/* Sidebar Content */}
            <div className="flex-1 overflow-hidden relative">
              {ui.activeTab === "chat" ? (
                <ChatsSidebar
                  currentChatId={currentChatId}
                  onChatSelect={handleChatSelect}
                  onNewChat={handleNewChat}
                />
              ) : (
                <div className="h-full flex flex-col">
                  <div className="p-4 border-b border-slate-200/70">
                    <Button
                      onClick={() => ui.setUploadDialogOpen(true)}
                      className="w-full bg-linear-to-r from-emerald-500 to-teal-500 hover:from-emerald-500 hover:to-teal-400 shadow-sm shadow-emerald-500/20"
                    >
                      <Upload className="h-4 w-4 mr-2" />
                      Upload Document
                    </Button>
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <DocumentsPanel chatId={currentChatId} />
                  </div>
                </div>
              )}
            </div>
          </div>
        }
      >
        {/* Main Content */}
        <div className="flex-1 flex flex-col h-full min-h-0 bg-linear-to-br from-white via-slate-50 to-emerald-50 relative">
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
            {streaming.error && (
              <div className="m-4 p-4 rounded-lg border-rose-200 bg-rose-50/80 backdrop-blur-sm">
                <p className="text-sm text-rose-600">{streaming.error}</p>
              </div>
            )}

            {/* Messages or Welcome Screen */}
            {!currentChatId && messages.length === 0 && !streaming.isStreaming ? (
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
              <div ref={chatAreaRef} className="flex-1 overflow-y-auto">
                <MessageList messages={messages} isLoading={isLoading && !streaming.isStreaming} />

                {/* Streaming Content */}
                {streaming.isStreaming && (
                  <div className="space-y-6 p-6 pb-32">
                    {/* Agent Progress */}
                    <AgentProgress activityLog={streaming.activityLog} currentAgent={streaming.currentAgent} />

                    {/* Reasoning/Thoughts */}
                    {streaming.streamingThoughts && (
                      <div className="bg-slate-50/80 border border-slate-200 backdrop-blur-sm rounded-xl overflow-hidden">
                        <button
                          onClick={ui.toggleReasoningExpanded}
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
                          {ui.isReasoningExpanded ? (
                            <ChevronUp className="h-4 w-4 text-slate-400" />
                          ) : (
                            <ChevronDown className="h-4 w-4 text-slate-400" />
                          )}
                        </button>
                        {ui.isReasoningExpanded && (
                          <div ref={thinkingBoxRef} className="p-4 max-h-60 overflow-y-auto reasoning-box">
                            <StreamMarkdown
                              content={streaming.streamingThoughts}
                              isStreaming={true}
                              className="text-xs text-slate-600 **:text-xs [&_p]:leading-relaxed [&_code]:text-[10px]"
                            />
                          </div>
                        )}
                      </div>
                    )}

                    {/* Streaming Answer */}
                    {streaming.streamingAnswer && (
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
                            content={streaming.streamingAnswer}
                            isStreaming={true}
                          />
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
          <div className="p-4 sm:p-8 pb-10 sm:pb-12 bg-transparent pointer-events-none absolute bottom-0 left-0 right-0 z-10">
            <div className="max-w-4xl mx-auto w-full pointer-events-auto">
              <div
                className={cn(
                  "input-pill-container transition-all duration-500",
                  "glass-morphism bg-white/70 ring-1 ring-slate-200/50",
                  isImageMode ? "emerald-glow ring-emerald-400/30" : "premium-shadow"
                )}
              >
                <div className="flex items-center gap-1 pl-2">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setIsImageMode(!isImageMode)}
                    className={cn(
                      "h-10 w-10 rounded-xl transition-all duration-300",
                      isImageMode
                        ? "bg-emerald-100/80 text-emerald-600"
                        : "text-slate-400 hover:text-slate-600 hover:bg-slate-100/50"
                    )}
                    title={isImageMode ? "Image Mode Active" : "Enable Image Generation"}
                  >
                    <ImagePlus className={cn("h-5 w-5", isImageMode && "animate-pulse")} />
                  </Button>

                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => ui.setUploadDialogOpen(true)}
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
                    onKeyDown={handleKeyDown}
                    placeholder={
                      isImageMode
                        ? "Describe the image you want to generate..."
                        : currentChatId
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
                    onClick={handleSubmit}
                    disabled={isLoading || !query.trim()}
                    className={cn(
                      "h-9 w-9 rounded-xl transition-all duration-300 shadow-sm",
                      isImageMode
                        ? "bg-emerald-500 hover:bg-emerald-600 text-white"
                        : "bg-slate-900 hover:bg-slate-800 text-white"
                    )}
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
        </div>

        {/* Upload Dialog */}
        <UploadDialog
          open={ui.uploadDialogOpen}
          chatId={currentChatId}
          onOpenChange={ui.setUploadDialogOpen}
          onUploadSuccess={() => {
            // Documents panel will auto-refresh via its own state
          }}
          onChatCreated={(newChatId, title) => {
            // Create chat preview and add to store
            const chatPreview = {
              id: newChatId,
              user_id: user.id,
              title: title || "New Chat",
              thread_id: "",
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              last_message_preview: null,
              message_count: 0,
            };
            addChat(chatPreview);
            setCurrentChat(newChatId);
          }}
        />
      </ResizableLayout>
    </div>
  );
}
