import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from fakeredis import aioredis
from fakeredis.aioredis import FakeRedis

from custos_examinis.costs.tracker import TokenUsageSummary
from custos_examinis.domain.report import AuditReport
from custos_examinis.jobs.events import stream_audit_events
from custos_examinis.jobs.store import JobStore


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeRedis]:
    redis = aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


@pytest.fixture
def store(redis_client: FakeRedis) -> JobStore:
    return JobStore(redis_client)


def _report(audit_id: str) -> AuditReport:
    return AuditReport.build(
        audit_id=audit_id,
        summary="done",
        findings=[],
        agent_errors=[],
        token_usage=TokenUsageSummary(),
    )


async def test_unknown_audit_id_yields_nothing(store: JobStore, redis_client: FakeRedis) -> None:
    events = [chunk async for chunk in stream_audit_events("missing", store, redis_client)]
    assert events == []


async def test_already_completed_job_replays_progress_then_final_status(
    store: JobStore, redis_client: FakeRedis
) -> None:
    await store.create("audit-1", owner="user-1")
    await store.append_progress("audit-1", "vulnerability_agent")
    await store.append_progress("audit-1", "guardrail")
    await store.mark_completed("audit-1", _report("audit-1"))

    events = [chunk async for chunk in stream_audit_events("audit-1", store, redis_client)]

    assert events == [
        'event: progress\ndata: {"node": "vulnerability_agent"}\n\n',
        'event: progress\ndata: {"node": "guardrail"}\n\n',
        'event: status\ndata: {"status": "completed", "error": null}\n\n',
    ]


async def test_live_progress_is_streamed_as_it_is_published(
    store: JobStore, redis_client: FakeRedis
) -> None:
    await store.create("audit-1", owner="user-1")
    await store.mark_running("audit-1")

    async def _drive() -> None:
        await asyncio.sleep(0.05)
        await store.append_progress("audit-1", "vulnerability_agent")
        await asyncio.sleep(0.05)
        await store.append_progress("audit-1", "guardrail")
        await asyncio.sleep(0.05)
        await store.mark_completed("audit-1", _report("audit-1"))

    driver = asyncio.create_task(_drive())
    events = [chunk async for chunk in stream_audit_events("audit-1", store, redis_client)]
    await driver

    assert len(events) == 3
    assert "vulnerability_agent" in events[0]
    assert "guardrail" in events[1]
    assert "status" in events[2] and "completed" in events[2]


async def test_duplicate_progress_publish_is_not_emitted_twice(
    store: JobStore, redis_client: FakeRedis
) -> None:
    """A node already present in the stored snapshot could still arrive again
    on the pub/sub channel, since the subscription is opened before the
    snapshot is read to avoid missing events, not to avoid double-delivery.
    The generator must dedupe by node name rather than replaying it.
    """
    await store.create("audit-1", owner="user-1")
    await store.append_progress("audit-1", "vulnerability_agent")
    await store.mark_running("audit-1")

    async def _drive() -> None:
        await asyncio.sleep(0.05)
        await redis_client.publish(
            store.channel("audit-1"),
            json.dumps({"type": "progress", "node": "vulnerability_agent"}),
        )
        await asyncio.sleep(0.05)
        await store.mark_completed("audit-1", _report("audit-1"))

    driver = asyncio.create_task(_drive())
    events = [chunk async for chunk in stream_audit_events("audit-1", store, redis_client)]
    await driver

    assert len(events) == 2
    assert "vulnerability_agent" in events[0]
    assert "status" in events[1]


async def test_failed_job_terminates_the_stream_with_the_error(
    store: JobStore, redis_client: FakeRedis
) -> None:
    await store.create("audit-1", owner="user-1")
    await store.mark_failed("audit-1", "boom")

    events = [chunk async for chunk in stream_audit_events("audit-1", store, redis_client)]

    assert len(events) == 1
    assert "status" in events[0]
    assert "boom" in events[0]
