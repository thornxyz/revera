-- RPC function for vector similarity search
CREATE OR REPLACE FUNCTION match_document_chunks(
    query_embedding vector(768),
    user_id_param UUID,
    match_count INTEGER DEFAULT 10,
    document_ids UUID[] DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    metadata JSONB,
    distance FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        dc.id,
        dc.document_id,
        dc.content,
        dc.metadata,
        dc.embedding <=> query_embedding AS distance
    FROM document_chunks dc
    JOIN documents d ON d.id = dc.document_id
    WHERE d.user_id = user_id_param
    AND (document_ids IS NULL OR dc.document_id = ANY(document_ids))
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- RPC function for full-text search
CREATE OR REPLACE FUNCTION search_document_chunks_fts(
    search_query TEXT,
    user_id_param UUID,
    match_count INTEGER DEFAULT 10,
    document_ids UUID[] DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    metadata JSONB,
    rank DOUBLE PRECISION
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        dc.id,
        dc.document_id,
        dc.content,
        dc.metadata,
        ts_rank(to_tsvector('english', dc.content), to_tsquery('english', search_query))::double precision AS rank
    FROM document_chunks dc
    JOIN documents d ON d.id = dc.document_id
    WHERE d.user_id = user_id_param
    AND (document_ids IS NULL OR dc.document_id = ANY(document_ids))
    AND to_tsvector('english', dc.content) @@ to_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$$;

