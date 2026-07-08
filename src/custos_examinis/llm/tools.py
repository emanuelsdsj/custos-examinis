from langchain_core.tools import BaseTool, tool

from custos_examinis.ingest.models import FileSet


def make_read_file_tool(file_set: FileSet) -> BaseTool:
    """A file-read tool scoped entirely to an in-memory, already-sandboxed FileSet.

    Not bound to any MVP agent: current agents inline size-capped file content
    directly into a single prompt call instead of a tool-calling loop. Kept here,
    wired and tested, as the seam for a later large-repo/agentic-loop mode where
    content can't fit in one prompt. It grants no filesystem or network access,
    it is a plain dict lookup against files ingested before the agent ran.
    """

    @tool
    def read_file(path: str) -> str:
        """Read a file that is part of this audit's file set. No other paths are reachable."""
        ingested = file_set.files.get(path)
        if ingested is None:
            return f"ERROR: {path!r} is not part of this audit's file set."
        return ingested.content

    return read_file
