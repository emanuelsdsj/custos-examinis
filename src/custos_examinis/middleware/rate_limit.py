import time

from redis.asyncio import Redis
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send


async def check_sliding_window(
    redis: Redis,
    key: str,
    *,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds) using a Redis sorted-set sliding window."""
    now = time.time()
    window_start = now - window_seconds
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zcard(key)
    pipe.zadd(key, {f"{now}:{id(now)}": now})
    pipe.expire(key, window_seconds)
    results = await pipe.execute()
    count = results[1]

    if count >= limit:
        oldest = await redis.zrange(key, 0, 0, withscores=True)
        oldest_score = float(oldest[0][1]) if oldest else now
        retry_after = int(window_seconds - (now - oldest_score)) if oldest else window_seconds
        await redis.zrem(key, f"{now}:{id(now)}")
        return False, max(retry_after, 1)

    return True, 0


class RateLimitMiddleware:
    """Generic per-client-IP sliding-window limiter for all routes.

    Reads the Redis client from `request.app.state.redis` at call time rather
    than capturing one at construction, so tests can swap in a fake by setting
    `app.state.redis` without rebuilding the middleware stack.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        limit: int,
        window_seconds: int = 60,
    ) -> None:
        self.app = app
        self.limit = limit
        self.window_seconds = window_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        redis: Redis = request.app.state.redis
        client_key = f"ratelimit:generic:{request.client.host if request.client else 'unknown'}"
        allowed, retry_after = await check_sliding_window(
            redis, client_key, limit=self.limit, window_seconds=self.window_seconds
        )
        if not allowed:
            response: Response = JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
