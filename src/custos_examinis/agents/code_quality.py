import functools
from collections.abc import Awaitable, Callable

from custos_examinis.agents.prompts import build_review_prompt
from custos_examinis.agents.support import invoke_structured
from custos_examinis.domain.errors import AgentError
from custos_examinis.domain.finding import FindingsBatch
from custos_examinis.domain.state import AuditState, NodeUpdate
from custos_examinis.llm.router import ModelRouter

AGENT_NAME = "code_quality_agent"
ROLE = "broad_review"

INSTRUCTIONS = """\
You are a code quality reviewer. Identify maintainability and correctness
issues in the submitted code: dead code, missing error handling, overly
complex functions, duplicated logic, unclear naming, missing input validation
at trust boundaries, and similar concerns. For each finding, give a rule_id
(short, kebab-case), title, description, severity, the exact file, a line
number when identifiable, a short snippet, and a confidence between 0 and 1.
Skip security vulnerabilities, that is a separate review. Return only findings
with category "code_quality".
"""


def make_code_quality_node(
    router: ModelRouter,
) -> Callable[[AuditState], Awaitable[NodeUpdate]]:
    async def code_quality_node(state: AuditState) -> NodeUpdate:
        prompt = build_review_prompt(INSTRUCTIONS, state["file_set"].as_prompt_blocks())
        build_model = functools.partial(
            router.get_chat_model, ROLE, structured_output=FindingsBatch
        )
        result = await invoke_structured(build_model, prompt, ROLE)

        if result.error is not None or result.parsed is None:
            error = AgentError(
                agent=AGENT_NAME, message=result.error or "no output", recoverable=True
            )
            update: NodeUpdate = {"agent_errors": [error]}
            if result.usage_event is not None:
                update["token_usage"] = [result.usage_event]
            return update

        batch: FindingsBatch = result.parsed
        findings = [f.model_copy(update={"agent": AGENT_NAME}) for f in batch.findings]

        return {
            "quality_findings": findings,
            "token_usage": [result.usage_event] if result.usage_event else [],
        }

    return code_quality_node
