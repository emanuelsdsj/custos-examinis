import re
from collections.abc import Awaitable, Callable

from custos_examinis.costs.tracker import TokenUsageSummary
from custos_examinis.domain.errors import AgentError
from custos_examinis.domain.finding import Finding, FindingCategory
from custos_examinis.domain.report import AuditReport
from custos_examinis.domain.state import AuditState, NodeUpdate

MAX_FINDINGS = 500

_SNIPPET_VALUE_PATTERN = re.compile(r"['\"]([^'\"]{4,})['\"]")


def _redact_secret_snippet(snippet: str | None) -> str | None:
    if snippet is None:
        return None
    return _SNIPPET_VALUE_PATTERN.sub("'***REDACTED***'", snippet)


def _sanitize(finding: Finding, known_files: set[str]) -> tuple[Finding | None, str | None]:
    if finding.file not in known_files:
        return None, f"dropped finding {finding.rule_id!r}: file {finding.file!r} not in file set"

    if finding.category is FindingCategory.SECRET:
        finding = finding.model_copy(update={"snippet": _redact_secret_snippet(finding.snippet)})

    return finding, None


def make_guardrail_node() -> Callable[[AuditState], Awaitable[NodeUpdate]]:
    async def guardrail_node(state: AuditState) -> NodeUpdate:
        known_files = set(state["file_set"].files.keys())
        sanitized: list[Finding] = []
        drop_notes: list[str] = []

        for finding in state["deduped_findings"][:MAX_FINDINGS]:
            clean, note = _sanitize(finding, known_files)
            if clean is not None:
                sanitized.append(clean)
            if note is not None:
                drop_notes.append(note)

        agent_errors = list(state["agent_errors"])
        agent_errors.extend(
            AgentError(agent="guardrail", message=note, recoverable=True) for note in drop_notes
        )

        token_usage = TokenUsageSummary.from_events(state["token_usage"])

        report = AuditReport.build(
            audit_id=state["audit_id"],
            summary=state["summary"],
            findings=sanitized,
            agent_errors=agent_errors,
            token_usage=token_usage,
        )

        return {"report": report}

    return guardrail_node
