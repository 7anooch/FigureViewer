from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class BrowseBudget:
    """In-session cache / prefetch budget driven by browse pace."""

    cache_size: int
    prefetch_radius: int


class BrowsePacing:
    """Expand cache/prefetch during fast flipping; decay toward a base when idle.

    No persistent logging — budget is session-local only.
    """

    MIN_CACHE = 15
    BASE_CACHE = 32
    MAX_CACHE = 80
    BASE_PREFETCH = 4
    MAX_PREFETCH = 10
    FAST_INTERVAL_S = 0.35
    FAST_STREAK = 3
    IDLE_S = 10.0
    DECAY_CACHE_STEP = 8
    DECAY_PREFETCH_STEP = 1

    def __init__(self) -> None:
        self._cache_size = self.BASE_CACHE
        self._prefetch_radius = self.BASE_PREFETCH
        self._last_navigate = 0.0
        self._fast_streak = 0

    @property
    def budget(self) -> BrowseBudget:
        return BrowseBudget(self._cache_size, self._prefetch_radius)

    def note_navigate(self) -> BrowseBudget:
        now = time.monotonic()
        if self._last_navigate > 0 and (now - self._last_navigate) <= self.FAST_INTERVAL_S:
            self._fast_streak += 1
        else:
            self._fast_streak = 1
        self._last_navigate = now

        if self._fast_streak >= self.FAST_STREAK:
            # Ramp toward max while the user keeps flipping quickly.
            self._cache_size = min(self.MAX_CACHE, self._cache_size + 8)
            self._prefetch_radius = min(self.MAX_PREFETCH, self._prefetch_radius + 1)
        return self.budget

    def seconds_idle(self) -> float:
        if self._last_navigate <= 0:
            return 0.0
        return time.monotonic() - self._last_navigate

    def decay_if_idle(self) -> BrowseBudget | None:
        """Shrink toward BASE_* after IDLE_S with no navigation. Returns new budget if changed."""
        if self.seconds_idle() < self.IDLE_S:
            return None
        if (
            self._cache_size <= self.BASE_CACHE
            and self._prefetch_radius <= self.BASE_PREFETCH
        ):
            return None

        new_cache = max(self.BASE_CACHE, self._cache_size - self.DECAY_CACHE_STEP)
        # Never below hard floor even if BASE is lowered later.
        new_cache = max(self.MIN_CACHE, new_cache)
        new_prefetch = max(self.BASE_PREFETCH, self._prefetch_radius - self.DECAY_PREFETCH_STEP)
        if new_cache == self._cache_size and new_prefetch == self._prefetch_radius:
            return None
        self._cache_size = new_cache
        self._prefetch_radius = new_prefetch
        self._fast_streak = 0
        return self.budget
