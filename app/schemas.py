from pydantic import BaseModel, ConfigDict, Field


class PolicyCreate(BaseModel):
    number: str = Field(min_length=1, max_length=80)
    holder: str = Field(min_length=1, max_length=150)
    owner_id: int = Field(gt=0)
    active: bool = True


class PolicyOut(BaseModel):
    id: int
    number: str
    holder: str
    owner_id: int | None
    active: bool

    model_config = ConfigDict(from_attributes=True)


class ClaimCreate(BaseModel):
    policy_id: int = Field(gt=0)
    description: str = Field(min_length=3, max_length=5000)
    amount: int = Field(ge=0)


class ClaimOut(BaseModel):
    id: int
    policy_id: int
    owner_id: int
    assigned_to: int | None
    description: str
    amount: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class AssignmentCreate(BaseModel):
    user_id: int = Field(gt=0)


class StatusChange(BaseModel):
    status: str
    justification: str | None = Field(default=None, max_length=2000)


class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


from datetime import date
from pydantic import Field
class PolicyQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    policy_code: str | None = Field(default=None, max_length=100)
class SourceReference(BaseModel):
    document_id: str
    document_name: str
    version: str
    page_number: int | None = None
    chunk_id: str
class PolicyQueryResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    response_time_ms: int
    status: str
