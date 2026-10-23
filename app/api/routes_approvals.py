from datetime import datetime, timezone
from ipaddress import ip_network
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import require_roles
from app.db.session import get_db
from app.models import Finding, RemediationAction, User
from app.schemas.finding import ApprovalRequest
from app.services.azure_service import AzureService
from app.services.audit_service import record_audit

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.get("/pending")
def pending_approvals(db: Session = Depends(get_db), user: User = Depends(require_roles("SECURITY_OFFICER", "ADMIN"))):
    findings = db.scalars(
        select(Finding).where(Finding.status == "PENDING_APPROVAL").order_by(Finding.created_at)
    ).all()
    return [
        {
            "finding_id": f.id, "title": f.title, "resource_name": f.resource_name,
            "severity": f.severity, "status": f.status, "details": f.details,
            "created_at": f.created_at,
        } for f in findings
    ]


@router.post("/findings/{finding_id}/approve")
def approve_finding(
    finding_id: int,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("SECURITY_OFFICER", "ADMIN")),
):
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if finding.policy_code != "NSG_INBOUND_ANY_IPV4" or finding.status != "PENDING_APPROVAL":
        raise HTTPException(status_code=409, detail="Finding is not awaiting NSG remediation approval")

    try:
        replacement = ip_network(payload.replacement_source_cidr, strict=False)
    except ValueError:
        raise HTTPException(status_code=422, detail="replacement_source_cidr must be a valid CIDR")
    if replacement.version != 4 or replacement.prefixlen == 0:
        raise HTTPException(status_code=422, detail="Replacement must be a restricted IPv4 CIDR, not 0.0.0.0/0")

    action = RemediationAction(
        finding_id=finding.id, requested_by_user_id=None, approved_by_user_id=user.id,
        action_type="RESTRICT_NSG_SOURCE_CIDR", status="RUNNING",
        input_data={"replacement_source_cidr": str(replacement)},
    )
    db.add(action)
    db.flush()
    try:
        azure = AzureService(_subscription_id_from_resource(finding.resource_id))
        azure.replace_nsg_rule_source(
            finding.details["resource_group"], finding.details["nsg_name"],
            finding.details["rule_name"], str(replacement),
        )
        action.status = "SUCCEEDED"
        action.result_message = f"Updated NSG rule source to {replacement}"
        action.completed_at = datetime.now(timezone.utc)
        finding.status = "RESOLVED"
        record_audit(
            db, actor_user_id=user.id, action="HIGH_RISK_REMEDIATION_APPROVED_AND_EXECUTED",
            entity_type="Finding", entity_id=str(finding.id),
            details={"replacement_source_cidr": str(replacement), "action_id": action.id},
        )
        db.commit()
        return {"finding_id": finding.id, "status": finding.status, "action_id": action.id, "result": action.result_message}
    except Exception as exc:
        action.status = "FAILED"
        action.result_message = str(exc)[:2000]
        action.completed_at = datetime.now(timezone.utc)
        finding.status = "PENDING_APPROVAL"
        record_audit(
            db, actor_user_id=user.id, action="APPROVED_REMEDIATION_FAILED",
            entity_type="Finding", entity_id=str(finding.id), details={"error": str(exc)[:500]},
        )
        db.commit()
        raise HTTPException(status_code=502, detail=f"Approval recorded, but Azure remediation failed: {str(exc)[:500]}")


def _subscription_id_from_resource(resource_id: str) -> str:
    parts = resource_id.split("/")
    for index, part in enumerate(parts):
        if part.casefold() == "subscriptions" and index + 1 < len(parts):
            return parts[index + 1]
    raise ValueError("Could not determine subscription ID from resource ID")
