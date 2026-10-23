from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import Finding, PolicyRule, RemediationAction, Scan
from app.services.azure_service import AzureService
from app.services.audit_service import record_audit
from app.services.policy_engine import missing_required_tag, is_open_to_any_ipv4


def run_scan(db: Session, *, subscription_id: str, user_id: int) -> Scan:
    scan = Scan(subscription_id=subscription_id, triggered_by_user_id=user_id, status="RUNNING")
    db.add(scan)
    db.flush()
    try:
        azure = AzureService(subscription_id)
        policies = {p.code: p for p in db.query(PolicyRule).filter(PolicyRule.enabled.is_(True)).all()}

        tag_policy = policies.get("VM_REQUIRED_ENVIRONMENT_TAG")
        if tag_policy:
            tag_name = tag_policy.config.get("required_tag", "Environment")
            tag_value = tag_policy.config.get("default_value", "dev")
            for vm in azure.list_vms():
                if missing_required_tag(vm.get("tags"), tag_name):
                    finding = Finding(
                        scan_id=scan.id,
                        policy_code=tag_policy.code,
                        resource_id=vm["id"],
                        resource_name=vm["name"],
                        resource_type="Microsoft.Compute/virtualMachines",
                        severity="LOW",
                        status="REMEDIATING",
                        title=f"VM missing required tag: {tag_name}",
                        description=f"VM {vm['name']} is missing the required {tag_name} tag.",
                        details={"tag_name": tag_name, "tag_value": tag_value, "resource_group": vm.get("resource_group")},
                    )
                    db.add(finding)
                    db.flush()
                    action = RemediationAction(
                        finding_id=finding.id, requested_by_user_id=user_id,
                        action_type="ADD_VM_TAG", status="RUNNING",
                        input_data={"tag_name": tag_name, "tag_value": tag_value},
                    )
                    db.add(action)
                    db.flush()
                    try:
                        azure.set_vm_tag(vm["id"], tag_name, tag_value)
                        action.status = "SUCCEEDED"
                        action.result_message = f"Added {tag_name}={tag_value}; existing tags are preserved."
                        action.completed_at = datetime.now(timezone.utc)
                        finding.status = "RESOLVED"
                        record_audit(
                            db, actor_user_id=None, actor_type="AUTOMATION",
                            action="AUTO_REMEDIATION_SUCCEEDED", entity_type="Finding",
                            entity_id=str(finding.id),
                            details={"policy": tag_policy.code, "resource_id": vm["id"], "tag": tag_name, "value": tag_value},
                        )
                    except Exception as exc:
                        action.status = "FAILED"
                        action.result_message = str(exc)[:2000]
                        action.completed_at = datetime.now(timezone.utc)
                        finding.status = "OPEN"
                        record_audit(
                            db, actor_user_id=None, actor_type="AUTOMATION",
                            action="AUTO_REMEDIATION_FAILED", entity_type="Finding",
                            entity_id=str(finding.id), details={"error": str(exc)[:500]},
                        )

        nsg_policy = policies.get("NSG_INBOUND_ANY_IPV4")
        if nsg_policy:
            for rule in azure.list_nsg_rules():
                if is_open_to_any_ipv4(rule.get("source_prefix"), rule.get("access"), rule.get("direction")):
                    finding = Finding(
                        scan_id=scan.id,
                        policy_code=nsg_policy.code,
                        resource_id=rule["nsg_id"],
                        resource_name=rule["nsg_name"],
                        resource_type="Microsoft.Network/networkSecurityGroups",
                        severity="HIGH",
                        status="PENDING_APPROVAL",
                        title=f"NSG rule open to all IPv4: {rule['rule_name']}",
                        description=(
                            f"NSG {rule['nsg_name']} rule {rule['rule_name']} allows inbound traffic "
                            f"from 0.0.0.0/0. A Security/Compliance Officer must approve a specific replacement CIDR."
                        ),
                        details={
                            "resource_group": rule["resource_group"],
                            "nsg_name": rule["nsg_name"],
                            "rule_name": rule["rule_name"],
                            "source_prefix": rule["source_prefix"],
                            "destination_port": rule.get("destination_port"),
                            "priority": rule.get("priority"),
                            "protocol": rule.get("protocol"),
                        },
                    )
                    db.add(finding)
                    db.flush()
                    record_audit(
                        db, actor_user_id=user_id, action="HIGH_RISK_FINDING_CREATED",
                        entity_type="Finding", entity_id=str(finding.id),
                        details={"policy": nsg_policy.code, "resource_id": rule["nsg_id"], "rule_name": rule["rule_name"]},
                    )

        scan.status = "COMPLETED"
        scan.completed_at = datetime.now(timezone.utc)
        record_audit(
            db, actor_user_id=user_id, action="SCAN_COMPLETED", entity_type="Scan",
            entity_id=str(scan.id), details={"subscription_id": subscription_id},
        )
        db.commit()
        db.refresh(scan)
        return scan
    except Exception as exc:
        db.rollback()
        failed_scan = db.get(Scan, scan.id)
        if failed_scan:
            failed_scan.status = "FAILED"
            failed_scan.error_message = str(exc)[:2000]
            failed_scan.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise
