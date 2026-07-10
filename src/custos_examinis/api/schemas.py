from pydantic import BaseModel, Field

from custos_examinis.domain.report import AuditReport
from custos_examinis.jobs.store import JobStatus


class InlineFilesRequest(BaseModel):
    files: dict[str, str] = Field(min_length=1)


class AuditSubmitResponse(BaseModel):
    audit_id: str
    status: JobStatus


class AuditStatusResponse(BaseModel):
    audit_id: str
    status: JobStatus
    progress: list[str] = Field(default_factory=list)
    report: AuditReport | None = None
    error: str | None = None
