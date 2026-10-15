"""
In-Memory Sliding-Window Rate Limiter.
Tracks per-client request timestamps to enforce rate limits and prevent abuse.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    """
    Structured outcome of a rate limit evaluation.
    """
    allowed: bool
    limit: int
    remaining: int
    reset_after: float  # Seconds until the oldest request expires


class InMemoryRateLimiter:
    """
    Sliding-window rate limiter using a double-ended queue (deque) per client.
    """

    def __init__(self, max_requests: int = 5, window_seconds: float = 60.0):
        """
        Args:
            max_requests: Maximum number of allowed requests in the time window.
            window_seconds: Duration of the sliding window in seconds.
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Maps client_id -> deque of Unix timestamps
        self._history = defaultdict(deque)

    def check(self, client_id: str) -> RateLimitResult:
        """
        Evaluates whether a request from the given client_id is allowed.
        
        Args:
            client_id: Unique client identifier (e.g., client IP address).

        Returns:
            RateLimitResult containing allow status, remaining quota, and reset time.
        """
        now = time.time()
        queue = self._history[client_id]

        # 1. Evict any timestamps older than our sliding window
        cutoff = now - self.window_seconds
        while queue and queue[0] <= cutoff:
            queue.popleft()

        # 2. Check if the client has exceeded the limit
        if len(queue) >= self.max_requests:
            oldest_timestamp = queue[0]
            # Time remaining until the oldest timestamp slides out of the window
            reset_after = max(0.0, (oldest_timestamp + self.window_seconds) - now)
            return RateLimitResult(
                allowed=False,
                limit=self.max_requests,
                remaining=0,
                reset_after=round(reset_after, 2),
            )

        # 3. Request is allowed: record timestamp and calculate remaining quota
        queue.append(now)
        remaining = self.max_requests - len(queue)

        return RateLimitResult(
            allowed=True,
            limit=self.max_requests,
            remaining=remaining,
            reset_after=round(self.window_seconds, 2),
        )


# Global rate limiter instance: 5 requests per 60 seconds per client
rate_limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60.0)