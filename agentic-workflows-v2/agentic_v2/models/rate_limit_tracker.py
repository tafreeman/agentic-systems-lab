"""Rate-limit tracking with provider-aware header parsing (ADR-002E).

Implements dual token-bucket tracking (RPM + TPM) per provider and parses
provider-specific rate-limit headers to set precise cooldown durations
instead of the flat 120s default.

Key design decisions:
- Provider-specific header parsing (OpenAI, Anthropic, Azure, Gemini)
- Fallback to exponential backoff with jitter when headers are unreliable
- Dual buckets (requests + tokens) per provider
- Thread-safe via monotonic clock (ADR-002C)
"""

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


@dataclass
class TokenBucket:
    """Token bucket for rate limiting.

    Tracks available capacity using the token bucket algorithm. Tokens
    are consumed on each request and refilled at a steady rate. Uses
    monotonic clock for timing (ADR-002C).
    """

    capacity: int
    refill_rate: float  # tokens per second
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.capacity)
        self._last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens.

        Returns True if successful.
        """
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def remaining(self) -> float:
        """Return current available tokens."""
        self._refill()
        return self._tokens

    def time_until_available(self, tokens: int = 1) -> float:
        """Seconds until `tokens` become available.

        0 if already available.
        """
        self._refill()
        if self._tokens >= tokens:
            return 0.0
        deficit = tokens - self._tokens
        return deficit / self.refill_rate if self.refill_rate > 0 else float("inf")

    def reset(self, remaining: int, reset_seconds: float) -> None:
        """Reset bucket state from provider headers.

        Args:
            remaining: Remaining capacity reported by provider
            reset_seconds: Seconds until full capacity resets
        """
        self._tokens = float(min(remaining, self.capacity))
        if reset_seconds > 0 and remaining < self.capacity:
            self.refill_rate = (self.capacity - remaining) / reset_seconds
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        """Refill bucket based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now


@dataclass
class ProviderRateLimits:
    """Rate-limit state for a single provider."""

    provider: str
    rpm_bucket: TokenBucket  # Requests per minute
    tpm_bucket: TokenBucket | None = None  # Tokens per minute (if tracked)
    last_retry_after: float | None = None  # Last Retry-After value seen
    total_requests: int = 0  # Total requests for throttle computation
    recent_errors: int = 0  # Recent errors for throttle computation


# Default rate limits per provider (conservative estimates)
_DEFAULT_LIMITS: dict[str, dict[str, int]] = {
    "openai": {"rpm": 60, "tpm": 90_000},
    "anthropic": {"rpm": 60, "tpm": 80_000},
    "gemini": {"rpm": 60, "tpm": 100_000},
    "gh": {"rpm": 15, "tpm": 150_000},  # GitHub Models
    "azure": {"rpm": 60, "tpm": 120_000},
    "ollama": {"rpm": 1000, "tpm": 1_000_000},  # Local, effectively unlimited
}


