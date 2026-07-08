from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from custos_examinis.config import Settings
from custos_examinis.llm.providers import build_anthropic, build_gemini, build_ollama
from custos_examinis.logging import get_logger

logger = get_logger(__name__)


class ProviderName(StrEnum):
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"


# Each role has a different primary provider on purpose, so a normal (non-degraded)
# run genuinely exercises all three providers rather than two of them sitting idle
# as fallbacks that never trigger.
DEFAULT_ROLE_TABLE: dict[str, list[ProviderName]] = {
    "deep_reasoning": [ProviderName.ANTHROPIC, ProviderName.GOOGLE, ProviderName.OLLAMA],
    "broad_review": [ProviderName.GOOGLE, ProviderName.ANTHROPIC, ProviderName.OLLAMA],
    "triage": [ProviderName.OLLAMA, ProviderName.GOOGLE, ProviderName.ANTHROPIC],
    "summarize": [ProviderName.GOOGLE, ProviderName.OLLAMA, ProviderName.ANTHROPIC],
}


class ModelRouter:
    """Resolves a logical role to a chat model with a provider fallback chain.

    Two ways to build one: `ModelRouter(settings)` constructs real provider
    clients from `DEFAULT_ROLE_TABLE` (or an override); `ModelRouter.from_models(...)`
    wires in pre-built chains (typically GenericFakeChatModel instances) for tests,
    so fallback ordering can be exercised without any network access.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        role_table: dict[str, list[ProviderName]] | None = None,
        fake_chains: dict[str, list[BaseChatModel]] | None = None,
    ) -> None:
        self._settings = settings
        self._role_table = role_table or DEFAULT_ROLE_TABLE
        self._fake_chains = fake_chains
        self._cache: dict[tuple[str, str], Runnable[Any, Any]] = {}

    def get_chat_model(
        self, role: str, *, structured_output: type[BaseModel] | None = None
    ) -> Runnable[Any, Any]:
        cache_key = (role, structured_output.__name__ if structured_output else "")
        if cache_key in self._cache:
            return self._cache[cache_key]

        models = self._resolve_models(role, structured_output)
        if not models:
            raise ValueError(f"no models configured for role {role!r}")

        primary, *fallbacks = models
        resolved = primary.with_fallbacks(fallbacks) if fallbacks else primary
        self._cache[cache_key] = resolved
        return resolved

    def _resolve_models(
        self, role: str, structured_output: type[BaseModel] | None
    ) -> Sequence[Runnable[Any, Any]]:
        if self._fake_chains is not None:
            chain = self._fake_chains.get(role, [])
            if structured_output is not None:
                return [
                    model.with_structured_output(structured_output, include_raw=True)
                    for model in chain
                ]
            return list(chain)

        providers = self._role_table.get(role, [])
        built: list[Runnable[Any, Any]] = []
        for provider in providers:
            try:
                built.append(self._build(provider, structured_output))
            except Exception as exc:  # noqa: BLE001, PERF203 - a provider's own client
                # can raise eagerly at construction time (e.g. a missing API key).
                # One broken provider in the chain must not stop the remaining
                # ones from being tried, otherwise the fallback chain never gets
                # past whichever provider happens to validate eagerly.
                logger.warning(
                    "provider_unavailable", role=role, provider=provider.value, error=str(exc)
                )
        return built

    def _build(
        self, provider: ProviderName, structured_output: type[BaseModel] | None
    ) -> Runnable[Any, Any]:
        if self._settings is None:
            raise ValueError("ModelRouter has no settings; use from_models() in tests")

        if provider is ProviderName.ANTHROPIC:
            model = build_anthropic(self._settings)
        elif provider is ProviderName.GOOGLE:
            model = build_gemini(self._settings)
        else:
            model = build_ollama(self._settings)

        if structured_output is not None:
            method = "json_schema" if provider is ProviderName.OLLAMA else "function_calling"
            return model.with_structured_output(
                structured_output, method=method, include_raw=True
            )
        return model

    @classmethod
    def from_models(cls, chains: dict[str, list[BaseChatModel]]) -> "ModelRouter":
        return cls(fake_chains=chains)
