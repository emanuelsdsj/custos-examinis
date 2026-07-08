"""Audit a local directory without going through the HTTP API.

This is the safe home for "point the auditor at a path" convenience: reading
an arbitrary path off the local filesystem is fine when it's the operator's
own machine and their own invocation, but exposing that as an API parameter
would let any authenticated caller make the server read its own filesystem.
See the ingestion trust-boundary note in README.md.

Usage:
    python scripts/audit_local.py path/to/project
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from custos_examinis.config import get_settings
from custos_examinis.domain.state import initial_state
from custos_examinis.graph.build import build_audit_graph
from custos_examinis.ingest.sandbox import ALLOWED_EXTENSIONS, IngestionError
from custos_examinis.ingest.sources import from_inline_files
from custos_examinis.llm.router import ModelRouter


def _collect_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            files[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return files


async def _run(root: Path) -> int:
    settings = get_settings()
    try:
        file_set = from_inline_files(_collect_files(root), settings)
    except IngestionError as exc:
        print(f"ingestion rejected: {exc}", file=sys.stderr)
        return 1

    if not file_set.files:
        print("no auditable files found under the given path", file=sys.stderr)
        return 1

    router = ModelRouter(settings)
    graph = build_audit_graph(router)
    result = await graph.ainvoke(initial_state(str(uuid.uuid4()), file_set))

    report = result["report"]
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="local directory to audit")
    args = parser.parse_args()
    return asyncio.run(_run(args.path))


if __name__ == "__main__":
    raise SystemExit(main())
