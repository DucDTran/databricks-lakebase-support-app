"""Lakebase/Postgres connection and weather vector-storage helpers."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

import psycopg2
from psycopg2.extras import Json, RealDictCursor, execute_values


EMBEDDING_DIMENSION = 384
WEATHER_SCHEMA_DDL = f"""
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
    embedding vector({EMBEDDING_DIMENSION}) NOT NULL,
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_weather_embeddings_document_id
    ON weather_embeddings(document_id);
CREATE INDEX IF NOT EXISTS idx_weather_embeddings_embedding_cosine
    ON weather_embeddings USING hnsw (embedding vector_cosine_ops);
"""


def _connection_from_environment():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    required = ("PGHOST", "PGDATABASE", "PGUSER")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing Lakebase connection settings: " + ", ".join(missing))

    kwargs: dict[str, Any] = {
        "host": os.environ["PGHOST"],
        "dbname": os.environ["PGDATABASE"],
        "user": os.environ["PGUSER"],
        "port": os.getenv("PGPORT", "5432"),
        "sslmode": os.getenv("PGSSLMODE", "require"),
    }
    if os.getenv("PGPASSWORD"):
        kwargs["password"] = os.environ["PGPASSWORD"]
    elif os.getenv("ENDPOINT_NAME"):
        # Lakebase Autoscaling uses a short-lived OAuth database credential.
        from databricks.sdk import WorkspaceClient

        credential = WorkspaceClient().postgres.generate_database_credential(
            endpoint=os.environ["ENDPOINT_NAME"]
        )
        kwargs["password"] = credential.token
    else:
        raise RuntimeError(
            "Set PGPASSWORD for local Postgres or ENDPOINT_NAME for a Databricks "
            "Lakebase Autoscaling connection"
        )
    return psycopg2.connect(**kwargs)


@contextmanager
def get_connection() -> Iterator[Any]:
    """Yield a psycopg2 connection and commit/rollback as a unit of work."""

    connection = _connection_from_environment()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_weather_schema(connection: Any) -> None:
    """Apply the idempotent weather document and embedding migration."""

    with connection.cursor() as cursor:
        cursor.execute(WEATHER_SCHEMA_DDL)


def initialize_weather_schema() -> None:
    with get_connection() as connection:
        ensure_weather_schema(connection)


def _record_value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def upsert_weather_documents(connection: Any, documents: Sequence[Any]) -> int:
    """Insert normalized documents and update changed NWS content on re-sync."""

    if not documents:
        return 0
    values = [
        (
            _record_value(document, "id"),
            _record_value(document, "location"),
            _record_value(document, "source_type"),
            _record_value(document, "headline"),
            _record_value(document, "narrative_text"),
            _record_value(document, "issued_at"),
            _record_value(document, "effective_at"),
            Json(_record_value(document, "payload", {})),
            _record_value(document, "synced_at"),
        )
        for document in documents
    ]
    statement = """
        INSERT INTO weather_documents
            (id, location, source_type, headline, narrative_text,
             issued_at, effective_at, payload, synced_at, updated_at)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            location = EXCLUDED.location,
            source_type = EXCLUDED.source_type,
            headline = EXCLUDED.headline,
            narrative_text = EXCLUDED.narrative_text,
            issued_at = EXCLUDED.issued_at,
            effective_at = EXCLUDED.effective_at,
            payload = EXCLUDED.payload,
            synced_at = EXCLUDED.synced_at,
            updated_at = now()
    """
    with connection.cursor() as cursor:
        execute_values(
            cursor,
            statement,
            values,
            template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
        )
    return len(values)


def fetch_unembedded_documents(connection: Any, limit: int | None = None) -> list[dict[str, Any]]:
    """Read documents that do not yet have any embedding chunks."""

    query = """
        SELECT d.id, d.narrative_text
        FROM weather_documents d
        WHERE NOT EXISTS (
            SELECT 1
            FROM weather_embeddings e
            WHERE e.document_id = d.id
        )
        ORDER BY d.synced_at ASC, d.id ASC
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT %s"
        params = (limit,)
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, params)
        return list(cursor.fetchall())


def vector_literal(embedding: Sequence[float] | str) -> str:
    """Format a vector for the explicit ``%s::vector`` SQL cast."""

    if isinstance(embedding, str):
        return embedding
    return "[" + ",".join(format(float(value), ".9g") for value in embedding) + "]"


def insert_weather_embeddings(connection: Any, rows: Sequence[Mapping[str, Any]]) -> int:
    """Batch upsert embedding chunks with psycopg2/pgvector."""

    if not rows:
        return 0
    values = [
        (
            row["document_id"],
            row["chunk_index"],
            row["chunk_text"],
            vector_literal(row["embedding"]),
            row["model_name"],
        )
        for row in rows
    ]
    statement = """
        INSERT INTO weather_embeddings
            (document_id, chunk_index, chunk_text, embedding, model_name)
        VALUES %s
        ON CONFLICT (document_id, chunk_index) DO UPDATE SET
            chunk_text = EXCLUDED.chunk_text,
            embedding = EXCLUDED.embedding,
            model_name = EXCLUDED.model_name,
            created_at = now()
    """
    with connection.cursor() as cursor:
        execute_values(
            cursor,
            statement,
            values,
            template="(%s, %s, %s, %s::vector, %s)",
        )
    return len(values)


def search_weather_embeddings(
    connection: Any,
    embedding: Sequence[float] | str,
    top_k: int,
) -> list[dict[str, Any]]:
    """Return nearest weather chunks using pgvector cosine distance."""

    vector = vector_literal(embedding)
    query = """
        SELECT
            d.id,
            d.location,
            d.source_type,
            d.headline,
            d.narrative_text,
            e.chunk_index,
            e.chunk_text,
            1 - (e.embedding <=> %s::vector) AS similarity
        FROM weather_embeddings e
        JOIN weather_documents d ON d.id = e.document_id
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
    """
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, (vector, vector, top_k))
        return list(cursor.fetchall())

