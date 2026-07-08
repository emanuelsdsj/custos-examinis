from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


# Static price table, USD per million tokens. Update as providers change pricing.
# Ollama entries are local, kept at zero for cost accounting purposes.
PRICE_TABLE: dict[str, ModelPrice] = {
    "claude-sonnet-4-5": ModelPrice(input_per_million=3.0, output_per_million=15.0),
    "claude-haiku-4-5": ModelPrice(input_per_million=0.8, output_per_million=4.0),
    "gemini-2.5-flash": ModelPrice(input_per_million=0.30, output_per_million=2.50),
    "gemini-2.5-pro": ModelPrice(input_per_million=1.25, output_per_million=10.0),
}

DEFAULT_OLLAMA_PRICE = ModelPrice(input_per_million=0.0, output_per_million=0.0)


def price_for_model(model: str) -> ModelPrice:
    return PRICE_TABLE.get(model, DEFAULT_OLLAMA_PRICE)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = price_for_model(model)
    return (
        input_tokens / 1_000_000 * price.input_per_million
        + output_tokens / 1_000_000 * price.output_per_million
    )
