from custos_examinis.agents.guardrail import make_guardrail_node
from custos_examinis.domain.finding import Finding, FindingCategory, Severity
from custos_examinis.domain.state import AuditState, initial_state
from custos_examinis.ingest.models import FileSet, IngestedFile


def _state_with_findings(findings: list[Finding]) -> AuditState:
    file_set = FileSet(files={"app.py": IngestedFile(path="app.py", content="x", size_bytes=1)})
    state = initial_state("audit-1", file_set)
    state["deduped_findings"] = findings
    state["summary"] = "test summary"
    return state


async def test_guardrail_drops_findings_referencing_unknown_files() -> None:
    finding = Finding(
        rule_id="r1",
        title="t",
        description="d",
        severity=Severity.LOW,
        category=FindingCategory.CODE_QUALITY,
        file="does-not-exist.py",
        agent="x",
    )
    node = make_guardrail_node()

    result = await node(_state_with_findings([finding]))

    assert result["report"].findings == []
    assert any("dropped finding" in e.message for e in result["report"].agent_errors)


async def test_guardrail_redacts_secret_snippet_values() -> None:
    finding = Finding(
        rule_id="secret-aws-access-key",
        title="AWS key",
        description="d",
        severity=Severity.CRITICAL,
        category=FindingCategory.SECRET,
        file="app.py",
        snippet='AWS_KEY = "AKIAABCDEFGHIJKLMNOP"',
        agent="x",
    )
    node = make_guardrail_node()

    result = await node(_state_with_findings([finding]))

    redacted = result["report"].findings[0].snippet
    assert "AKIAABCDEFGHIJKLMNOP" not in redacted
    assert "REDACTED" in redacted


async def test_guardrail_builds_severity_counts_on_report() -> None:
    finding = Finding(
        rule_id="r1",
        title="t",
        description="d",
        severity=Severity.HIGH,
        category=FindingCategory.CODE_QUALITY,
        file="app.py",
        agent="x",
    )
    node = make_guardrail_node()

    result = await node(_state_with_findings([finding]))

    assert result["report"].severity_counts == {"high": 1}
    assert result["report"].summary == "test summary"
