"""Smart model router with adaptive learning and production hardening."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from filelock import FileLock

from .model_stats import CircuitState, ModelStats
from .rate_limit_tracker import RateLimitTracker, _extract_provider
from .router import ModelRouter, ModelTier

# Default per-provider concurrency limits (ADR-002A)
_DEFAULT_BULKHEAD_LIMITS: dict[str, int] = {
    "ollama": 10,
    "openai": 50,
    "anthropic": 50,
    "gemini": 50,
    "gh": 30,
    "azure": 50,
}


@dataclass(frozen=True)
class ModelSelection:
    """Result of a model selection decision.

    Captures whether the returned model came from the requested tier
    (normal) or a different tier (degraded fallback). Callers can
    inspect ``is_degraded`` to log, meter, or adjust behavior.
    """

    model_name: str
    requested_tier: str
    actual_tier: str
    is_degraded: bool = False


@dataclass
class CooldownConfig:
    """Configuration for adaptive cooldowns."""

    # Base cooldown durations
    base_failure_cooldown_seconds: int = 30
    base_rate_limit_cooldown_seconds: int = 120
    base_timeout_cooldown_seconds: int = 60

    # Scaling factors
    consecutive_failure_multiplier: float = 1.5
    max_cooldown_seconds: int = 600  # 10 minutes

    # Recovery
    success_count_to_clear: int = 3


@dataclass
class SmartModelRouter(ModelRouter):
    """Production-hardened router with learning and adaptive behavior."""

    # Stats for each model
    model_stats: dict[str, ModelStats] = field(default_factory=dict)

    # Configuration
    cooldown_config: CooldownConfig = field(default_factory=CooldownConfig)

    # Persistence
    stats_file: Path | None = None
    _auto_save: bool = True

    # Cost weights (tokens per $0.001)
    model_costs: dict[str, float] = field(
        default_factory=lambda: {
            "ollama:phi4": 0.0,
            "ollama:llama3.2:latest": 0.0,
            "gh:gpt-4o-mini": 0.15,
            "gh:gpt-4o": 2.5,
        }
    )

    # ADR-002E: Rate-limit tracker with provider-aware header parsing
    rate_limit_tracker: RateLimitTracker = field(default_factory=RateLimitTracker)

    # ADR-002A: Per-provider bulkhead semaphores (cascade prevention)
    _provider_semaphores: dict[str, asyncio.Semaphore] = field(
        default_factory=dict, repr=False
    )

    # ADR-002D: Per-provider probe locks (half-open serialization)
    _probe_locks: dict[str, asyncio.Lock] = field(default_factory=dict, repr=False)

    # Last model selection result (for degraded-mode inspection)
    _last_selection: ModelSelection | None = field(default=None, repr=False)

    @property
    def last_selection(self) -> ModelSelection | None:
        """The most recent model selection result.

        Inspect ``last_selection.is_degraded`` after calling
        ``get_model_for_tier()`` to determine if cross-tier fallback
        was used.
        """
        return self._last_selection

    def __post_init__(self) -> None:
        if self.stats_file:
            self._load_stats()

    def _get_stats(self, model: str) -> ModelStats:
        """Get or create stats for a model."""
        if model not in self.model_stats:
            self.model_stats[model] = ModelStats(model_id=model)
        return self.model_stats[model]

    def _get_semaphore(self, model: str) -> asyncio.Semaphore:
        """Get or create a bulkhead semaphore for a provider."""
        provider = _extract_provider(model)
        if provider not in self._provider_semaphores:
            limit = _DEFAULT_BULKHEAD_LIMITS.get(provider, 20)
            self._provider_semaphores[provider] = asyncio.Semaphore(limit)
        return self._provider_semaphores[provider]

    def _get_probe_lock(self, model: str) -> asyncio.Lock:
        """Get or create a probe lock for half-open serialization."""
        provider = _extract_provider(model)
        if provider not in self._probe_locks:
            self._probe_locks[provider] = asyncio.Lock()
        return self._probe_locks[provider]

    def record_success(self, model: str, latency_ms: float) -> None:
        """Record a successful call."""
        stats = self._get_stats(model)
        stats.record_success(latency_ms)
        self.mark_available(model)

        if self._auto_save and self.stats_file:
            self._save_stats()

    def record_failure(
        self, model: str, error_type: str = "unknown", is_permanent: bool = False
    ) -> None:
        """Record a failed call."""
        stats = self._get_stats(model)
        stats.record_failure(error_type)

        # Apply adaptive cooldown
        cooldown = self._calculate_cooldown(stats, error_type)
        stats.set_cooldown(cooldown)

        # Mark permanently unavailable if permanent error
        if is_permanent:
            self.mark_unavailable(model)

        if self._auto_save and self.stats_file:
            self._save_stats()

    def record_rate_limit(
        self,
        model: str,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        """Record a rate limit hit with provider-aware cooldown."""
        stats = self._get_stats(model)
        cooldown = self.rate_limit_tracker.get_cooldown_seconds(
            model, headers=response_headers
        )
        stats.record_rate_limit(retry_after_seconds=cooldown)

        if self._auto_save and self.stats_file:
            self._save_stats()

    def record_timeout(self, model: str) -> None:
        """Record a timeout."""
        stats = self._get_stats(model)
        stats.record_timeout()

        cooldown = self._calculate_cooldown(stats, "timeout")
        stats.set_cooldown(cooldown)

        if self._auto_save and self.stats_file:
            self._save_stats()

    def _calculate_cooldown(self, stats: ModelStats, error_type: str) -> int:
        """Calculate adaptive cooldown duration."""
        cfg = self.cooldown_config
        if error_type == "rate_limit":
            base = cfg.base_rate_limit_cooldown_seconds
        elif error_type == "timeout":
            base = cfg.base_timeout_cooldown_seconds
        else:
            base = cfg.base_failure_cooldown_seconds
        failures = stats._consecutive_failures
        multiplier = cfg.consecutive_failure_multiplier ** min(failures, 5)

        cooldown = int(base * multiplier)
        return min(cooldown, cfg.max_cooldown_seconds)

    def _cross_tier_search(
        self,
        original_tier: ModelTier,
        max_cost: float | None = None,
    ) -> tuple[list[tuple[str, ModelStats]], ModelTier | None]:
        """Search adjacent tiers for available models.

        Returns:
            A tuple of (candidates, actual_tier). actual_tier is the tier
            that provided the candidates, or None if no candidates found.
        """
        all_tiers = sorted(ModelTier, key=lambda t: t.value)
        eligible = [
            t for t in all_tiers if t != original_tier and t != ModelTier.TIER_0
        ]

        # Sort by distance from original tier, preferring lower (degrade) first
        def tier_priority(t: ModelTier) -> tuple[int, int]:
            distance = abs(t.value - original_tier.value)
            direction = 0 if t.value < original_tier.value else 1
            return (distance, direction)

        eligible.sort(key=tier_priority)

        for tier in eligible:
            candidates = self._find_candidates_in_tier(tier, max_cost)
            if candidates:
                return candidates, tier

        return [], None

    def _find_candidates_in_tier(
        self,
        tier: ModelTier,
        max_cost: float | None = None,
    ) -> list[tuple[str, ModelStats]]:
        """Find all healthy candidate models in a single tier."""
        chain = self.get_chain(tier)
        candidates: list[tuple[str, ModelStats]] = []

        for model in chain:
            if not self.is_model_available(model):
                continue
            stats = self._get_stats(model)
            if not stats.check_circuit():
                continue
            if stats.is_in_cooldown:
                continue
            if max_cost is not None:
                cost = self.model_costs.get(model, 0.0)
                if cost > max_cost:
                    continue
            candidates.append((model, stats))

        return candidates

    def get_model_for_tier(
        self,
        tier: ModelTier,
        prefer_healthy: bool = True,
        max_cost: float | None = None,
        allow_cross_tier: bool = True,
    ) -> str | None:
        """Get best available model for a tier with cross-tier degradation.

        After calling this method, inspect ``last_selection`` to determine
        whether cross-tier fallback was used (``is_degraded=True``).
        """
        candidates = self._find_candidates_in_tier(tier, max_cost)
        actual_tier = tier
        is_degraded = False

        if not candidates and allow_cross_tier:
            candidates, cross_tier = self._cross_tier_search(tier, max_cost)
            if cross_tier is not None:
                actual_tier = cross_tier
                is_degraded = True

        if not candidates:
            self._last_selection = None
            return None

        if not prefer_healthy or len(candidates) == 1:
            selected = candidates[0][0]
            self._last_selection = ModelSelection(
                model_name=selected,
                requested_tier=tier.name,
                actual_tier=actual_tier.name,
                is_degraded=is_degraded,
            )
            return selected

        # Score candidates by health
        def score(model_stats: tuple[str, ModelStats]) -> float:
            _, stats = model_stats
            # Weight: success_rate (60%) + low latency (20%) + recency (20%)
            success_score = stats.recent_success_rate * 0.6

            # Latency score (lower is better, normalize to 0-1)
            latency = stats.avg_latency_ms
            latency_score = max(0, 1 - (latency / 10000)) * 0.2 if latency > 0 else 0.2

            # Recency score (recent successes preferred)
            recency_score = 0.2
            if stats.last_success:
                age = (datetime.now(timezone.utc) - stats.last_success).total_seconds()
                recency_score = max(0, 1 - (age / 3600)) * 0.2  # Decay over 1 hour

            return success_score + latency_score + recency_score

        candidates.sort(key=score, reverse=True)
        selected = candidates[0][0]
        self._last_selection = ModelSelection(
            model_name=selected,
            requested_tier=tier.name,
            actual_tier=actual_tier.name,
            is_degraded=is_degraded,
        )
        return selected

    def get_fallback_chain_with_health(
        self, tier: ModelTier
    ) -> list[tuple[str, float]]:
        """Get fallback chain with health scores."""
        chain = self.get_chain(tier)
        scored = []

        for model in chain:
            stats = self._get_stats(model)
            if stats.check_circuit() and not stats.is_in_cooldown:
                scored.append((model, stats.recent_success_rate))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def predict_availability(self, model: str) -> dict[str, Any]:
        """Predict model availability (dict with confidence and reason)."""
        stats = self._get_stats(model)

        # Check obvious blockers
        if not self.is_model_available(model):
            return {
                "available": False,
                "confidence": 1.0,
                "reason": "marked_unavailable",
            }

        if stats.circuit_state == CircuitState.OPEN:
            return {
                "available": False,
                "confidence": 0.9,
                "reason": "circuit_open",
                "recovery_in_seconds": stats._recovery_timeout_seconds,
            }

        if stats.is_in_cooldown:
            return {
                "available": False,
                "confidence": 0.95,
                "reason": "in_cooldown",
                "cooldown_remaining": stats.cooldown_remaining_seconds,
            }

        # Predict based on recent performance
        if stats.recent_success_rate < 0.3:
            return {
                "available": True,
                "confidence": 0.4,
                "reason": "poor_recent_performance",
                "success_rate": stats.recent_success_rate,
            }

        if stats.rate_limit_count > 5:
            return {
                "available": True,
                "confidence": 0.6,
                "reason": "rate_limit_history",
                "rate_limit_count": stats.rate_limit_count,
            }

        return {
            "available": True,
            "confidence": min(0.9, stats.recent_success_rate + 0.1),
            "reason": "healthy",
            "success_rate": stats.recent_success_rate,
        }

    def get_stats_summary(self) -> dict[str, Any]:
        """Get summary of all model stats."""
        return {
            "total_models": len(self.model_stats),
            "healthy_models": sum(1 for s in self.model_stats.values() if s.is_healthy),
            "models": {
                model: stats.to_dict() for model, stats in self.model_stats.items()
            },
        }

    def _save_stats(self) -> None:
        """Save stats to file atomically with cross-process file locking."""
        if not self.stats_file:
            return

        data = {
            "version": "1.0",
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "stats": {
                model: stats.to_dict() for model, stats in self.model_stats.items()
            },
        }

        lock = FileLock(str(self.stats_file) + ".lock")
        with lock:
            # Atomic write: write to temp file, then rename
            temp_file = self.stats_file.with_suffix(".tmp")
            temp_file.write_text(json.dumps(data, indent=2))
            temp_file.replace(self.stats_file)

    def _load_stats(self) -> None:
        """Load stats from file with cross-process file locking."""
        if not self.stats_file or not self.stats_file.exists():
            return

        lock = FileLock(str(self.stats_file) + ".lock")
        try:
            with lock:
                data = json.loads(self.stats_file.read_text())
            for model, stats_dict in data.get("stats", {}).items():
                self.model_stats[model] = ModelStats.from_dict(stats_dict)
        except (json.JSONDecodeError, KeyError):
            # Log error but continue with empty stats
            pass

    def _is_model_ready_for_attempt(self, model: str) -> bool:
        """Check if a model can accept a request right now."""
        stats = self._get_stats(model)
        if stats.circuit_state == CircuitState.HALF_OPEN:
            if self._get_probe_lock(model).locked():
                return False
        semaphore = self._get_semaphore(model)
        if semaphore.locked():
            return False

        return True

    async def _execute_call(
        self, caller: Callable[[str, str], Any], model: str, prompt: str
    ) -> Any:
        """Execute a model call with bulkhead and probe-lock guards."""
        stats = self._get_stats(model)
        semaphore = self._get_semaphore(model)
        async with semaphore:
            if stats.circuit_state == CircuitState.HALF_OPEN:
                async with self._get_probe_lock(model):
                    return await caller(model, prompt)
            return await caller(model, prompt)

    def _classify_and_record_error(self, model: str, error: Exception) -> None:
        """Classify error and record with appropriate cooldown."""
        error_str = str(error).lower()
        response_headers = getattr(error, "headers", None)
        headers_dict: dict[str, str] | None = None
        if isinstance(response_headers, dict):
            headers_dict = dict(response_headers)
            self.rate_limit_tracker.update_from_headers(model, headers_dict)

        if "rate limit" in error_str or "429" in error_str:
            self.record_rate_limit(model, headers_dict)
        elif "timeout" in error_str:
            self.record_timeout(model)
        elif "not found" in error_str or "no access" in error_str:
            self.record_failure(model, "permanent", is_permanent=True)
        else:
            self.record_failure(model, type(error).__name__)

    async def call_with_fallback(
        self,
        caller: Callable[[str, str], Any],
        prompt: str,
        tier: ModelTier,
        max_retries: int = 3,
    ) -> tuple[str, Any]:
        """Call a model with automatic fallback and production hardening."""
        tried: list[str] = []
        last_error: Exception | None = None

        for _ in range(max_retries):
            model = self.get_model_for_tier(tier)
            if model is None or model in tried:
                break

            tried.append(model)

            if not self._is_model_ready_for_attempt(model):
                continue

            start_mono = time.monotonic()
            try:
                response = await self._execute_call(caller, model, prompt)
                latency = (time.monotonic() - start_mono) * 1000
                self.record_success(model, latency)
                return model, response
            except Exception as e:
                self._classify_and_record_error(model, e)
                last_error = e

        raise RuntimeError(
            f"All models failed. Tried: {tried}. Last error: {last_error}"
        )

    def __repr__(self) -> str:
        healthy = sum(1 for s in self.model_stats.values() if s.is_healthy)
        return (
            f"SmartModelRouter(models={len(self.model_stats)}, "
            f"healthy={healthy}, "
            f"stats_file={self.stats_file})"
        )


# Global smart router instance
_smart_router: SmartModelRouter | None = None


def get_smart_router(stats_file: Path | None = None) -> SmartModelRouter:
    """Get the global smart router."""
    global _smart_router
    if _smart_router is None:
        _smart_router = SmartModelRouter(stats_file=stats_file)
    return _smart_router


def reset_smart_router() -> None:
    """Reset the global smart router (for testing)."""
    global _smart_router
    _smart_router = None
