from datetime import datetime
from pydantic import BaseModel, Field


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subscription_id: str = Field(min_length=36, max_length=36)


class SubscriptionResponse(BaseModel):
    id: int
    name: str
    subscription_id: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
