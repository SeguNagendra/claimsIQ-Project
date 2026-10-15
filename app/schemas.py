from pydantic import BaseModel, ConfigDict, Field


class PolicyCreate(BaseModel):
    number: str = Field(min_length=1, max_length=80)
    holder: str = Field(min_length=1, max_length=150)
    active: bool = True


class PolicyOut(BaseModel):
    id: int
    number: str
    holder: str
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
