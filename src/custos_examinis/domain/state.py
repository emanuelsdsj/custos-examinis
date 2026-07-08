import operator
from typing import Annotated, Any, TypedDict

from custos_examinis.costs.tracker import TokenUsageEvent
from custos_examinis.domain.errors import AgentError
from custos_examinis.domain.finding import Finding
from custos_examinis.domain.report import AuditReport
from custos_examinis.ingest.models import FileSet

# Return type for LangGraph node functions: a partial state update. Typed as
# dict[str, Any] rather than a TypedDict since each node only returns the keys
# it touches, not the whole AuditState.
NodeUpdate = dict[str, Any]


class AuditState(TypedDict):
    audit_id: str
    file_set: FileSet
    vulnerability_findings: list[Finding]
    quality_findings: list[Finding]
    secret_findings: list[Finding]
    agent_errors: Annotated[list[AgentError], operator.add]
    token_usage: Annotated[list[TokenUsageEvent], operator.add]
    deduped_findings: list[Finding]
    summary: str
    report: AuditReport | None


def initial_state(audit_id: str, file_set: FileSet) -> AuditState:
    return AuditState(
        audit_id=audit_id,
        file_set=file_set,
        vulnerability_findings=[],
        quality_findings=[],
        secret_findings=[],
        agent_errors=[],
        token_usage=[],
        deduped_findings=[],
        summary="",
        report=None,
    )
