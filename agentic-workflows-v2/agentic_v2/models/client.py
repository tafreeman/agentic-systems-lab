"""LLM client wrapper with smart routing integration.

:class:`LLMClientWrapper` is the primary interface for making LLM calls
within the native engine.  It combines:

- **Smart routing** — delegates model selection to :class:`SmartModelRouter`,
  which provides health-weighted fallback, circuit-breaking, and adaptive
  cooldowns.
- **Response caching** — SHA-256 keyed, TTL-based deduplication with LRU
  pruning at 1 000 entries.
- **Token budget tracking** — :class:`TokenBudget` enforces a per-run cap
  on total token consumption.
- **Streaming support** — :meth:`complete_stream` yields response chunks
  while still recording router metrics on completion.
- **Retry with jitter** — :func:`retry_with_jitter` decorator provides
  exponential backoff with configurable jitter factor.

The :class:`LLMBackend` :class:`Protocol` defines the minimal interface
that concrete backends (OpenAI, Anthropic, Gemini, etc.) must implement.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Protocol, TypeVar

if TYPE_CHECKING:
    from ..middleware.response_sanitizer import ResponseSanitizer
    from ..middleware.sanitization import SanitizationMiddleware

from .router import ModelTier
from .smart_router import SmartModelRouter, get_smart_router

logger = logging.getLogger(__name__)


# Protocol for LLM backend
class LLMBackend(Protocol):
    """Protocol for LLM backend implementations."""

    async def complete(self, model: str, prompt: str, **kwargs: Any) -> str:
        """Send completion request."""
        ...

    async def complete_stream(
        self, model: str, prompt: str, **kwargs: Any
    ) -> AsyncIterator[str]:
        """Send streaming completion request."""
        ...

    def count_tokens(self, text: str, model: str) -> int:
        """Count tokens in text."""
        ...


T = TypeVar("T")


def retry_with_jitter(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.5,
) -> Callable:
    """Decorator for retrying with exponential backoff and jitter.

    Args:
        max_retries: Maximum retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Jitter factor (0-1)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2**attempt), max_delay)
                        jittered = delay * (1 + random.uniform(-jitter, jitter))
                        await asyncio.sleep(jittered)
            raise last_error

        return wrapper

    return decorator


@dataclass
class TokenBudget:
    """Track token usage against a budget."""

    max_tokens: int
    used_tokens: int = 0

    @property
    def remaining(self) -> int:
        """Get remaining tokens."""
        return max(0, self.max_tokens - self.used_tokens)

    @property
    def percentage_used(self) -> float:
        """Get percentage of budget used."""
        if self.max_tokens == 0:
            return 100.0
        return (self.used_tokens / self.max_tokens) * 100

    def consume(self, tokens: int) -> bool:
        """Consume tokens from budget.

        Returns:
            True if tokens were available, False if budget exceeded
        """
        if self.used_tokens + tokens > self.max_tokens:
            return False
        self.used_tokens += tokens
        return True

    def can_afford(self, tokens: int) -> bool:
        """Check if budget can afford tokens."""
        return self.used_tokens + tokens <= self.max_tokens


@dataclass
class CachedResponse:
    """Cached LLM response."""

    response: str
    model: str
    timestamp: datetime
    tokens_used: int

    @property
    def age_seconds(self) -> float:
        """Get age of cached response in seconds."""
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds()


