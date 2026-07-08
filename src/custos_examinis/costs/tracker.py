from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from custos_examinis.costs.pricing import estimate_cost_usd


class TokenUsageEvent(BaseModel):
    role: str = Field(max_length=50)
    provider: str = Field(max_length=50)
    model: str = Field(max_length=100)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def estimated_cost_usd(self) -> float:
        return estimate_cost_usd(self.model, self.input_tokens, self.output_tokens)


class TokenUsageSummary(BaseModel):
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_estimated_cost_usd: float = 0.0
    by_provider: dict[str, float] = Field(default_factory=dict)

    @classmethod
    def from_events(cls, events: list[TokenUsageEvent]) -> "TokenUsageSummary":
        summary = cls()
        by_provider: dict[str, float] = {}
        for event in events:
            summary.total_input_tokens += event.input_tokens
            summary.total_output_tokens += event.output_tokens
            summary.total_estimated_cost_usd += event.estimated_cost_usd
            by_provider[event.provider] = (
                by_provider.get(event.provider, 0.0) + event.estimated_cost_usd
            )
        summary.by_provider = by_provider
        return summary


def _infer_provider(model: str) -> str:
    lowered = model.lower()
    if "claude" in lowered:
        return "anthropic"
    if "gemini" in lowered:
        return "google"
    return "ollama"


def usage_event_from_message(role: str, message: AIMessage) -> TokenUsageEvent | None:
    usage = getattr(message, "usage_metadata", None)
    if not usage:
        return None
    model = (
        message.response_metadata.get("model_name")
        or message.response_metadata.get("model")
        or "unknown"
    )
    return TokenUsageEvent(
        role=role,
        provider=_infer_provider(model),
        model=model,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )
