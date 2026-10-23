from datetime import datetime
from pydantic import BaseModel


class ScanRequest(BaseModel):
    subscription_id: str


class ScanResponse(BaseModel):
    id: int
    subscription_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}
