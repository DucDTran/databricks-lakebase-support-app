-- Run this once against the Lakebase database, or let the API/embedding job
-- apply the same idempotent migration through lakebase.ensure_weather_schema().

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS weather_documents (
    id TEXT PRIMARY KEY,
    location TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('alert', 'forecast')),
    headline TEXT NOT NULL,
    narrative_text TEXT NOT NULL CHECK (length(trim(narrative_text)) > 0),
    issued_at TIMESTAMPTZ,
    effective_at TIMESTAMPTZ,
    payload JSONB NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_weather_documents_source_type
    ON weather_documents(source_type);
CREATE INDEX IF NOT EXISTS idx_weather_documents_location
    ON weather_documents(location);
CREATE INDEX IF NOT EXISTS idx_weather_documents_effective_at
    ON weather_documents(effective_at DESC);

CREATE TABLE IF NOT EXISTS weather_embeddings (
    id BIGSERIAL PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES weather_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    chunk_text TEXT NOT NULL CHECK (length(trim(chunk_text)) > 0),
    embedding vector(384) NOT NULL,
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_weather_embeddings_document_id
    ON weather_embeddings(document_id);
CREATE INDEX IF NOT EXISTS idx_weather_embeddings_embedding_cosine
    ON weather_embeddings USING hnsw (embedding vector_cosine_ops);

