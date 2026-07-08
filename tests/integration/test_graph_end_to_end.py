from pathlib import Path

from custos_examinis.config import Settings
from custos_examinis.domain.finding import Finding, FindingCategory, FindingsBatch, Severity
from custos_examinis.domain.state import initial_state
from custos_examinis.graph.build import build_audit_graph
from custos_examinis.ingest.sources import from_inline_files
from custos_examinis.llm.router import ModelRouter
from tests.fakes.fake_chat_model import ScriptedChatModel

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "vulnerable_sample"


def _vulnerable_files() -> dict[str, str]:
    return {"app.py": (FIXTURE_DIR / "app.py").read_text()}


def _fake_router() -> ModelRouter:
    vulnerability_batch = FindingsBatch(
        findings=[
            Finding(
                rule_id="sql-injection",
                title="SQL injection via string concatenation",
                description="user input is concatenated directly into a SQL query",
                severity=Severity.HIGH,
                category=FindingCategory.VULNERABILITY,
                file="app.py",
                line=9,
                agent="llm",
            )
        ]
    )
    quality_batch = FindingsBatch(
        findings=[
            Finding(
                rule_id="bare-except",
                title="Bare except clause",
                description="swallows all exceptions including KeyboardInterrupt",
                severity=Severity.LOW,
                category=FindingCategory.CODE_QUALITY,
                file="app.py",
                line=16,
                agent="llm",
            )
        ]
    )

    return ModelRouter.from_models(
        {
            "deep_reasoning": [ScriptedChatModel(structured_response=vulnerability_batch)],
            "broad_review": [ScriptedChatModel(structured_response=quality_batch)],
            "triage": [ScriptedChatModel(text_response="unused")],
            "summarize": [ScriptedChatModel(text_response="Two findings were reported.")],
        }
    )


async def test_full_graph_produces_a_validated_report_from_a_vulnerable_sample() -> None:
    file_set = from_inline_files(_vulnerable_files(), Settings())
    graph = build_audit_graph(_fake_router())

    result = await graph.ainvoke(initial_state("audit-1", file_set))

    report = result["report"]
    assert report is not None
    assert report.audit_id == "audit-1"
    assert report.summary == "Two findings were reported."

    categories = {f.category for f in report.findings}
    assert FindingCategory.VULNERABILITY in categories
    assert FindingCategory.CODE_QUALITY in categories
    assert FindingCategory.SECRET in categories  # regex pre-filter catches the AWS key

    assert report.token_usage.total_input_tokens > 0
    assert report.agent_errors == []