@dataclass
class RateLimitTracker:
    """Track rate limits per provider using dual token buckets (ADR-002E).

    Parses provider-specific rate-limit headers to maintain accurate
    capacity tracking. Falls back to conservative defaults when headers
    are absent or unreliable.
    """

    _providers: dict[str, ProviderRateLimits] = field(default_factory=dict)

    def get_provider(self, model: str) -> ProviderRateLimits:
        """Get or create rate-limit state for a model's provider."""
        provider = _extract_provider(model)
        if provider not in self._providers:
            limits = _DEFAULT_LIMITS.get(provider, {"rpm": 30, "tpm": 50_000})
            self._providers[provider] = ProviderRateLimits(
                provider=provider,
                rpm_bucket=TokenBucket(
                    capacity=limits["rpm"],
                    refill_rate=limits["rpm"] / 60.0,
                ),
                tpm_bucket=TokenBucket(
                    capacity=limits["tpm"],
                    refill_rate=limits["tpm"] / 60.0,
                ),
            )
        return self._providers[provider]

    def can_request(self, model: str, estimated_tokens: int = 1000) -> bool:
        """Check if a request is allowed under current rate limits."""
        state = self.get_provider(model)
        if not state.rpm_bucket.consume():
            return False
        if state.tpm_bucket and not state.tpm_bucket.consume(estimated_tokens):
            return False
        return True

    def parse_retry_after(self, headers: dict[str, str]) -> int | None:
        """Parse Retry-After header (RFC 7231 Section 7.1.3).

        Supports both delta-seconds and HTTP-date formats.

        Args:
            headers: Response headers (case-insensitive keys)

        Returns:
            Retry-after seconds, or None if header absent/unparseable
        """
        # Normalize header keys to lowercase
        lower_headers = {k.lower(): v for k, v in headers.items()}
        retry_after = lower_headers.get("retry-after")
        if not retry_after:
            return None

        try:
            seconds = int(retry_after)
            # Sanity check: reject negative or absurdly large values
            if 0 < seconds <= 3600:
                return seconds
        except ValueError:
            pass

        # Try HTTP-date format (RFC 7231 Section 7.1.3)
        try:
            dt = parsedate_to_datetime(retry_after)
            delta = (dt - datetime.now(timezone.utc)).total_seconds()
            seconds = int(max(0, delta))
            if 0 < seconds <= 3600:
                return seconds
        except (ValueError, TypeError):
            pass

        return None

    def update_from_headers(self, model: str, headers: dict[str, str]) -> int | None:
        """Parse provider-specific rate-limit headers and update buckets.

        Returns the recommended cooldown seconds if rate-limited, else None.

        Supported header formats:
        - OpenAI: x-ratelimit-remaining-requests, x-ratelimit-reset-requests,
                  x-ratelimit-remaining-tokens, x-ratelimit-reset-tokens
        - Anthropic: retry-after, x-ratelimit-limit-requests,
                     x-ratelimit-remaining-requests
        - Azure: retry-after, x-ratelimit-remaining-requests
        """
        lower_headers = {k.lower(): v for k, v in headers.items()}
        provider = _extract_provider(model)
        state = self.get_provider(model)

        # Parse Retry-After first (universal)
        retry_after = self.parse_retry_after(headers)
        if retry_after is not None:
            state.last_retry_after = float(retry_after)
            return retry_after

        # Provider-specific header parsing
        if provider in ("openai", "gh", "azure"):
            return self._parse_openai_headers(state, lower_headers)
        elif provider == "anthropic":
            return self._parse_anthropic_headers(state, lower_headers)

        return None

    def get_cooldown_seconds(
        self,
        model: str,
        headers: dict[str, str] | None = None,
        default_cooldown: int = 120,
    ) -> int:
        """Get the appropriate cooldown for a rate-limited model.

        Priority: provider Retry-After > parsed headers > default + jitter.

        Args:
            model: Model identifier
            headers: Response headers (if available)
            default_cooldown: Fallback cooldown seconds

        Returns:
            Recommended cooldown in seconds
        """
        if headers:
            from_headers = self.update_from_headers(model, headers)
            if from_headers is not None:
                return from_headers

        # Fallback: exponential backoff with jitter
        state = self.get_provider(model)
        if state.last_retry_after is not None:
            # Use last known retry-after as base estimate
            base = int(state.last_retry_after)
        else:
            base = default_cooldown

        # Add 10-25% jitter to prevent thundering herd
        jitter = random.uniform(0.1, 0.25)
        return int(base * (1 + jitter))

    def record_request(self, model: str) -> None:
        """Record a request for throttle factor computation.

        Args:
            model: Model identifier (provider extracted automatically)
        """
        state = self.get_provider(model)
        state.total_requests += 1

    def record_error(self, model: str) -> None:
        """Record an error for throttle factor computation.

        Args:
            model: Model identifier (provider extracted automatically)
        """
        state = self.get_provider(model)
        state.recent_errors += 1

    def compute_throttle_factor(self, model: str) -> float:
        """Return 0.0-1.0 throttle factor based on recent error rate.

        A throttle factor of 0.0 means no throttling; 1.0 means maximum
        throttling. The factor scales linearly at 2x the error rate,
        capped at 1.0.

        Args:
            model: Model identifier (provider extracted automatically)

        Returns:
            Throttle factor between 0.0 and 1.0
        """
        provider = _extract_provider(model)
        state = self._providers.get(provider)
        if not state or state.total_requests < 10:
            return 0.0  # Not enough data
        error_rate = state.recent_errors / state.total_requests
        return min(1.0, error_rate * 2)

    def _parse_openai_headers(
        self, state: ProviderRateLimits, headers: dict[str, str]
    ) -> int | None:
        """Parse OpenAI-style rate-limit headers."""
        remaining_requests = _safe_int(headers.get("x-ratelimit-remaining-requests"))
        reset_requests = _parse_duration(headers.get("x-ratelimit-reset-requests"))
        remaining_tokens = _safe_int(headers.get("x-ratelimit-remaining-tokens"))
        reset_tokens = _parse_duration(headers.get("x-ratelimit-reset-tokens"))

        # Update RPM bucket
        if remaining_requests is not None and reset_requests is not None:
            state.rpm_bucket.reset(remaining_requests, reset_requests)

        # Update TPM bucket
        if (
            state.tpm_bucket
            and remaining_tokens is not None
            and reset_tokens is not None
        ):
            state.tpm_bucket.reset(remaining_tokens, reset_tokens)

        # If remaining is 0, return the reset time as cooldown
        if remaining_requests is not None and remaining_requests <= 0:
            return int(reset_requests) if reset_requests else None

        return None

    def _parse_anthropic_headers(
        self, state: ProviderRateLimits, headers: dict[str, str]
    ) -> int | None:
        """Parse Anthropic-style rate-limit headers."""
        remaining = _safe_int(headers.get("x-ratelimit-remaining-requests"))

        if remaining is not None:
            state.rpm_bucket.reset(remaining, 60.0)  # Anthropic resets per minute

        if remaining is not None and remaining <= 0:
            # Anthropic doesn't always give a precise reset time
            return 60  # Conservative: wait one minute

        return None


