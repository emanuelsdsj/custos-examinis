from pydantic import BaseModel, Field


class IngestedFile(BaseModel):
    path: str = Field(max_length=1000)
    content: str
    size_bytes: int = Field(ge=0)


class FileSet(BaseModel):
    files: dict[str, IngestedFile] = Field(default_factory=dict)

    @property
    def total_size_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files.values())

    @property
    def file_count(self) -> int:
        return len(self.files)

    def as_prompt_blocks(self) -> str:
        blocks = []
        for path, file in sorted(self.files.items()):
            blocks.append(f'<file path="{path}">\n{file.content}\n</file>')
        return "\n".join(blocks)
