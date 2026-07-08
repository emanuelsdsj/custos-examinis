from custos_examinis.ingest.models import FileSet, IngestedFile
from custos_examinis.llm.tools import make_read_file_tool


def _file_set() -> FileSet:
    ingested = IngestedFile(path="app.py", content="print(1)", size_bytes=8)
    return FileSet(files={"app.py": ingested})


def test_read_file_tool_returns_content_for_known_path() -> None:
    tool = make_read_file_tool(_file_set())

    assert tool.invoke({"path": "app.py"}) == "print(1)"


def test_read_file_tool_rejects_paths_outside_the_file_set() -> None:
    tool = make_read_file_tool(_file_set())

    result = tool.invoke({"path": "/etc/passwd"})

    assert "ERROR" in result
    assert "not part of this audit" in result
