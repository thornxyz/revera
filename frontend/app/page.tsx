"use client";

import { useState, useRef, useEffect } from "react";
import {
  Sparkles,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
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
import { StreamingContent } from "@/components/chat/streaming-content";
import { ChatInputArea } from "@/components/chat/chat-input-area";

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
  } = useChatStore();

  // Custom hooks for streaming and UI
  const streaming = useStreamingChat();
  const ui = useUIState();

  // Refs for auto-scroll
  const thinkingBoxRef = useRef<HTMLDivElement>(null);
  const userScrolledAwayRef = useRef(false);
  const chatAreaRef = useRef<HTMLDivElement>(null);
  const wasStreamingRef = useRef(false);

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

  // Reset scroll tracking when streaming ends so the post-stream
  // scroll-to-bottom isn't blocked
  useEffect(() => {
    if (streaming.isStreaming) {
      wasStreamingRef.current = true;
    } else if (wasStreamingRef.current) {
      // Streaming just ended — reset the user-scrolled flag so the
      // messages-change effect below can scroll to the new content
      wasStreamingRef.current = false;
      userScrolledAwayRef.current = false;
    }
  }, [streaming.isStreaming]);

  // Auto-scroll during streaming (only if user hasn't scrolled away)
  useEffect(() => {
    if (streaming.isStreaming && !userScrolledAwayRef.current && chatAreaRef.current) {
      chatAreaRef.current.scrollTo({
        top: chatAreaRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [streaming.isStreaming, streaming.streamingAnswer, streaming.streamingThoughts]);

  // Auto-scroll thinking box to bottom when new thoughts arrive
  useEffect(() => {
    if (thinkingBoxRef.current && streaming.streamingThoughts) {
      thinkingBoxRef.current.scrollTop = thinkingBoxRef.current.scrollHeight;
    }
  }, [streaming.streamingThoughts]);

  // Scroll to bottom when switching chats or loading new messages.
  // Uses a double-RAF to wait for the DOM to fully settle after
  // streaming elements unmount and the MessageList re-renders.
  useEffect(() => {
    const chatArea = chatAreaRef.current;
    if (chatArea) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          chatArea.scrollTop = chatArea.scrollHeight;
        });
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
                onClick={() => ui.setActiveTab("attachments")}
                className={`flex-1 py-3 text-sm font-medium transition-colors ${ui.activeTab === "attachments"
                  ? "text-emerald-700 border-b-2 border-emerald-500 bg-emerald-50"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                  }`}
              >
                Attachments
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
                    <DocumentsPanel chatId={currentChatId} refreshToken={ui.attachmentsRefresh} />
                  </div>
                </div>
              )}
            </div>
          </div>
        }
      >
        {/* Main Content */}
        <div className="flex-1 flex flex-col h-full min-h-0 bg-linear-to-br from-white via-slate-50 to-emerald-50 relative overflow-hidden">
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
          <div className="flex-1 flex flex-col min-h-0">
            {streaming.error && (
              <div className="m-4 p-4 rounded-lg border-rose-200 bg-rose-50/80 backdrop-blur-sm">
                <p className="text-sm text-rose-600">{streaming.error}</p>
              </div>
            )}

            {/* Messages or Welcome Screen */}
            {!currentChatId && messages.length === 0 && !streaming.isStreaming ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center px-4 min-h-0">
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
              <div ref={chatAreaRef} className="flex-1 overflow-y-auto min-h-0">
                <MessageList messages={messages} isLoading={isLoading && !streaming.isStreaming} />

                {/* Streaming Content */}
                {streaming.isStreaming && (
                  <StreamingContent
                    activityLog={streaming.activityLog}
                    currentAgent={streaming.currentAgent}
                    streamingThoughts={streaming.streamingThoughts}
                    streamingAnswer={streaming.streamingAnswer}
                    isReasoningExpanded={ui.isReasoningExpanded}
                    toggleReasoningExpanded={ui.toggleReasoningExpanded}
                    thinkingBoxRef={thinkingBoxRef}
                  />
                )}
              </div>
            )}
          </div>

          {/* Input Area */}
          <ChatInputArea
            query={query}
            setQuery={setQuery}
            isLoading={isLoading}
            onSubmit={handleSubmit}
            onKeyDown={handleKeyDown}
            onUploadClick={() => ui.setUploadDialogOpen(true)}
            currentChatId={currentChatId}
          />
        </div>

        {/* Upload Dialog */}
        <UploadDialog
          open={ui.uploadDialogOpen}
          chatId={currentChatId}
          onOpenChange={ui.setUploadDialogOpen}
          onUploadSuccess={() => {
            ui.refreshAttachments();
          }}
          onChatCreated={async (newChatId, title) => {
            try {
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
              await loadChatMessages(newChatId);
              ui.refreshAttachments();
            } catch (err) {
              console.error("Failed to initialize new chat:", err);
            }
          }}
        />
      </ResizableLayout>
    </div>
  );
}
