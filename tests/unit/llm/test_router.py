import pytest
from pydantic import BaseModel

from custos_examinis.llm.router import ModelRouter
from tests.fakes.fake_chat_model import ScriptedChatModel


class _Echo(BaseModel):
    value: str


async def test_get_chat_model_uses_primary_when_healthy() -> None:
    primary = ScriptedChatModel(model_name="primary", text_response="from primary")
    router = ModelRouter.from_models({"summarize": [primary]})

    model = router.get_chat_model("summarize")
    result = await model.ainvoke("prompt")

    assert result.content == "from primary"


async def test_get_chat_model_falls_back_when_primary_raises() -> None:
    primary = ScriptedChatModel(model_name="primary", should_raise=True)
    fallback = ScriptedChatModel(model_name="fallback", text_response="from fallback")
    router = ModelRouter.from_models({"summarize": [primary, fallback]})

    model = router.get_chat_model("summarize")
    result = await model.ainvoke("prompt")

    assert result.content == "from fallback"


async def test_get_chat_model_structured_output_falls_back() -> None:
    echo = _Echo(value="ok")
    primary = ScriptedChatModel(model_name="primary", should_raise=True)
    fallback = ScriptedChatModel(model_name="fallback", structured_response=echo)
    router = ModelRouter.from_models({"triage": [primary, fallback]})

    model = router.get_chat_model("triage", structured_output=_Echo)
    result = await model.ainvoke("prompt")

    assert result["parsed"] == echo
    assert result["raw"].response_metadata["model_name"] == "fallback"


def test_get_chat_model_raises_for_unknown_role() -> None:
    router = ModelRouter.from_models({})
    with pytest.raises(ValueError, match="no models configured"):
        router.get_chat_model("unknown-role")
