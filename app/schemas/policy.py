from datetime import datetime
from pydantic import BaseModel


class PolicyResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str
    resource_type: str
    severity: str
    config: dict
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}
