"""
Models module - Model routing and statistics.

Exports:
- Routing: ModelRouter, SmartModelRouter, ModelTier, FallbackChain
- Stats: ModelStats, CircuitState, LatencyPercentiles, CooldownConfig
- Rate Limits: RateLimitTracker, TokenBucket (ADR-002E)
- Client: LLMClientWrapper, LLMBackend, TokenBudget
- Globals: get_router, get_smart_router, get_client
"""

from .backends import (
    AnthropicBackend,
    GeminiBackend,
    GitHubModelsBackend,
    MockBackend,
    MultiBackend,
    OllamaBackend,
    OpenAIBackend,
    auto_configure_backend,
    get_backend,
)
from .client import (
    CachedResponse,
    LLMBackend,
    LLMClientWrapper,
    TokenBudget,
    get_client,
    reset_client,
    retry_with_jitter,
)
from .model_stats import CircuitState, LatencyPercentiles, ModelStats
from .rate_limit_tracker import RateLimitTracker, TokenBucket
from .router import (
    DEFAULT_CHAINS,
    ChainBuilder,
    FallbackChain,
    ModelRouter,
    ModelTier,
    ScopedRouter,
    get_router,
    reset_router,
)
from .smart_router import (
    CooldownConfig,
    ModelSelection,
    SmartModelRouter,
    get_smart_router,
    reset_smart_router,
)

__all__ = [
    # Stats
    "CircuitState",
    "LatencyPercentiles",
    "ModelStats",
    # Router
    "ModelTier",
    "FallbackChain",
    "ChainBuilder",
    "ModelRouter",
    "ScopedRouter",
    "DEFAULT_CHAINS",
    "get_router",
    "reset_router",
    # Rate-limit tracker (ADR-002E)
    "RateLimitTracker",
    "TokenBucket",
    # Smart router
    "CooldownConfig",
    "ModelSelection",
    "SmartModelRouter",
    "get_smart_router",
    "reset_smart_router",
    # Client
    "LLMBackend",
    "TokenBudget",
    "CachedResponse",
    "LLMClientWrapper",
    "retry_with_jitter",
    "get_client",
    "reset_client",
    # Backends
    "GitHubModelsBackend",
    "OpenAIBackend",
    "AnthropicBackend",
    "GeminiBackend",
    "OllamaBackend",
    "MultiBackend",
    "MockBackend",
    "get_backend",
    "auto_configure_backend",
]