@dataclass
class LLMClientWrapper:
    """High-level LLM client with smart routing, caching, and budgeting.

    Wraps a pluggable :class:`LLMBackend` with :class:`SmartModelRouter`
    integration.  On each call, the router selects the best model for the
    requested tier, the client executes the call, and the router records
    the outcome (success + latency, or failure type) to improve future
    selections.

    Attributes:
        backend: Injected LLM backend (``None`` = placeholder mode).
        router: Smart model router for selection and health tracking.
        cache: In-memory response cache keyed by prompt + tier hash.
        cache_ttl_seconds: Time-to-live for cached responses (default 300 s).
        enable_cache: Master switch for response caching.
        budget: Optional token budget enforcing a per-run cap.
        log_prompts: Log truncated prompts at INFO level.
        log_responses: Log truncated responses at INFO level.
    """

    # Backend (injected)
    backend: LLMBackend | None = None

    # Router
    router: SmartModelRouter = field(default_factory=get_smart_router)

    # Caching
    cache: dict[str, CachedResponse] = field(default_factory=dict)
    cache_ttl_seconds: int = 300  # 5 minutes
    enable_cache: bool = True

    # Token budget
    budget: TokenBudget | None = None

    # Logging
    log_prompts: bool = False
    log_responses: bool = False

    # Sanitization (optional)
    sanitization: SanitizationMiddleware | None = None
    response_sanitizer: ResponseSanitizer | None = None

    @property
    def model_id(self) -> str | None:
        """Return the current default model ID from the router."""
        return self.router.get_model_for_tier(ModelTier.TIER_2)

    def set_backend(self, backend: LLMBackend) -> None:
        """Set the LLM backend.

        Args:
            backend: Backend implementation
        """
        self.backend = backend

    def set_budget(self, max_tokens: int) -> None:
        """Set token budget.

        Args:
            max_tokens: Maximum tokens to use
        """
        self.budget = TokenBudget(max_tokens=max_tokens)

    def _cache_key(self, prompt: str, tier: ModelTier, **kwargs: Any) -> str:
        """Generate cache key for request.

        The key is a stable hash of the prompt, model tier, and sorted
        kwargs. This ensures that identical requests produce the same
        key regardless of dictionary ordering.
        """
        key_data = f"{prompt}:{tier.value}:{sorted(kwargs.items())}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def _get_cached(self, key: str) -> CachedResponse | None:
        """Get cached response if valid.

        Checks for presence and ensures the entry has not exceeded the
        TTL.
        """
        if not self.enable_cache:
            return None

        cached = self.cache.get(key)
        if cached is None:
            return None

        # Expiry check
        if cached.age_seconds > self.cache_ttl_seconds:
            del self.cache[key]
            return None

        return cached

    def _set_cached(self, key: str, response: str, model: str, tokens: int) -> None:
        """Cache a response.

        Stores the model used and token count alongside the content to
        preserve metadata on cache hit. Includes LRU-style pruning if
        cache size exceeds 1000 entries.
        """
        if not self.enable_cache:
            return

        self.cache[key] = CachedResponse(
            response=response,
            model=model,
            timestamp=datetime.now(timezone.utc),
            tokens_used=tokens,
        )

        # Cache Pruning Policy:
        # If cache too large, remove the oldest 100 entries (10%).
        if len(self.cache) > 1000:
            sorted_keys = sorted(
                self.cache.keys(), key=lambda k: self.cache[k].timestamp
            )
            for k in sorted_keys[:100]:
                del self.cache[k]

    async def complete(
        self,
        prompt: str,
        tier: ModelTier = ModelTier.TIER_2,
        max_retries: int = 3,
        use_cache: bool = True,
        **kwargs: Any,
    ) -> tuple[str, str, int]:
        """Send completion request with smart routing.

        Args:
            prompt: Prompt to send
            tier: Model tier to use
            max_retries: Maximum models to try
            use_cache: Whether to use response cache
            **kwargs: Additional arguments for backend

        Returns:
            Tuple of (response, model_used, tokens_used)

        Raises:
            RuntimeError: If no backend configured or all models fail
            ValueError: If budget exceeded
        """
        if self.backend is None:
            raise RuntimeError("No LLM backend configured")

        # Check cache
        if use_cache and self.enable_cache:
            cache_key = self._cache_key(prompt, tier, **kwargs)
            cached = self._get_cached(cache_key)
            if cached:
                logger.debug(f"Cache hit for key {cache_key}")
                return cached.response, cached.model, cached.tokens_used

        # Log prompt if enabled
        if self.log_prompts:
            logger.info(f"Prompt (tier={tier.name}): {prompt[:200]}...")

        # Pre-send sanitization
        effective_prompt = prompt
        if self.sanitization is not None:
            san_result = await self.sanitization.process(
                prompt, {"source": "llm_complete", "tier": tier.name}
            )
            if not san_result.is_safe:
                raise ValueError(
                    f"Prompt blocked by sanitization: {san_result.classification.value}"
                )
            if san_result.sanitized_text is not None:
                effective_prompt = san_result.sanitized_text

        # Use router for model selection and fallback
        async def call_model(model: str, p: str) -> tuple[str, int]:
            response = await self.backend.complete(model, p, **kwargs)
            tokens = self.backend.count_tokens(p + response, model)
            return response, tokens

        tried = []
        last_error = None

        for _ in range(max_retries):
            model = self.router.get_model_for_tier(tier)
            if model is None or model in tried:
                break

            tried.append(model)

            # Estimate tokens and check budget
            prompt_tokens = self.backend.count_tokens(effective_prompt, model)
            if self.budget and not self.budget.can_afford(prompt_tokens * 2):
                raise ValueError(
                    f"Budget exceeded: {self.budget.used_tokens}/{self.budget.max_tokens}"
                )

            start = datetime.now(timezone.utc)

            try:
                response, tokens = await call_model(model, effective_prompt)
                latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000

                # Record success
                self.router.record_success(model, latency)

                # Post-receive response sanitization
                if self.response_sanitizer is not None:
                    resp_result = await self.response_sanitizer.sanitize_response(
                        response
                    )
                    if resp_result.sanitized_text is not None:
                        response = resp_result.sanitized_text

                # Update budget
                if self.budget:
                    self.budget.consume(tokens)

                # Cache response
                if use_cache:
                    self._set_cached(cache_key, response, model, tokens)

                # Log response if enabled
                if self.log_responses:
                    logger.info(f"Response from {model}: {response[:200]}...")

                return response, model, tokens

            except Exception as e:
                error_str = str(e).lower()

                # Classify and record error
                if "rate limit" in error_str or "429" in error_str:
                    self.router.record_rate_limit(model)
                elif "timeout" in error_str:
                    self.router.record_timeout(model)
                elif "not found" in error_str or "no access" in error_str:
                    self.router.record_failure(model, "permanent", is_permanent=True)
                else:
                    self.router.record_failure(model, type(e).__name__)

                last_error = e
                logger.warning(f"Model {model} failed: {e}")

        raise RuntimeError(
            f"All models failed. Tried: {tried}. Last error: {last_error}"
        )

    async def complete_stream(
        self, prompt: str, tier: ModelTier = ModelTier.TIER_2, **kwargs: Any
    ) -> AsyncIterator[str]:
        """Send streaming completion request.

        Note: Streaming bypasses cache.

        Args:
            prompt: Prompt to send
            tier: Model tier
            **kwargs: Additional arguments

        Yields:
            Response chunks
        """
        if self.backend is None:
            raise RuntimeError("No LLM backend configured")

        model = self.router.get_model_for_tier(tier)
        if model is None:
            raise RuntimeError(f"No available model for tier {tier.name}")

        # Pre-send sanitization
        effective_prompt = prompt
        if self.sanitization is not None:
            san_result = await self.sanitization.process(
                prompt, {"source": "llm_stream", "tier": tier.name}
            )
            if not san_result.is_safe:
                raise ValueError(
                    f"Prompt blocked by sanitization: {san_result.classification.value}"
                )
            if san_result.sanitized_text is not None:
                effective_prompt = san_result.sanitized_text

        start = datetime.now(timezone.utc)
        total_response = []

        try:
            async for chunk in self.backend.complete_stream(
                model, effective_prompt, **kwargs
            ):
                total_response.append(chunk)
                yield chunk

            # Record success after stream completes
            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            full_response = "".join(total_response)
            tokens = self.backend.count_tokens(effective_prompt + full_response, model)

            self.router.record_success(model, latency)

            if self.budget:
                self.budget.consume(tokens)

        except Exception as e:
            self.router.record_failure(model, type(e).__name__)
            raise

    def with_sanitization(
        self,
        sanitization: SanitizationMiddleware | None = None,
        response_sanitizer: ResponseSanitizer | None = None,
    ) -> None:
        """Attach sanitization middleware to the client.

        Args:
            sanitization: Inbound prompt sanitizer.
            response_sanitizer: Outbound response sanitizer.
        """
        self.sanitization = sanitization
        self.response_sanitizer = response_sanitizer

    def clear_cache(self) -> int:
        """Clear response cache.

        Returns:
            Number of entries cleared
        """
        count = len(self.cache)
        self.cache.clear()
        return count

    def get_stats(self) -> dict[str, Any]:
        """Get client statistics."""
        return {
            "cache_entries": len(self.cache),
            "cache_enabled": self.enable_cache,
            "budget": {
                "max": self.budget.max_tokens if self.budget else None,
                "used": self.budget.used_tokens if self.budget else None,
                "remaining": self.budget.remaining if self.budget else None,
            },
            "router_stats": self.router.get_stats_summary(),
        }

    def __repr__(self) -> str:
        backend_name = type(self.backend).__name__ if self.backend else "None"
        return (
            f"LLMClientWrapper(backend={backend_name}, "
            f"cache_size={len(self.cache)}, "
            f"budget={'set' if self.budget else 'none'})"
        )


