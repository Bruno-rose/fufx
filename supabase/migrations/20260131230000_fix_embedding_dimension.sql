-- gte-small uses 384 dimensions, not 1536
-- Drop old column and recreate with correct size

ALTER TABLE extractions DROP COLUMN IF EXISTS summary_embedding;
ALTER TABLE extractions ADD COLUMN summary_embedding vector(384);

-- Recreate index
DROP INDEX IF EXISTS idx_extractions_embedding;
CREATE INDEX idx_extractions_embedding 
ON extractions USING hnsw (summary_embedding vector_cosine_ops);

-- Update match function for 384 dims
CREATE OR REPLACE FUNCTION match_extractions(
    query_embedding vector(384),
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