def _extract_provider(model: str) -> str:
    """Extract provider name from model identifier.

    Supports formats: 'provider:model', 'provider/model', plain 'model'.
    """
    if ":" in model:
        return model.split(":")[0].lower()
    if "/" in model:
        return model.split("/")[0].lower()
    return "unknown"


def _safe_int(value: str | None) -> int | None:
    """Parse an integer from a header value, returning None on failure."""
    if value is None:
        return None
    try:
        result = int(value)
        # Azure is known to return -1 and 0 incorrectly
        return result if result >= 0 else None
    except (ValueError, TypeError):
        return None


def _parse_duration(value: str | None) -> float | None:
    """Parse a duration string like '6s', '1m30s', '500ms' to seconds."""
    if value is None:
        return None

    try:
        # Try plain seconds first
        return float(value)
    except ValueError:
        pass

    # Parse OpenAI-style duration strings: "6s", "1m0s", "200ms"
    total = 0.0
    remaining = value.strip()

    # Minutes
    if "m" in remaining and "ms" not in remaining:
        parts = remaining.split("m", 1)
        try:
            total += float(parts[0]) * 60
        except ValueError:
            return None
        remaining = parts[1]

    # Seconds
    if "s" in remaining and "ms" not in remaining:
        parts = remaining.split("s", 1)
        try:
            total += float(parts[0])
        except ValueError:
            pass
        remaining = parts[1] if len(parts) > 1 else ""

    # Milliseconds
    if "ms" in remaining:
        parts = remaining.split("ms", 1)
        try:
            total += float(parts[0]) / 1000
        except ValueError:
            pass

    return total if total > 0 else None
