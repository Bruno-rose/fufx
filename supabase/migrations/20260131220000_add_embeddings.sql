-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to extractions (1536 dims for text-embedding-3-small)
ALTER TABLE extractions 
ADD COLUMN IF NOT EXISTS summary_embedding vector(1536);

-- Create index for similarity search (using HNSW for better performance)
CREATE INDEX IF NOT EXISTS idx_extractions_embedding 
ON extractions USING hnsw (summary_embedding vector_cosine_ops);

-- Function to match extractions by similarity
CREATE OR REPLACE FUNCTION match_extractions(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    id int,
    document_id int,
    title text,
    summary text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id,
        e.document_id,
        e.title,
        e.summary,
        1 - (e.summary_embedding <=> query_embedding) as similarity
    FROM extractions e
    WHERE e.summary_embedding IS NOT NULL
      AND 1 - (e.summary_embedding <=> query_embedding) > match_threshold
    ORDER BY e.summary_embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Note: After deploying the edge function, create a database webhook in Supabase Dashboard:
-- 1. Go to Database > Webhooks
-- 2. Create webhook for "extractions" table on INSERT and UPDATE events
-- 3. Set the URL to your edge function: https://<project-ref>.supabase.co/functions/v1/generate-embedding
-- 4. Add header: Authorization: Bearer <SUPABASE_ANON_KEY>

