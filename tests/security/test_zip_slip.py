import io
import zipfile

import pytest

from custos_examinis.config import Settings
from custos_examinis.ingest.sandbox import IngestionError
from custos_examinis.ingest.sources import from_zip_bytes
from tests.conftest import make_zip_bytes


def test_from_zip_bytes_accepts_well_formed_archive(settings: Settings) -> None:
    data = make_zip_bytes({"app.py": "print(1)\n"})
    file_set = from_zip_bytes(data, settings)

    assert "app.py" in file_set.files
    assert file_set.files["app.py"].content == "print(1)\n"


@pytest.mark.parametrize(
    "malicious_name",
    [
        "../../etc/passwd.py",
        "../outside.py",
        "/etc/passwd.py",
    ],
)
def test_from_zip_bytes_rejects_path_traversal_entries(
    settings: Settings, malicious_name: str
) -> None:
    data = make_zip_bytes({malicious_name: "evil = True\n"})
    with pytest.raises(IngestionError):
        from_zip_bytes(data, settings)


def test_from_zip_bytes_rejects_symlink_entries(settings: Settings) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("link.py")
        info.external_attr = (0o120777 & 0xFFFF) << 16
        archive.writestr(info, "../../etc/passwd")

    with pytest.raises(IngestionError):
        from_zip_bytes(buffer.getvalue(), settings)


def test_from_zip_bytes_rejects_archive_over_total_size_budget() -> None:
    tight_settings = Settings(max_archive_size_bytes=10, max_file_count=10, max_file_size_bytes=10)
    data = make_zip_bytes({"a.py": "x" * 20})
    with pytest.raises(IngestionError):
        from_zip_bytes(data, tight_settings)


def test_from_zip_bytes_rejects_too_many_files() -> None:
    tight_settings = Settings(max_file_count=1)
    data = make_zip_bytes({"a.py": "x", "b.py": "y"})
    with pytest.raises(IngestionError):
        from_zip_bytes(data, tight_settings)


def test_from_zip_bytes_rejects_disallowed_extension(settings: Settings) -> None:
    data = make_zip_bytes({"payload.exe": "binary-ish"})
    with pytest.raises(IngestionError):
        from_zip_bytes(data, settings)
