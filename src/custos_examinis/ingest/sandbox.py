import posixpath

from custos_examinis.config import Settings

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".rs", ".kt", ".swift", ".cs",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".env", ".txt",
    ".md", ".sql", ".sh", ".dockerfile", ".gradle", ".xml", ".html",
}


class IngestionError(Exception):
    pass


def normalize_path(raw_path: str) -> str:
    """Reject anything that could escape the in-memory sandbox: absolute paths,
    parent-directory traversal, null bytes, or backslash-style Windows separators
    hiding a traversal attempt.
    """
    if "\x00" in raw_path:
        raise IngestionError(f"path contains a null byte: {raw_path!r}")

    candidate = raw_path.replace("\\", "/")
    if candidate.startswith("/") or (len(candidate) > 1 and candidate[1] == ":"):
        raise IngestionError(f"absolute paths are not allowed: {raw_path!r}")

    normalized = posixpath.normpath(candidate)
    if normalized == "." or normalized.startswith("../") or normalized == "..":
        raise IngestionError(f"path escapes the sandbox: {raw_path!r}")

    return normalized


def validate_extension(path: str) -> None:
    suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise IngestionError(f"unsupported file extension for {path!r}")


def validate_file_size(path: str, size_bytes: int, settings: Settings) -> None:
    if size_bytes > settings.max_file_size_bytes:
        raise IngestionError(
            f"{path!r} exceeds the per-file size limit "
            f"({size_bytes} > {settings.max_file_size_bytes} bytes)"
        )


def validate_file_count(count: int, settings: Settings) -> None:
    if count > settings.max_file_count:
        raise IngestionError(
            f"too many files ({count} > {settings.max_file_count} allowed)"
        )


def validate_total_size(total_bytes: int, settings: Settings) -> None:
    if total_bytes > settings.max_archive_size_bytes:
        raise IngestionError(
            f"total size exceeds the archive size limit "
            f"({total_bytes} > {settings.max_archive_size_bytes} bytes)"
        )


def decode_text(path: str, raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestionError(f"{path!r} is not valid UTF-8 text") from exc
