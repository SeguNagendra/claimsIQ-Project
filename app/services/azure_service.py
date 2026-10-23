
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass
class AzureService:
    subscription_id: str

    def __post_init__(self) -> None:
        self._mock = settings.cloudguard_azure_mock
        self._compute = None
        self._network = None
        self._resource = None
        self._credential = None

        if self._mock:
            return

        # Authenticate using the Azure CLI session created by `az login`.
        from azure.identity import AzureCliCredential
        from azure.mgmt.compute import ComputeManagementClient
        from azure.mgmt.network import NetworkManagementClient
        from azure.mgmt.resource import ResourceManagementClient

        self._credential = AzureCliCredential()

        self._compute = ComputeManagementClient(
            self._credential,
            self.subscription_id,
        )

        self._network = NetworkManagementClient(
            self._credential,
            self.subscription_id,
        )

        self._resource = ResourceManagementClient(
            self._credential,
            self.subscription_id,
        )

    def list_vms(self) -> list[dict[str, Any]]:
        if self._mock:
            return [
                {
                    "id": (
                        "/subscriptions/mock/resourceGroups/rg-demo/"
                        "providers/Microsoft.Compute/virtualMachines/vm-demo-01"
                    ),
                    "name": "vm-demo-01",
                    "resource_group": "rg-demo",
                    "tags": {"Owner": "CloudGuardDemo"},
                },
                {
                    "id": (
                        "/subscriptions/mock/resourceGroups/rg-demo/"
                        "providers/Microsoft.Compute/virtualMachines/vm-demo-02"
                    ),
                    "name": "vm-demo-02",
                    "resource_group": "rg-demo",
                    "tags": {"Environment": "prod"},
                },
            ]

        items: list[dict[str, Any]] = []

        for vm in self._compute.virtual_machines.list_all():
            items.append(
                {
                    "id": vm.id,
                    "name": vm.name,
                    "resource_group": self._resource_group_from_id(vm.id),
                    "tags": vm.tags or {},
                }
            )

        return items

    def list_nsg_rules(self) -> list[dict[str, Any]]:
        if self._mock:
            return [
                {
                    "nsg_id": (
                        "/subscriptions/mock/resourceGroups/rg-demo/"
                        "providers/Microsoft.Network/"
                        "networkSecurityGroups/nsg-demo-01"
                    ),
                    "nsg_name": "nsg-demo-01",
                    "resource_group": "rg-demo",
                    "rule_name": "Allow-SSH-Any",
                    "source_prefix": "0.0.0.0/0",
                    "access": "Allow",
                    "direction": "Inbound",
                    "destination_port": "22",
                    "priority": 100,
                    "protocol": "Tcp",
                }
            ]

        items: list[dict[str, Any]] = []

        for nsg in self._network.network_security_groups.list_all():
            resource_group = self._resource_group_from_id(nsg.id)

            for rule in nsg.security_rules or []:
                # Azure rules may use either a single source prefix or a list.
                prefixes = (
                    list(rule.source_address_prefixes or [])
                    if rule.source_address_prefixes
                    else [rule.source_address_prefix]
                )

                for prefix in prefixes:
                    items.append(
                        {
                            "nsg_id": nsg.id,
                            "nsg_name": nsg.name,
                            "resource_group": resource_group,
                            "rule_name": rule.name,
                            "source_prefix": prefix,
                            "access": rule.access,
                            "direction": rule.direction,
                            "destination_port": rule.destination_port_range,
                            "priority": rule.priority,
                            "protocol": rule.protocol,
                        }
                    )

        return items

    def set_vm_tag(
        self,
        resource_id: str,
        tag_name: str,
        tag_value: str,
    ) -> None:
        if self._mock:
            return

        # Merge preserves existing tags and adds/updates only the requested tag.
        from azure.mgmt.resource.resources.models import TagsPatchResource

        patch = TagsPatchResource(
            operation="Merge",
            properties={"tags": {tag_name: tag_value}},
        )

        self._resource.tags.begin_update_at_scope(
            resource_id,
            patch,
        ).result()

    def replace_nsg_rule_source(
        self,
        resource_group: str,
        nsg_name: str,
        rule_name: str,
        source_cidr: str,
    ) -> None:
        if self._mock:
            return

        rule = self._network.security_rules.get(
            resource_group,
            nsg_name,
            rule_name,
        )

        # Preserve the rule's other settings, such as ports, protocol and priority.
        # Update the same source-prefix property style the rule originally used.
        if rule.source_address_prefixes:
            rule.source_address_prefix = None
            rule.source_address_prefixes = [source_cidr]
        else:
            rule.source_address_prefix = source_cidr

        self._network.security_rules.begin_create_or_update(
            resource_group,
            nsg_name,
            rule_name,
            rule,
        ).result()

    @staticmethod
    def _resource_group_from_id(resource_id: str | None) -> str:
        if not resource_id:
            return ""

        parts = resource_id.split("/")

        try:
            index = [
                part.casefold() for part in parts
            ].index("resourcegroups")

            return parts[index + 1]

        except (ValueError, IndexError):
            return ""
