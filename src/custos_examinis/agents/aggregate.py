from collections.abc import Awaitable, Callable

from langchain_core.messages import AIMessage

from custos_examinis.costs.tracker import usage_event_from_message
from custos_examinis.domain.errors import AgentError
from custos_examinis.domain.finding import Finding
from custos_examinis.domain.state import AuditState, NodeUpdate
from custos_examinis.llm.router import ModelRouter

AGENT_NAME = "aggregate_agent"
ROLE = "summarize"

FALLBACK_SUMMARY = "Automated summary unavailable; see the findings list below."


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, int | None, str]] = set()
    deduped: list[Finding] = []
    for finding in findings:
        key = (finding.file, finding.line, finding.rule_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def _build_summary_prompt(findings: list[Finding]) -> str:
    lines = [
        "Write a concise executive summary (max 5 sentences, plain text, no "
        "markdown headers) of the following security and quality audit "
        "findings for an engineering audience.",
        "",
    ]
    for finding in findings:
        location = f":{finding.line}" if finding.line else ""
        lines.append(
            f"- [{finding.severity}] {finding.title} in {finding.file}{location} "
            f"({finding.category})"
        )
    if not findings:
        lines.append("- No findings were reported.")
    return "\n".join(lines)


def make_aggregate_node(router: ModelRouter) -> Callable[[AuditState], Awaitable[NodeUpdate]]:
    async def aggregate_node(state: AuditState) -> NodeUpdate:
        deduped = _dedupe(
            [
                *state["vulnerability_findings"],
                *state["quality_findings"],
                *state["secret_findings"],
            ]
        )

        prompt = _build_summary_prompt(deduped)

        try:
            model = router.get_chat_model(ROLE)
            message = await model.ainvoke(prompt)
        except Exception as exc:  # noqa: BLE001 - degrade to a fallback summary
            return {
                "deduped_findings": deduped,
                "summary": FALLBACK_SUMMARY,
                "agent_errors": [
                    AgentError(agent=AGENT_NAME, message=str(exc), recoverable=True)
                ],
            }

        summary = str(message.content) if isinstance(message, AIMessage) else str(message)
        usage_event = (
            usage_event_from_message(ROLE, message) if isinstance(message, AIMessage) else None
        )

        return {
            "deduped_findings": deduped,
            "summary": summary,
            "token_usage": [usage_event] if usage_event else [],
        }

    return aggregate_node
