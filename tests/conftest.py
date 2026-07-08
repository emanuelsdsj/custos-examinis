import io
import zipfile

import pytest

from custos_examinis.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        jwt_secret="test-secret",
        max_archive_size_bytes=1024 * 1024,
        max_file_count=50,
        max_file_size_bytes=64 * 1024,
    )


def make_zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()
