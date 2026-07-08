from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from custos_examinis.api.routers import audits, health
from custos_examinis.config import get_settings
from custos_examinis.llm.router import ModelRouter
from custos_examinis.logging import configure_logging, get_logger
from custos_examinis.middleware.correlation import CorrelationIdMiddleware
from custos_examinis.middleware.rate_limit import RateLimitMiddleware
from custos_examinis.middleware.timing import TimingMiddleware

settings = get_settings()
configure_logging(debug=settings.debug)
logger = get_logger(__name__)

redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
model_router = ModelRouter(settings)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await redis_client.ping()
    logger.info("startup_complete")
    yield
    await redis_client.aclose()
    logger.info("shutdown_complete")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)
app.state.redis = redis_client
app.state.model_router = model_router

app.add_middleware(TimingMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    limit=settings.rate_limit_requests_per_minute,
    window_seconds=60,
)

app.include_router(health.router)
app.include_router(audits.router)
