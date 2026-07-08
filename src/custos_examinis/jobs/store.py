from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel
from redis.asyncio import Redis

from custos_examinis.domain.report import AuditReport

_KEY_PREFIX = "audit-job:"
_JOB_TTL_SECONDS = 24 * 60 * 60


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditJob(BaseModel):
    audit_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    owner: str
    report: AuditReport | None = None
    error: str | None = None


class JobStore:
    """Redis is the sole source of truth for job state: the API can run with
    multiple uvicorn workers, and a GET may land on a different process than
    the one running the background task, so in-memory state would be unsafe.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, audit_id: str) -> str:
        return f"{_KEY_PREFIX}{audit_id}"

    async def create(self, audit_id: str, owner: str) -> AuditJob:
        now = datetime.now(UTC)
        job = AuditJob(
            audit_id=audit_id,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            owner=owner,
        )
        await self._save(job)
        return job

    async def get(self, audit_id: str) -> AuditJob | None:
        raw = await self._redis.get(self._key(audit_id))
        if raw is None:
            return None
        return AuditJob.model_validate_json(raw)

    async def mark_running(self, audit_id: str) -> None:
        job = await self.get(audit_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.updated_at = datetime.now(UTC)
        await self._save(job)

    async def mark_completed(self, audit_id: str, report: AuditReport) -> None:
        job = await self.get(audit_id)
        if job is None:
            return
        job.status = JobStatus.COMPLETED
        job.report = report
        job.updated_at = datetime.now(UTC)
        await self._save(job)

    async def mark_failed(self, audit_id: str, error: str) -> None:
        job = await self.get(audit_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error = error
        job.updated_at = datetime.now(UTC)
        await self._save(job)

    async def _save(self, job: AuditJob) -> None:
        await self._redis.set(self._key(job.audit_id), job.model_dump_json(), ex=_JOB_TTL_SECONDS)