# Global client instance
_client: LLMClientWrapper | None = None


def get_client(auto_configure: bool = False) -> LLMClientWrapper:
    """Get the global LLM client.

    If ``AGENTIC_NO_LLM=1``, installs a ``MockBackend`` with an
    identifiable placeholder response and skips provider probing
    entirely.  See ``docs/NO_LLM_MODE.md``.

    Args:
        auto_configure: If True and no client exists, probe environment
            variables and set up a MultiBackend automatically.  Default
            is False so that unit tests get a backend-less client
            (placeholder mode).
    """
    global _client
    if _client is None:
        _client = LLMClientWrapper()
        from ..settings import get_settings

        if get_settings().agentic_no_llm:
            from .backends import PLACEHOLDER_RESPONSE_TEXT, MockBackend

            _client.set_backend(
                MockBackend(default_response=PLACEHOLDER_RESPONSE_TEXT)
            )
            logger.warning(
                "AGENTIC_NO_LLM=1: all LLM calls return a placeholder. "
                "Disable for production workloads."
            )
        elif auto_configure:
            from .backends import auto_configure_backend

            try:
                _client.set_backend(auto_configure_backend())
            except RuntimeError:
                pass  # No backends available — will fail at call time
    return _client


def reset_client() -> None:
    """Reset the global client (for testing)."""
    global _client
    _client = None
