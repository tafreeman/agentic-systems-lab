"""RAG embedding providers — in-memory and fallback implementations.

Provides:
- :class:`InMemoryEmbedder`: Deterministic hash-based embedder for testing/dev.
- :class:`FallbackEmbedder`: Ordered fallback across multiple embedding providers.
"""

from __future__ import annotations

import hashlib
import logging
import math
import struct
from typing import Sequence

from .errors import EmbeddingError
from .protocols import EmbeddingProtocol

logger = logging.getLogger(__name__)


class InMemoryEmbedder:
    """Deterministic hash-based embedder for testing and development.

    Generates embedding vectors by hashing input text with SHA-256, then
    expanding the hash bytes into a float vector of the requested
    dimensionality.  Same input always produces the same output, with
    no external API calls.

    Satisfies :class:`EmbeddingProtocol`.

    Args:
        dimensions: Number of dimensions for embedding vectors (default 384).
    """

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions <= 0:
            raise ValueError(f"dimensions must be positive, got {dimensions}")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        """Dimensionality of the embedding vectors."""
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using deterministic hashing.

        Args:
            texts: Strings to embed.

        Returns:
            List of embedding vectors (one per input text), each of
            length :attr:`dimensions` with values in [-1.0, 1.0].
        """
        return [self._hash_to_vector(text) for text in texts]

    def _hash_to_vector(self, text: str) -> list[float]:
        """Convert text to a deterministic float vector.

        Uses SHA-256 iteratively to produce enough bytes, then converts
        to floats in [-1.0, 1.0] and L2-normalizes.
        """
        vector: list[float] = []
        seed = text.encode("utf-8")

        # Generate enough floats by chaining hashes
        iteration = 0
        while len(vector) < self._dimensions:
            hash_input = seed + struct.pack(">I", iteration)
            digest = hashlib.sha256(hash_input).digest()
            # Each 4 bytes → one float via unsigned int → [-1, 1]
            for offset in range(0, len(digest), 4):
                if len(vector) >= self._dimensions:
                    break
                uint_val = struct.unpack(">I", digest[offset : offset + 4])[0]
                # Map [0, 2^32) to [-1.0, 1.0)
                float_val = (uint_val / (2**32)) * 2.0 - 1.0
                vector.append(float_val)
            iteration += 1

        # L2-normalize so vectors have unit length
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector


class FallbackEmbedder:
    """Ordered fallback across multiple embedding providers.

    Tries each provider in sequence.  On :class:`EmbeddingError` from
    one provider, falls back to the next.  If all providers fail, raises
    :class:`EmbeddingError` listing all collected errors.

    Satisfies :class:`EmbeddingProtocol`.

    Args:
        providers: Ordered sequence of embedding providers to try.

    Raises:
        ValueError: If *providers* is empty.
    """

    def __init__(self, providers: Sequence[EmbeddingProtocol]) -> None:
        if not providers:
            raise ValueError("FallbackEmbedder requires at least one provider")
        self._providers: tuple[EmbeddingProtocol, ...] = tuple(providers)

    @property
    def dimensions(self) -> int:
        """Dimensionality from the first provider."""
        return self._providers[0].dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using the first available provider.

        Tries each provider in order.  Falls back on
        :class:`EmbeddingError`.

        Args:
            texts: Strings to embed.

        Returns:
            List of embedding vectors from the first successful provider.

        Raises:
            EmbeddingError: If all providers fail.
        """
        errors: list[EmbeddingError] = []

        for provider in self._providers:
            try:
                return await provider.embed(texts)
            except EmbeddingError as exc:
                logger.warning(
                    "Embedding provider failed, trying next: %s",
                    exc,
                )
                errors.append(exc)
            except Exception as exc:
                wrapped = EmbeddingError(
                    f"Provider {type(provider).__name__} raised "
                    f"{type(exc).__name__}: {exc}"
                )
                wrapped.__cause__ = exc
                logger.warning(
                    "Embedding provider raised non-RAG error, trying next: %s",
                    exc,
                )
                errors.append(wrapped)

        error_messages = "; ".join(str(e) for e in errors)
        raise EmbeddingError(
            f"All {len(errors)} embedding providers failed: {error_messages}"
        )
