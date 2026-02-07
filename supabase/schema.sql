-- Supabase Schema for Revera (Qdrant-based Vector Storage)
-- Note: Embeddings are stored in Qdrant, not PostgreSQL.

-- ============================================
-- TABLES
-- ============================================

-- Chats: Conversation threads with multiple messages
CREATE TABLE chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT,
    thread_id TEXT UNIQUE,  -- LangGraph thread ID for checkpointer
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Documents table (metadata only, vectors are in Qdrant)
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    chat_id UUID REFERENCES chats(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    type VARCHAR(10) DEFAULT 'pdf',  -- 'pdf' or 'image'
    file_path TEXT,
    image_url TEXT,  -- Supabase Storage path for images
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Research sessions
CREATE TABLE research_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    chat_id UUID REFERENCES chats(id) ON DELETE SET NULL,
    thread_id TEXT,
    query TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Messages: Individual query/response pairs within a chat
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    session_id UUID REFERENCES research_sessions(id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    answer TEXT,
    thinking TEXT,  -- LLM reasoning/thought process
    agent_timeline JSONB DEFAULT '[]',  -- Agent execution steps [{agent, latency_ms, events}]
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    sources JSONB DEFAULT '[]',
    verification JSONB,
    confidence TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Agent execution logs
CREATE TABLE agent_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    events JSONB DEFAULT '{}',
    latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- INDEXES
-- ============================================
CREATE INDEX idx_chats_user_id ON chats(user_id);
CREATE INDEX idx_chats_thread_id ON chats(thread_id);
CREATE INDEX idx_chats_updated_at ON chats(updated_at DESC);
CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_chat_id ON documents(chat_id);
CREATE INDEX idx_research_sessions_user_id ON research_sessions(user_id);
CREATE INDEX idx_research_sessions_chat_id ON research_sessions(chat_id);
CREATE INDEX idx_research_sessions_thread_id ON research_sessions(thread_id);
CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_agent_logs_session_id ON agent_logs(session_id);

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================
ALTER TABLE chats ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_logs ENABLE ROW LEVEL SECURITY;

-- Chats: users can only access their own
CREATE POLICY "Users can view own chats" ON chats
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own chats" ON chats
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own chats" ON chats
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own chats" ON chats
    FOR DELETE USING (auth.uid() = user_id);

-- Documents: users can only access their own (respecting chat scoping)
CREATE POLICY "Users can view documents in own chats" ON documents
    FOR SELECT USING (
        auth.uid() = user_id AND 
        (chat_id IS NULL OR EXISTS (SELECT 1 FROM chats WHERE chats.id = documents.chat_id AND chats.user_id = auth.uid()))
    );
CREATE POLICY "Users can insert own documents" ON documents
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own documents" ON documents
    FOR DELETE USING (auth.uid() = user_id);

-- Research sessions: users can only access their own
CREATE POLICY "Users can view own sessions" ON research_sessions
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own sessions" ON research_sessions
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own sessions" ON research_sessions
    FOR DELETE USING (auth.uid() = user_id);

-- Messages: access through chat ownership
CREATE POLICY "Users can view messages in own chats" ON messages
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM chats WHERE chats.id = messages.chat_id AND chats.user_id = auth.uid())
    );
CREATE POLICY "Users can insert messages in own chats" ON messages
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM chats WHERE chats.id = messages.chat_id AND chats.user_id = auth.uid())
    );
-- Allow service role to update messages for background verification
CREATE POLICY "Service role can update message verification" ON messages
    FOR UPDATE USING (true);

-- Agent logs: access through session ownership
CREATE POLICY "Users can view logs of own sessions" ON agent_logs
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM research_sessions WHERE research_sessions.id = agent_logs.session_id AND research_sessions.user_id = auth.uid())
    );

-- ============================================
-- FUNCTIONS & TRIGGERS
-- ============================================

-- Function to update chat's updated_at timestamp when messages are added
CREATE OR REPLACE FUNCTION update_chat_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE chats 
    SET updated_at = NEW.created_at 
    WHERE id = NEW.chat_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update chat timestamp
CREATE TRIGGER trigger_update_chat_timestamp
AFTER INSERT ON messages
FOR EACH ROW
EXECUTE FUNCTION update_chat_timestamp();

-- Function to get chats with message count and preview (optimized for single query)
CREATE OR REPLACE FUNCTION get_chats_with_preview(p_user_id UUID)
RETURNS TABLE (
    id UUID,
    user_id UUID,
    title TEXT,
    thread_id TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    message_count BIGINT,
    last_message_preview TEXT
) 
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.user_id,
        c.title,
        c.thread_id,
        c.created_at,
        c.updated_at,
        COUNT(m.id) as message_count,
        (
            SELECT 
                CASE 
                    WHEN LENGTH(msg.query) > 80 THEN LEFT(msg.query, 80) || '...'
                    ELSE msg.query
                END
            FROM messages msg
            WHERE msg.chat_id = c.id
            ORDER BY msg.created_at DESC
            LIMIT 1
        ) as last_message_preview
    FROM chats c
    LEFT JOIN messages m ON m.chat_id = c.id
    WHERE c.user_id = p_user_id
    GROUP BY c.id, c.user_id, c.title, c.thread_id, c.created_at, c.updated_at
    ORDER BY c.updated_at DESC;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- COMMENTS
-- ============================================
COMMENT ON TABLE chats IS 'Conversation threads with multiple messages';
COMMENT ON TABLE messages IS 'Individual query/response pairs within a chat';
COMMENT ON COLUMN chats.thread_id IS 'LangGraph thread ID for checkpointer integration';
COMMENT ON COLUMN documents.chat_id IS 'Documents are now scoped to specific chats';
COMMENT ON COLUMN research_sessions.chat_id IS 'Links session to parent chat for backward tracking';
COMMENT ON POLICY "Service role can update message verification" ON messages IS 
    'Allows background critic process to update verification and confidence fields after streaming completes';
