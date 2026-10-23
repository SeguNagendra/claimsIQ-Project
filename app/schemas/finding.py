from datetime import datetime
from pydantic import BaseModel


class FindingResponse(BaseModel):
    id: int
    scan_id: int
    policy_code: str
    resource_id: str
    resource_name: str
    resource_type: str
    severity: str
    status: str
    title: str
    description: str
    details: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalRequest(BaseModel):
    # The officer must supply the intended replacement CIDR. Never guess a production allowlist.
    replacement_source_cidr: str


class RemediationRequest(BaseModel):
    reason: str | None = None
