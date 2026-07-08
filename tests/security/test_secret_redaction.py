from custos_examinis.logging import redact_secrets_processor


def test_redact_secrets_processor_masks_api_key_style_values() -> None:
    event_dict = {"event": "startup", "detail": 'api_key: "sk_live_abcdef1234567890"'}

    result = redact_secrets_processor(None, "info", event_dict)

    assert "sk_live_abcdef1234567890" not in result["detail"]
    assert "REDACTED" in result["detail"]


def test_redact_secrets_processor_masks_bearer_tokens() -> None:
    event_dict = {"event": "request", "detail": "Authorization: Bearer abc.def.ghi"}

    result = redact_secrets_processor(None, "info", event_dict)

    assert "abc.def.ghi" not in result["detail"]


def test_redact_secrets_processor_leaves_non_secret_fields_untouched() -> None:
    event_dict = {"event": "audit_run_failed", "audit_id": "1234"}

    result = redact_secrets_processor(None, "error", event_dict)

    assert result == event_dict
