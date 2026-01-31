-- GovInfo document URLs and metadata
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    package_id TEXT NOT NULL,
    granule_id TEXT,
    title TEXT,
    doc_class TEXT,
    publish_date DATE NOT NULL,
    metadata TEXT,
    pdf_url TEXT,
    html_url TEXT,
    details_url TEXT,
    summary TEXT,
    crawled_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(package_id, granule_id)
);

CREATE INDEX IF NOT EXISTS idx_documents_publish_date ON documents(publish_date);
CREATE INDEX IF NOT EXISTS idx_documents_doc_class ON documents(doc_class);

