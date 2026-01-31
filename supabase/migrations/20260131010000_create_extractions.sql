-- Enums for extraction fields
DO $$ BEGIN
    CREATE TYPE sector AS ENUM (
        'healthcare',
        'finance',
        'tech',
        'energy',
        'manufacturing',
        'retail',
        'other'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE relevance AS ENUM (
        'high',
        'medium',
        'low'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Firecrawl extraction results
CREATE TABLE IF NOT EXISTS extractions (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    title TEXT,
    companies_mentioned TEXT[], -- array of company names
    sectors sector[],
    relevance relevance[],
    summary TEXT,
    raw_json JSONB, -- full firecrawl response for debugging
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id)
);

CREATE INDEX IF NOT EXISTS idx_extractions_document_id ON extractions(document_id);
CREATE INDEX IF NOT EXISTS idx_extractions_sectors ON extractions USING GIN(sectors);
CREATE INDEX IF NOT EXISTS idx_extractions_companies ON extractions USING GIN(companies_mentioned);
CREATE INDEX IF NOT EXISTS idx_extractions_relevance ON extractions USING GIN(relevance);
