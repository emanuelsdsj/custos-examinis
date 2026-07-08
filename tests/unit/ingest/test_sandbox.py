import pytest

from custos_examinis.config import Settings
from custos_examinis.ingest.sandbox import (
    IngestionError,
    normalize_path,
    validate_extension,
    validate_file_count,
    validate_file_size,
    validate_total_size,
)


def test_normalize_path_accepts_relative_path() -> None:
    assert normalize_path("src/app.py") == "src/app.py"


@pytest.mark.parametrize(
    "raw_path",
    [
        "../etc/passwd",
        "../../etc/passwd",
        "a/../../b.py",
        "/etc/passwd",
        "C:\\Windows\\system.ini",
        "a\x00b.py",
    ],
)
def test_normalize_path_rejects_traversal_and_absolute_paths(raw_path: str) -> None:
    with pytest.raises(IngestionError):
        normalize_path(raw_path)


def test_validate_extension_accepts_allowlisted_suffix() -> None:
    validate_extension("src/app.py")


def test_validate_extension_rejects_unknown_suffix() -> None:
    with pytest.raises(IngestionError):
        validate_extension("payload.exe")


def test_validate_file_size_rejects_oversized_file() -> None:
    small_settings = Settings(max_file_size_bytes=10)
    with pytest.raises(IngestionError):
        validate_file_size("big.py", 11, small_settings)


def test_validate_file_count_rejects_too_many_files() -> None:
    small_settings = Settings(max_file_count=1)
    with pytest.raises(IngestionError):
        validate_file_count(2, small_settings)


def test_validate_total_size_rejects_over_budget() -> None:
    small_settings = Settings(max_archive_size_bytes=10)
    with pytest.raises(IngestionError):
        validate_total_size(11, small_settings)
