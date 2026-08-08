"""Chunk and embed unembedded weather documents into Lakebase.

Run after ``POST /weather/sync`` (or after manually loading
``weather_documents``):

    python ingest_weather_embeddings.py --limit 200
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Mapping, Sequence

from embedding import EMBEDDING_DIMENSION, MODEL_NAME, embed_texts
from lakebase import (
    ensure_weather_schema,
    fetch_unembedded_documents,
    get_connection,
    insert_weather_embeddings,
)


CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def chunk_text(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping character windows.

    NWS narratives are normally short.  The window keeps longer alert
    descriptions and instructions searchable without losing context at a
    boundary.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be between zero and chunk_size - 1")
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(normalized):
            break
        start = end - chunk_overlap
    return chunks


def build_chunk_records(
    documents: Sequence[Mapping[str, Any]],
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for document in documents:
        chunks = chunk_text(
            document["narrative_text"],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        for chunk_index, chunk in enumerate(chunks):
            records.append(
                {
                    "document_id": document["id"],
                    "chunk_index": chunk_index,
                    "chunk_text": chunk,
                }
            )
    return records


def embed_document_rows(
    documents: Sequence[Mapping[str, Any]],
    *,
    model_name: str = MODEL_NAME,
    batch_size: int = 32,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    rows = build_chunk_records(
        documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    vectors = embed_texts(
        [row["chunk_text"] for row in rows],
        model_name=model_name,
        batch_size=batch_size,
    )
    if any(len(vector) != EMBEDDING_DIMENSION for vector in vectors):
        raise ValueError(f"All vectors must have {EMBEDDING_DIMENSION} dimensions")
    for row, vector in zip(rows, vectors):
        row["embedding"] = vector
        row["model_name"] = model_name
    return rows


def run(
    *,
    limit: int | None = None,
    batch_size: int = 32,
    model_name: str = MODEL_NAME,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    dry_run: bool = False,
) -> dict[str, int]:
    with get_connection() as connection:
        ensure_weather_schema(connection)
        documents = fetch_unembedded_documents(connection, limit=limit)
        if not documents:
            return {"documents": 0, "chunks": 0}
        rows = embed_document_rows(
            documents,
            model_name=model_name,
            batch_size=batch_size,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if not dry_run:
            insert_weather_embeddings(connection, rows)
        return {"documents": len(documents), "chunks": len(rows)}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Maximum documents to process")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=CHUNK_OVERLAP)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    print(
        json.dumps(
            run(
                limit=args.limit,
                batch_size=args.batch_size,
                model_name=args.model,
                chunk_size=args.chunk_size,
                chunk_overlap=args.overlap,
                dry_run=args.dry_run,
            )
        )
    )
