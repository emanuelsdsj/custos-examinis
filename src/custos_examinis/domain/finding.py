from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingCategory(StrEnum):
    VULNERABILITY = "vulnerability"
    CODE_QUALITY = "code_quality"
    SECRET = "secret"  # noqa: S105 - category name, not a credential


class Finding(BaseModel):
    rule_id: str = Field(max_length=100)
    title: str = Field(max_length=200)
    description: str = Field(max_length=2000)
    severity: Severity
    category: FindingCategory
    file: str = Field(max_length=1000)
    line: int | None = Field(default=None, ge=1)
    snippet: str | None = Field(default=None, max_length=500)
    reference: str | None = Field(default=None, max_length=200)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    agent: str = Field(max_length=100)


class FindingsBatch(BaseModel):
    """Structured-output envelope: LLM providers bind schemas better to a single
    object with a named list field than to a bare top-level list.
    """

    findings: list[Finding] = Field(default_factory=list)
