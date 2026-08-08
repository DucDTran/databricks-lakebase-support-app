"""Flask REST API for weather document sync and semantic search."""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask, jsonify, request

from embedding import embed_query
from lakebase import (
    ensure_weather_schema,
    get_connection,
    search_weather_embeddings,
    upsert_weather_documents,
)
from weather_client import WeatherClient, WeatherClientError


DEFAULT_SYNC_LIMIT = 50
MAX_SYNC_LIMIT = 500
DEFAULT_TOP_K = 5
MAX_TOP_K = 20


def _json_object() -> dict[str, Any] | None:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def _bounded_integer(
    value: Any,
    *,
    field_name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    return max(minimum, min(maximum, parsed))


def _result_json(row: dict[str, Any]) -> dict[str, Any]:
    result = {
        "id": row.get("id"),
        "location": row.get("location"),
        "source_type": row.get("source_type"),
        "headline": row.get("headline"),
        "narrative_text": row.get("narrative_text"),
        "chunk_index": row.get("chunk_index"),
        "chunk_text": row.get("chunk_text"),
        "similarity": float(row.get("similarity", 0.0)),
    }
    return result


def create_app() -> Flask:
    application = Flask(__name__)
    application.logger.setLevel(logging.INFO)

    @application.get("/health")
    def health() -> Any:
        return jsonify({"ok": True})

    @application.post("/weather/sync")
    def weather_sync() -> Any:
        payload = _json_object()
        if payload is None:
            return jsonify({"error": "Request body must be a JSON object"}), 400
        locations = payload.get("locations")
        if not isinstance(locations, list) or not locations:
            return jsonify({"error": "locations must be a non-empty JSON array"}), 400
        try:
            limit = _bounded_integer(
                payload.get("limit"),
                field_name="limit",
                default=DEFAULT_SYNC_LIMIT,
                minimum=1,
                maximum=MAX_SYNC_LIMIT,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        try:
            documents = WeatherClient().harvest(locations, limit=limit)
            with get_connection() as connection:
                ensure_weather_schema(connection)
                synced = upsert_weather_documents(connection, documents)
        except WeatherClientError as exc:
            application.logger.warning("Weather sync failed: %s", exc)
            return jsonify({"error": str(exc)}), 502
        except Exception:
            application.logger.exception("Weather sync database failure")
            return jsonify({"error": "Unable to write weather documents"}), 500

        return jsonify(
            {
                "count": synced,
                "documents_synced": synced,
                "locations": len(locations),
                "limit": limit,
            }
        )

    @application.post("/weather/search")
    def weather_search() -> Any:
        payload = _json_object()
        if payload is None:
            return jsonify({"error": "Request body must be a JSON object"}), 400
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            return jsonify({"error": "query must be a non-empty string"}), 400
        if len(query) > 2_000:
            return jsonify({"error": "query must be 2,000 characters or fewer"}), 400
        try:
            top_k = _bounded_integer(
                payload.get("top_k"),
                field_name="top_k",
                default=DEFAULT_TOP_K,
                minimum=1,
                maximum=MAX_TOP_K,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        try:
            query_vector = embed_query(query.strip())
            with get_connection() as connection:
                ensure_weather_schema(connection)
                rows = search_weather_embeddings(connection, query_vector, top_k)
        except RuntimeError as exc:
            application.logger.warning("Weather embedding unavailable: %s", exc)
            return jsonify({"error": str(exc)}), 503
        except Exception:
            application.logger.exception("Weather search failure")
            return jsonify({"error": "Unable to search weather documents"}), 500

        results = [_result_json(row) for row in rows]
        return jsonify({"query": query.strip(), "top_k": top_k, "count": len(results), "results": results})

    return application


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")),
    )
