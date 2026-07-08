from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from custos_examinis.auth.jwt import CurrentUser, get_current_user
from custos_examinis.config import Settings, get_settings
from custos_examinis.jobs.store import JobStore
from custos_examinis.llm.router import ModelRouter
from custos_examinis.middleware.rate_limit import check_sliding_window


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


def get_model_router(request: Request) -> ModelRouter:
    router: ModelRouter = request.app.state.model_router
    return router


def get_job_store(redis: Annotated[Redis, Depends(get_redis)]) -> JobStore:
    return JobStore(redis)


async def enforce_audit_rate_limit(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    allowed, retry_after = await check_sliding_window(
        redis,
        f"ratelimit:audits:{user.subject}",
        limit=settings.audit_rate_limit_per_hour,
        window_seconds=60 * 60,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="audit submission rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
