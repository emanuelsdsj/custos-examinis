from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel


class ScriptedChatModel(BaseChatModel):
    """A fake chat model for tests: returns a fixed text response on a plain
    invoke, and a fixed structured-output envelope (matching the include_raw
    shape our ModelRouter always requests) on with_structured_output(...).
    Can be configured to raise, which is how fallback-chain ordering gets
    exercised without any real network access.
    """

    model_name: str = "scripted-fake"
    text_response: str = "ok"
    structured_response: BaseModel | None = None
    parsing_error: str | None = None
    should_raise: bool = False
    input_tokens: int = 10
    output_tokens: int = 5

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.should_raise:
            raise RuntimeError(f"{self.model_name} simulated failure")
        return ChatResult(generations=[ChatGeneration(message=self._build_message())])

    def _build_message(self) -> AIMessage:
        return AIMessage(
            content=self.text_response,
            usage_metadata={
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.input_tokens + self.output_tokens,
            },
            response_metadata={"model_name": self.model_name},
        )

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def with_structured_output(
        self, schema: dict[str, Any] | type, *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable[Any, Any]:

        def _invoke(_: Any) -> Any:
            if self.should_raise:
                raise RuntimeError(f"{self.model_name} simulated failure")
            raw = self._build_message()
            if not include_raw:
                if self.structured_response is None:
                    raise ValueError("no structured_response configured on fake model")
                return self.structured_response
            return {
                "raw": raw,
                "parsed": self.structured_response,
                "parsing_error": self.parsing_error,
            }

        return RunnableLambda(_invoke)
