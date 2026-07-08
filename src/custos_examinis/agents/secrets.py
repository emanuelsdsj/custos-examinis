import functools
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from custos_examinis.agents.support import invoke_structured
from custos_examinis.domain.errors import AgentError
from custos_examinis.domain.finding import Finding, FindingCategory, Severity
from custos_examinis.domain.state import AuditState, NodeUpdate
from custos_examinis.llm.router import ModelRouter

AGENT_NAME = "secrets_agent"
ROLE = "triage"

_PLACEHOLDER_VALUES = {
    "changeme", "xxx", "xxxx", "placeholder", "example", "test", "dummy",
    "your_key_here", "your-api-key", "todo", "fixme", "secret", "password",
    "notarealsecret", "fake", "redacted",
}


@dataclass(frozen=True)
class HighConfidenceRule:
    rule_id: str
    pattern: re.Pattern[str]
    title: str
    severity: Severity
    reference: str


@dataclass(frozen=True)
class AmbiguousRule:
    rule_id: str
    pattern: re.Pattern[str]
    title: str


HIGH_CONFIDENCE_RULES: list[HighConfidenceRule] = [
    HighConfidenceRule(
        rule_id="secret-aws-access-key",
        pattern=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        title="Hardcoded AWS access key ID",
        severity=Severity.CRITICAL,
        reference="CWE-798",
    ),
    HighConfidenceRule(
        rule_id="secret-private-key-block",
        pattern=re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"),
        title="Embedded private key",
        severity=Severity.CRITICAL,
        reference="CWE-798",
    ),
    HighConfidenceRule(
        rule_id="secret-stripe-live-key",
        pattern=re.compile(r"\bsk_live_[0-9a-zA-Z]{16,}\b"),
        title="Hardcoded Stripe live secret key",
        severity=Severity.CRITICAL,
        reference="CWE-798",
    ),
    HighConfidenceRule(
        rule_id="secret-slack-token",
        pattern=re.compile(r"\bxox[baprs]-[0-9a-zA-Z-]{10,}\b"),
        title="Hardcoded Slack token",
        severity=Severity.HIGH,
        reference="CWE-798",
    ),
]

AMBIGUOUS_RULES: list[AmbiguousRule] = [
    AmbiguousRule(
        rule_id="secret-generic-assignment",
        pattern=re.compile(
            r"(?i)\b(api[_-]?key|apikey|secret|password|token|access[_-]?key)"
            r"\s*[:=]\s*['\"]([^'\"]{6,})['\"]"
        ),
        title="Possible hardcoded credential",
    ),
]


class SecretCandidate(BaseModel):
    index: int
    file: str
    line: int
    context: str = Field(max_length=500)


class SecretTriageDecision(BaseModel):
    index: int
    is_secret: bool
    confidence: float = Field(ge=0.0, le=1.0)


class SecretTriageBatch(BaseModel):
    decisions: list[SecretTriageDecision] = Field(default_factory=list)


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _line_context(content: str, offset: int) -> str:
    line_start = content.rfind("\n", 0, offset) + 1
    line_end = content.find("\n", offset)
    if line_end == -1:
        line_end = len(content)
    return content[line_start:line_end].strip()


def _scan_file(path: str, content: str) -> tuple[list[Finding], list[SecretCandidate]]:
    findings: list[Finding] = []
    candidates: list[SecretCandidate] = []

    for hc_rule in HIGH_CONFIDENCE_RULES:
        for match in hc_rule.pattern.finditer(content):
            findings.append(
                Finding(
                    rule_id=hc_rule.rule_id,
                    title=hc_rule.title,
                    description=f"{hc_rule.title} detected in {path}.",
                    severity=hc_rule.severity,
                    category=FindingCategory.SECRET,
                    file=path,
                    line=_line_number(content, match.start()),
                    snippet=_line_context(content, match.start()),
                    reference=hc_rule.reference,
                    confidence=0.95,
                    agent=AGENT_NAME,
                )
            )

    for amb_rule in AMBIGUOUS_RULES:
        for match in amb_rule.pattern.finditer(content):
            value = match.group(2).strip().lower()
            if value in _PLACEHOLDER_VALUES or len(set(value)) <= 2:
                continue
            candidates.append(
                SecretCandidate(
                    index=0,
                    file=path,
                    line=_line_number(content, match.start()),
                    context=_line_context(content, match.start()),
                )
            )

    return findings, candidates


def _build_triage_prompt(candidates: list[SecretCandidate]) -> str:
    lines = [
        "For each candidate below, decide whether the value looks like a real "
        "secret (API key, password, token) as opposed to a placeholder, test "
        "fixture, or documentation example. Respond with one decision per "
        "candidate index.",
        "",
    ]
    for candidate in candidates:
        lines.append(f"[{candidate.index}] {candidate.file}:{candidate.line}: {candidate.context}")
    return "\n".join(lines)


def make_secrets_node(router: ModelRouter) -> Callable[[AuditState], Awaitable[NodeUpdate]]:
    async def secrets_node(state: AuditState) -> NodeUpdate:
        findings: list[Finding] = []
        all_candidates: list[SecretCandidate] = []

        for path, ingested in state["file_set"].files.items():
            file_findings, file_candidates = _scan_file(path, ingested.content)
            findings.extend(file_findings)
            all_candidates.extend(file_candidates)

        for i, candidate in enumerate(all_candidates):
            all_candidates[i] = candidate.model_copy(update={"index": i})

        if not all_candidates:
            return {"secret_findings": findings, "token_usage": []}

        prompt = _build_triage_prompt(all_candidates)
        build_model = functools.partial(
            router.get_chat_model, ROLE, structured_output=SecretTriageBatch
        )
        result = await invoke_structured(build_model, prompt, ROLE)

        if result.error is not None or result.parsed is None:
            update: NodeUpdate = {
                "secret_findings": findings,
                "agent_errors": [
                    AgentError(
                        agent=AGENT_NAME,
                        message=result.error or "no triage output",
                        recoverable=True,
                    )
                ],
            }
            if result.usage_event is not None:
                update["token_usage"] = [result.usage_event]
            return update

        batch: SecretTriageBatch = result.parsed
        by_index = {c.index: c for c in all_candidates}
        for decision in batch.decisions:
            if not decision.is_secret or decision.confidence < 0.5:
                continue
            matched_candidate = by_index.get(decision.index)
            if matched_candidate is None:
                continue
            findings.append(
                Finding(
                    rule_id="secret-triaged-credential",
                    title="Likely hardcoded credential",
                    description=(
                        f"A generic credential-shaped value in {matched_candidate.file} was "
                        "classified as a likely real secret rather than a placeholder."
                    ),
                    severity=Severity.HIGH,
                    category=FindingCategory.SECRET,
                    file=matched_candidate.file,
                    line=matched_candidate.line,
                    snippet=matched_candidate.context,
                    reference="CWE-798",
                    confidence=decision.confidence,
                    agent=AGENT_NAME,
                )
            )

        return {
            "secret_findings": findings,
            "token_usage": [result.usage_event] if result.usage_event else [],
        }

    return secrets_node
