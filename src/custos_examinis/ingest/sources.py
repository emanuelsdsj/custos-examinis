import zipfile
from io import BytesIO

from custos_examinis.config import Settings
from custos_examinis.ingest.models import FileSet, IngestedFile
from custos_examinis.ingest.sandbox import (
    IngestionError,
    decode_text,
    normalize_path,
    validate_extension,
    validate_file_count,
    validate_file_size,
    validate_total_size,
)

_SYMLINK_MODE_BIT = 0o120000


def from_zip_bytes(data: bytes, settings: Settings) -> FileSet:
    files: dict[str, IngestedFile] = {}
    running_total = 0

    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise IngestionError("not a valid zip archive") from exc

    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        validate_file_count(len(infos), settings)

        for info in infos:
            mode = (info.external_attr >> 16) & 0o170000
            if mode == _SYMLINK_MODE_BIT:
                raise IngestionError(f"symlink entries are not allowed: {info.filename!r}")

            path = normalize_path(info.filename)
            validate_extension(path)
            validate_file_size(path, info.file_size, settings)

            running_total += info.file_size
            validate_total_size(running_total, settings)

            raw = archive.read(info)
            if len(raw) != info.file_size:
                raise IngestionError(f"size mismatch while reading {path!r}")

            content = decode_text(path, raw)
            files[path] = IngestedFile(path=path, content=content, size_bytes=len(raw))

    return FileSet(files=files)


def from_inline_files(raw_files: dict[str, str], settings: Settings) -> FileSet:
    files: dict[str, IngestedFile] = {}
    running_total = 0

    validate_file_count(len(raw_files), settings)

    for raw_path, content in raw_files.items():
        path = normalize_path(raw_path)
        validate_extension(path)
        size_bytes = len(content.encode("utf-8"))
        validate_file_size(path, size_bytes, settings)

        running_total += size_bytes
        validate_total_size(running_total, settings)

        files[path] = IngestedFile(path=path, content=content, size_bytes=size_bytes)

    return FileSet(files=files)
