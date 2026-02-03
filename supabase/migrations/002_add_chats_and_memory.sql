-- Migration: Add Chats and Messages for Multi-Turn Conversations
-- This migration adds support for:
-- 1. Multi-turn conversations (chats with multiple messages)
-- 2. Chat-scoped documents
-- 3. LangGraph thread integration for memory

-- ============================================
-- 1. CREATE CHATS TABLE
-- ============================================
CREATE TABLE chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT,
    thread_id TEXT UNIQUE,  -- LangGraph thread ID for checkpointer
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- 2. CREATE MESSAGES TABLE
-- ============================================
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    session_id UUID REFERENCES research_sessions(id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    answer TEXT,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    sources JSONB DEFAULT '[]',
    verification JSONB,
    confidence TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- 3. UPDATE EXISTING TABLES
-- ============================================

-- Add chat_id to documents (chat-scoped documents)
ALTER TABLE documents ADD COLUMN chat_id UUID REFERENCES chats(id) ON DELETE CASCADE;

-- Add chat_id and thread_id to research_sessions (backward tracking)
ALTER TABLE research_sessions ADD COLUMN chat_id UUID REFERENCES chats(id) ON DELETE SET NULL;
ALTER TABLE research_sessions ADD COLUMN thread_id TEXT;

-- ============================================
-- 4. CREATE INDEXES
-- ============================================
CREATE INDEX idx_chats_user_id ON chats(user_id);
CREATE INDEX idx_chats_thread_id ON chats(thread_id);
CREATE INDEX idx_chats_updated_at ON chats(updated_at DESC);
CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_documents_chat_id ON documents(chat_id);
CREATE INDEX idx_research_sessions_chat_id ON research_sessions(chat_id);
CREATE INDEX idx_research_sessions_thread_id ON research_sessions(thread_id);

-- ============================================
-- 5. ROW LEVEL SECURITY (RLS)
-- ============================================
ALTER TABLE chats ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- Chats: users can only access their own
CREATE POLICY "Users can view own chats" ON chats
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own chats" ON chats
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own chats" ON chats
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own chats" ON chats
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

-- Update document policies to respect chat scoping
DROP POLICY IF EXISTS "Users can view own documents" ON documents;
CREATE POLICY "Users can view documents in own chats" ON documents
    FOR SELECT USING (
        auth.uid() = user_id AND 
        (chat_id IS NULL OR EXISTS (SELECT 1 FROM chats WHERE chats.id = documents.chat_id AND chats.user_id = auth.uid()))
    );

-- ============================================
-- 6. DATA MIGRATION (Convert existing sessions to chats)
-- ============================================

-- Create chats from completed research sessions
INSERT INTO chats (id, user_id, title, thread_id, created_at, updated_at)
SELECT 
    gen_random_uuid() as id,
    user_id,
    LEFT(query, 60) || CASE WHEN LENGTH(query) > 60 THEN '...' ELSE '' END as title,
    'migrated-' || id::text as thread_id,  -- Prefix to distinguish migrated threads
    created_at,
    created_at as updated_at
FROM research_sessions
WHERE status = 'completed'
ON CONFLICT DO NOTHING;

-- Link sessions to their newly created chats
-- Match by user_id and created_at (assuming unique per user per timestamp)
UPDATE research_sessions rs
SET chat_id = c.id,
    thread_id = c.thread_id
FROM chats c
WHERE rs.user_id = c.user_id 
  AND rs.created_at = c.created_at
  AND rs.chat_id IS NULL;

-- Create messages from completed sessions
INSERT INTO messages (chat_id, session_id, query, answer, role, sources, verification, confidence, created_at)
SELECT 
    rs.chat_id,
    rs.id as session_id,
    rs.query,
    rs.result->>'answer' as answer,
    'assistant' as role,
    COALESCE(rs.result->'sources', '[]'::jsonb) as sources,
    rs.result->'verification' as verification,
    rs.result->>'confidence' as confidence,
    rs.created_at
FROM research_sessions rs
WHERE rs.status = 'completed' 
  AND rs.chat_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM messages m WHERE m.session_id = rs.id
  );

-- ============================================
-- 7. HELPER FUNCTIONS
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

-- ============================================
-- 8. COMMENTS FOR DOCUMENTATION
-- ============================================
COMMENT ON TABLE chats IS 'Conversation threads with multiple messages';
COMMENT ON TABLE messages IS 'Individual query/response pairs within a chat';
COMMENT ON COLUMN chats.thread_id IS 'LangGraph thread ID for checkpointer integration';
COMMENT ON COLUMN documents.chat_id IS 'Documents are now scoped to specific chats';
COMMENT ON COLUMN research_sessions.chat_id IS 'Links session to parent chat for backward tracking';
