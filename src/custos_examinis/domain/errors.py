from pydantic import BaseModel, Field


class AgentError(BaseModel):
    agent: str = Field(max_length=100)
    message: str = Field(max_length=1000)
    recoverable: bool = True
