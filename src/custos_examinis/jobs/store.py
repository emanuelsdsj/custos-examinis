import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel
from redis.asyncio import Redis

from custos_examinis.domain.report import AuditReport

_KEY_PREFIX = "audit-job:"
_CHANNEL_PREFIX = "audit-progress:"
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
    progress: list[str] = []
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

    def channel(self, audit_id: str) -> str:
        """The Redis pub/sub channel progress/status events are published on.

        Public so `jobs.events` can subscribe before reading the stored
        snapshot, avoiding the gap between "read state" and "start listening"
        where an event could otherwise be missed.
        """
        return f"{_CHANNEL_PREFIX}{audit_id}"

    async def _publish(self, audit_id: str, payload: dict[str, object]) -> None:
        await self._redis.publish(self.channel(audit_id), json.dumps(payload))

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
        await self._publish(audit_id, {"type": "status", "status": job.status.value})

    async def mark_completed(self, audit_id: str, report: AuditReport) -> None:
        job = await self.get(audit_id)
        if job is None:
            return
        job.status = JobStatus.COMPLETED
        job.report = report
        job.updated_at = datetime.now(UTC)
        await self._save(job)
        await self._publish(audit_id, {"type": "status", "status": job.status.value})

    async def mark_failed(self, audit_id: str, error: str) -> None:
        job = await self.get(audit_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error = error
        job.updated_at = datetime.now(UTC)
        await self._save(job)
        await self._publish(
            audit_id, {"type": "status", "status": job.status.value, "error": error}
        )

    async def append_progress(self, audit_id: str, node: str) -> None:
        """Records that one agent/graph node finished, for SSE progress streaming.

        Written to the same Redis snapshot the status endpoint reads (so a
        client that connects late still sees everything that already
        happened) and published on the pub/sub channel (so a client already
        connected sees it the moment it happens).
        """
        job = await self.get(audit_id)
        if job is None:
            return
        job.progress = [*job.progress, node]
        job.updated_at = datetime.now(UTC)
        await self._save(job)
        await self._publish(audit_id, {"type": "progress", "node": node})

    async def _save(self, job: AuditJob) -> None:
        await self._redis.set(self._key(job.audit_id), job.model_dump_json(), ex=_JOB_TTL_SECONDS)
