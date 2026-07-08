from collections.abc import AsyncIterator

import pytest
from fakeredis import aioredis
from httpx import ASGITransport, AsyncClient

from custos_examinis.auth.jwt import CurrentUser, get_current_user
from custos_examinis.domain.finding import FindingsBatch
from custos_examinis.llm.router import ModelRouter
from custos_examinis.main import app
from tests.fakes.fake_chat_model import ScriptedChatModel

TEST_USER = CurrentUser(subject="test-user")


def _fake_router() -> ModelRouter:
    empty = FindingsBatch(findings=[])
    return ModelRouter.from_models(
        {
            "deep_reasoning": [ScriptedChatModel(structured_response=empty)],
            "broad_review": [ScriptedChatModel(structured_response=empty)],
            "triage": [ScriptedChatModel(text_response="unused")],
            "summarize": [ScriptedChatModel(text_response="No findings.")],
        }
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    fake_redis = aioredis.FakeRedis(decode_responses=True)
    app.state.redis = fake_redis
    app.state.model_router = _fake_router()
    app.dependency_overrides[get_current_user] = lambda: TEST_USER

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client

    app.dependency_overrides.clear()
    await fake_redis.aclose()
