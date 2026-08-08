"""Shared lazy loader for the 384-dimensional sentence-transformers model."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Sequence


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


@lru_cache(maxsize=4)
def get_embedding_model(model_name: str = MODEL_NAME) -> Any:
    """Load a model once per process, on the first embed request."""

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is required for weather embedding operations"
        ) from exc
    return SentenceTransformer(model_name)


def _as_float_lists(vectors: Any) -> list[list[float]]:
    if hasattr(vectors, "tolist"):
        vectors = vectors.tolist()
    return [[float(value) for value in vector] for vector in vectors]


def embed_texts(
    texts: Sequence[str],
    *,
    model_name: str = MODEL_NAME,
    batch_size: int = 32,
) -> list[list[float]]:
    if not texts:
        return []
    model = get_embedding_model(model_name)
    vectors = model.encode(
        list(texts),
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    result = _as_float_lists(vectors)
    invalid = [len(vector) for vector in result if len(vector) != EMBEDDING_DIMENSION]
    if invalid:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSION}-dimensional embeddings, got lengths {invalid}"
        )
    return result


def embed_query(query: str, *, model_name: str = MODEL_NAME) -> list[float]:
    return embed_texts([query], model_name=model_name, batch_size=1)[0]

