from pydantic import BaseModel, Field

from custos_examinis.costs.tracker import TokenUsageSummary
from custos_examinis.domain.errors import AgentError
from custos_examinis.domain.finding import Finding


class AuditReport(BaseModel):
    audit_id: str
    summary: str = Field(max_length=4000)
    findings: list[Finding] = Field(default_factory=list)
    severity_counts: dict[str, int] = Field(default_factory=dict)
    agent_errors: list[AgentError] = Field(default_factory=list)
    token_usage: TokenUsageSummary = Field(default_factory=TokenUsageSummary)

    @classmethod
    def build(
        cls,
        audit_id: str,
        summary: str,
        findings: list[Finding],
        agent_errors: list[AgentError],
        token_usage: TokenUsageSummary,
    ) -> "AuditReport":
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
        return cls(
            audit_id=audit_id,
            summary=summary,
            findings=findings,
            severity_counts=counts,
            agent_errors=agent_errors,
            token_usage=token_usage,
        )
