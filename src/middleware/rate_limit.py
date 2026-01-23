import time
from collections import defaultdict
from fastapi import Request, HTTPException
from src.config.settings import get_settings

settings = get_settings()


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window.

    For production with multiple instances, use Redis-based rate limiting.
    """

    def __init__(self):
        self.requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request (IP or API key)."""
        # Prefer API key if present, otherwise use IP
        api_key = request.headers.get(settings.api_key_header)
        if api_key:
            return f"key:{api_key[:8]}"  # Use first 8 chars of key

        # Get real IP considering proxies
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        return f"ip:{request.client.host if request.client else 'unknown'}"

    def _cleanup_old_requests(self, client_id: str, now: float):
        """Remove requests outside the current window."""
        window_start = now - settings.rate_limit_window
        self.requests[client_id] = [
            ts for ts in self.requests[client_id]
            if ts > window_start
        ]

    def is_allowed(self, request: Request) -> tuple[bool, dict]:
        """
        Check if request is allowed under rate limit.

        Returns:
            tuple: (is_allowed, rate_limit_info)
        """
        client_id = self._get_client_id(request)
        now = time.time()

        self._cleanup_old_requests(client_id, now)

        current_requests = len(self.requests[client_id])
        remaining = max(0, settings.rate_limit_requests - current_requests)
        reset_time = int(now + settings.rate_limit_window)

        info = {
            "limit": settings.rate_limit_requests,
            "remaining": remaining,
            "reset": reset_time,
            "window": settings.rate_limit_window,
        }

        if current_requests >= settings.rate_limit_requests:
            return False, info

        # Record this request
        self.requests[client_id].append(now)
        info["remaining"] = remaining - 1

        return True, info


# Global rate limiter instance
rate_limiter = RateLimiter()


async def check_rate_limit(request: Request) -> dict:
    """
    Check rate limit and raise exception if exceeded.

    Returns rate limit info for response headers.
    """
    allowed, info = rate_limiter.is_allowed(request)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(info["reset"]),
                "Retry-After": str(info["window"]),
            },
        )

    return info
