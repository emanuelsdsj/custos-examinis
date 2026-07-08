from collections.abc import AsyncIterator

import pytest
from fakeredis import aioredis

from custos_examinis.domain.finding import FindingsBatch
from custos_examinis.ingest.models import FileSet, IngestedFile
from custos_examinis.jobs.runner import run_audit
from custos_examinis.jobs.store import JobStatus, JobStore
from custos_examinis.llm.router import ModelRouter
from tests.fakes.fake_chat_model import ScriptedChatModel


@pytest.fixture
async def store() -> AsyncIterator[JobStore]:
    redis = aioredis.FakeRedis(decode_responses=True)
    yield JobStore(redis)
    await redis.aclose()


def _file_set() -> FileSet:
    return FileSet(files={"app.py": IngestedFile(path="app.py", content="x = 1", size_bytes=5)})


async def test_run_audit_marks_job_completed_on_success(store: JobStore) -> None:
    await store.create("audit-1", owner="user-1")
    empty = FindingsBatch(findings=[])
    router = ModelRouter.from_models(
        {
            "deep_reasoning": [ScriptedChatModel(structured_response=empty)],
            "broad_review": [ScriptedChatModel(structured_response=empty)],
            "triage": [ScriptedChatModel(text_response="unused")],
            "summarize": [ScriptedChatModel(text_response="all clear")],
        }
    )

    await run_audit("audit-1", _file_set(), router, store)

    job = await store.get("audit-1")
    assert job is not None
    assert job.status == JobStatus.COMPLETED
    assert job.report is not None
    assert job.report.summary == "all clear"


async def test_run_audit_completes_with_agent_errors_when_no_providers_configured(
    store: JobStore,
) -> None:
    """Every agent's own model construction fails (no roles configured on the
    router), which used to crash the whole graph since get_chat_model() was
    called outside each agent's try/except. It shouldn't: an audit is still a
    valid, completed run, just one that honestly reports every agent failed.
    """
    await store.create("audit-1", owner="user-1")
    router = ModelRouter.from_models({})

    await run_audit("audit-1", _file_set(), router, store)

    job = await store.get("audit-1")
    assert job is not None
    assert job.status == JobStatus.COMPLETED
    assert job.report is not None
    assert job.report.findings == []
    assert len(job.report.agent_errors) >= 3


async def test_run_audit_marks_job_failed_on_unexpected_graph_error(
    store: JobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _broken_graph_builder(_router: ModelRouter) -> None:
        raise RuntimeError("graph construction blew up")

    monkeypatch.setattr("custos_examinis.jobs.runner.build_audit_graph", _broken_graph_builder)
    await store.create("audit-1", owner="user-1")

    await run_audit("audit-1", _file_set(), ModelRouter.from_models({}), store)

    job = await store.get("audit-1")
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.error is not None
