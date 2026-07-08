from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi import HTTPException

from custos_examinis.auth.jwt import decode_token
from custos_examinis.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret="unit-test-secret", jwt_algorithm="HS256")


def _make_token(
    settings: Settings, *, subject: str | None = "user-1", expired: bool = False
) -> str:
    exp = datetime.now(UTC) + (timedelta(minutes=-1) if expired else timedelta(minutes=30))
    payload: dict[str, Any] = {"exp": exp}
    if subject is not None:
        payload["sub"] = subject
    return str(jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))


def test_decode_token_returns_current_user_for_valid_token(settings: Settings) -> None:
    token = _make_token(settings)
    user = decode_token(token, settings)
    assert user.subject == "user-1"


def test_decode_token_rejects_expired_token(settings: Settings) -> None:
    token = _make_token(settings, expired=True)
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token, settings)
    assert exc_info.value.status_code == 401


def test_decode_token_rejects_garbage_token(settings: Settings) -> None:
    with pytest.raises(HTTPException) as exc_info:
        decode_token("not-a-real-token", settings)
    assert exc_info.value.status_code == 401


def test_decode_token_rejects_token_without_subject(settings: Settings) -> None:
    token = _make_token(settings, subject=None)
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token, settings)
    assert exc_info.value.status_code == 401


def test_decode_token_rejects_token_signed_with_a_different_secret(settings: Settings) -> None:
    other_settings = Settings(jwt_secret="a-different-secret", jwt_algorithm="HS256")
    token = _make_token(other_settings)
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token, settings)
    assert exc_info.value.status_code == 401
