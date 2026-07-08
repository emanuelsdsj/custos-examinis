from typing import Any

import pytest
from pydantic import ValidationError

from custos_examinis.domain.finding import Finding, FindingCategory, Severity


def _base_kwargs() -> dict[str, Any]:
    return {
        "rule_id": "r1",
        "title": "t",
        "description": "d",
        "severity": Severity.LOW,
        "category": FindingCategory.CODE_QUALITY,
        "file": "app.py",
        "agent": "x",
    }


def test_finding_accepts_valid_payload() -> None:
    finding = Finding(**_base_kwargs())
    assert finding.confidence == 0.8
    assert finding.line is None


def test_finding_rejects_confidence_out_of_range() -> None:
    with pytest.raises(ValidationError):
        Finding(**{**_base_kwargs(), "confidence": 1.5})


def test_finding_rejects_non_positive_line_number() -> None:
    with pytest.raises(ValidationError):
        Finding(**{**_base_kwargs(), "line": 0})


def test_finding_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        Finding(**{**_base_kwargs(), "severity": "catastrophic"})
