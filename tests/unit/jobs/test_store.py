import json
from collections.abc import AsyncIterator

import pytest
from fakeredis import aioredis
from fakeredis.aioredis import FakeRedis

from custos_examinis.costs.tracker import TokenUsageSummary
from custos_examinis.domain.report import AuditReport
from custos_examinis.jobs.store import JobStatus, JobStore


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeRedis]:
    redis = aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


@pytest.fixture
def store(redis_client: FakeRedis) -> JobStore:
    return JobStore(redis_client)


async def test_create_then_get_round_trips_a_queued_job(store: JobStore) -> None:
    created = await store.create("audit-1", owner="user-1")
    assert created.status == JobStatus.QUEUED

    fetched = await store.get("audit-1")
    assert fetched is not None
    assert fetched.owner == "user-1"
    assert fetched.status == JobStatus.QUEUED


async def test_get_returns_none_for_unknown_id(store: JobStore) -> None:
    assert await store.get("does-not-exist") is None


async def test_mark_running_then_completed_updates_status_and_report(store: JobStore) -> None:
    await store.create("audit-1", owner="user-1")
    await store.mark_running("audit-1")
    running = await store.get("audit-1")
    assert running is not None
    assert running.status == JobStatus.RUNNING

    report = AuditReport.build(
        audit_id="audit-1",
        summary="done",
        findings=[],
        agent_errors=[],
        token_usage=TokenUsageSummary(),
    )
    await store.mark_completed("audit-1", report)

    completed = await store.get("audit-1")
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED
    assert completed.report is not None
    assert completed.report.summary == "done"


async def test_mark_failed_records_the_error(store: JobStore) -> None:
    await store.create("audit-1", owner="user-1")
    await store.mark_failed("audit-1", "boom")

    failed = await store.get("audit-1")
    assert failed is not None
    assert failed.status == JobStatus.FAILED
    assert failed.error == "boom"


async def test_append_progress_accumulates_node_names_in_order(store: JobStore) -> None:
    await store.create("audit-1", owner="user-1")

    await store.append_progress("audit-1", "vulnerability_agent")
    await store.append_progress("audit-1", "code_quality_agent")

    job = await store.get("audit-1")
    assert job is not None
    assert job.progress == ["vulnerability_agent", "code_quality_agent"]


async def test_append_progress_publishes_on_the_job_channel(
    store: JobStore, redis_client: FakeRedis
) -> None:
    pubsub = redis_client.pubsub()
    await store.create("audit-1", owner="user-1")
    await pubsub.subscribe(store.channel("audit-1"))
    await pubsub.get_message(timeout=1)  # subscribe acknowledgement

    await store.append_progress("audit-1", "guardrail")

    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    assert message is not None
    assert json.loads(message["data"]) == {"type": "progress", "node": "guardrail"}

    await pubsub.unsubscribe(store.channel("audit-1"))
    await pubsub.aclose()  # type: ignore[no-untyped-call]
