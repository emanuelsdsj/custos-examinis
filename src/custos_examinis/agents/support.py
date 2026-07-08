from collections.abc import Callable
from typing import Any

from langchain_core.runnables import Runnable
from pydantic import BaseModel

from custos_examinis.costs.tracker import TokenUsageEvent, usage_event_from_message


class StructuredCallResult(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    parsed: Any | None
    usage_event: TokenUsageEvent | None
    error: str | None


async def invoke_structured(
    build_model: Callable[[], Runnable[Any, Any]], prompt: str, role: str
) -> StructuredCallResult:
    """Build a router-bound structured-output model and call it, normalizing the
    include_raw envelope into (parsed value, usage event, error message). Takes a
    thunk rather than an already-built model so that construction failures (e.g.
    a missing provider API key, which ModelRouter/ChatModel constructors raise
    eagerly rather than at call time) degrade the same way invocation failures
    do. Never raises, agent nodes are expected to degrade on failure rather than
    crash the whole audit.
    """
    try:
        model = build_model()
        result = await model.ainvoke(prompt)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        return StructuredCallResult(parsed=None, usage_event=None, error=str(exc))

    if not isinstance(result, dict):
        return StructuredCallResult(parsed=result, usage_event=None, error=None)

    parsing_error = result.get("parsing_error")
    raw = result.get("raw")
    usage_event = usage_event_from_message(role, raw) if raw is not None else None

    if parsing_error is not None:
        return StructuredCallResult(parsed=None, usage_event=usage_event, error=str(parsing_error))

    return StructuredCallResult(parsed=result.get("parsed"), usage_event=usage_event, error=None)
