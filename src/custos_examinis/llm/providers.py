from langchain_core.language_models.chat_models import BaseChatModel

from custos_examinis.config import Settings

# Kept low deliberately: with_fallbacks() only helps if the primary gives up
# quickly instead of retrying internally until the fallback chain never runs.
_MAX_RETRIES = 1
_TIMEOUT_SECONDS = 30.0


def build_anthropic(settings: Settings) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        max_retries=_MAX_RETRIES,
        timeout=_TIMEOUT_SECONDS,
    )


def build_gemini(settings: Settings) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=settings.google_model,
        api_key=settings.google_api_key,
        max_retries=_MAX_RETRIES,
        timeout=_TIMEOUT_SECONDS,
    )


def build_ollama(settings: Settings) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        timeout=_TIMEOUT_SECONDS,
    )
