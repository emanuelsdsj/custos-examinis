from collections.abc import AsyncIterator

import pytest
from fakeredis import aioredis

from custos_examinis.costs.tracker import TokenUsageSummary
from custos_examinis.domain.report import AuditReport
from custos_examinis.jobs.store import JobStatus, JobStore


@pytest.fixture
async def store() -> AsyncIterator[JobStore]:
    redis = aioredis.FakeRedis(decode_responses=True)
    yield JobStore(redis)
    await redis.aclose()


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
