"""In-memory TTL cache with LRU eviction for embeddings and search results."""

import asyncio
import hashlib
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Sentinel used to distinguish "not cached" from a cached falsy value.
_MISSING = object()


@dataclass
class CacheEntry(Generic[T]):
    """A cache entry with value, expiry time, and access tracking."""

    value: T
    expires_at: float
    last_accessed: float


class TTLCache(Generic[T]):
    """
    Thread-safe TTL cache with LRU eviction.

    Features:
    - Time-to-live (TTL) for automatic expiration
    - LRU eviction when max size reached
    - Background cleanup of expired entries
    - Hash-based key generation for complex inputs
    """

    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0):
        """
        Initialize the cache.

        Args:
            max_size: Maximum number of entries before LRU eviction
            default_ttl: Default time-to-live in seconds (default: 5 minutes)
        """
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = threading.RLock()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        # Per-key async locks to prevent cache stampede on get_or_set_async
        self._inflight: dict[str, asyncio.Lock] = {}

    @staticmethod
    def generate_key(*args: Any, **kwargs: Any) -> str:
        """Generate a cache key from arguments."""
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    def _get_raw(self, key: str) -> Any:
        """
        Internal get that returns _MISSING on a cache miss (including expired).
        Distinguishes a cached falsy value from "not present".
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return _MISSING

            # Check expiration
            if time.time() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                logger.debug(f"[CACHE] Key {key[:8]}... expired")
                return _MISSING

            # Update access time and move to end (most recently used)
            entry.last_accessed = time.time()
            self._cache.move_to_end(key)
            self._hits += 1
            logger.debug(f"[CACHE] Hit for key {key[:8]}...")
            return entry.value

    def get(self, key: str) -> T | None:
        """
        Get a value from the cache.

        Returns None if key doesn't exist or has expired.
        Note: also returns None for a cached None value — use _get_raw if
        you need to distinguish those cases.
        """
        result = self._get_raw(key)
        return None if result is _MISSING else result  # type: ignore[return-value]

    def set(self, key: str, value: T, ttl: float | None = None) -> None:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            # Remove oldest entries if at capacity
            while len(self._cache) >= self._max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                logger.debug(f"[CACHE] Evicted LRU entry {oldest_key[:8]}...")

            self._cache[key] = CacheEntry(
                value=value,
                expires_at=expires_at,
                last_accessed=time.time(),
            )
            logger.debug(f"[CACHE] Set key {key[:8]}... with TTL {ttl}s")

    def get_or_set(
        self, key: str, factory: Callable[..., Any], ttl: float | None = None
    ) -> T:
        """
        Get a value from cache, or compute and cache it if missing.

        Args:
            key: Cache key
            factory: Callable that produces the value if not cached
            ttl: Time-to-live in seconds
        """
        result = self._get_raw(key)
        if result is not _MISSING:
            return result  # type: ignore[return-value]

        value = factory()
        self.set(key, value, ttl)
        return value

    async def get_or_set_async(
        self,
        key: str,
        factory: Callable[..., Any],
        ttl: float | None = None,
    ) -> T:
        """
        Async version of get_or_set with per-key locking to prevent stampede.

        Only one coroutine will call factory() for a given key; others wait
        and receive the cached result.

        Args:
            key: Cache key
            factory: Async callable that produces the value if not cached
            ttl: Time-to-live in seconds
        """
        result = self._get_raw(key)
        if result is not _MISSING:
            return result  # type: ignore[return-value]

        # Ensure a per-key lock exists (create lazily; not thread-safe here
        # but asyncio is single-threaded per event loop so this is fine).
        if key not in self._inflight:
            self._inflight[key] = asyncio.Lock()
        key_lock = self._inflight[key]

        async with key_lock:
            # Re-check after acquiring the lock — another coroutine may have
            # already populated the entry while we were waiting.
            result = self._get_raw(key)
            if result is not _MISSING:
                return result  # type: ignore[return-value]

            value = await factory()
            self.set(key, value, ttl)
            # Clean up the per-key lock once done.
            self._inflight.pop(key, None)
            return value

    def delete(self, key: str) -> bool:
        """Delete a key from the cache. Returns True if key existed."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info("[CACHE] Cleared all entries")

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        now = time.time()
        removed = 0
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() if now > entry.expires_at
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1
        if removed > 0:
            logger.info(f"[CACHE] Cleaned up {removed} expired entries")
        return removed

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "default_ttl": self._default_ttl,
            }


@lru_cache(maxsize=1)
def get_embedding_cache() -> TTLCache[list[list[float]]]:
    """Get the global embedding cache (15 minute TTL)."""
    cache: TTLCache[list[list[float]]] = TTLCache(max_size=500, default_ttl=900.0)
    logger.info("[CACHE] Initialized embedding cache")
    return cache


@lru_cache(maxsize=1)
def get_search_cache() -> TTLCache[list[dict]]:
    """Get the global search result cache (5 minute TTL)."""
    cache: TTLCache[list[dict]] = TTLCache(max_size=200, default_ttl=300.0)
    logger.info("[CACHE] Initialized search cache")
    return cache


@lru_cache(maxsize=1)
def get_llm_cache() -> TTLCache[str]:
    """Get the global LLM response cache (10 minute TTL)."""
    cache: TTLCache[str] = TTLCache(max_size=100, default_ttl=600.0)
    logger.info("[CACHE] Initialized LLM cache")
    return cache
