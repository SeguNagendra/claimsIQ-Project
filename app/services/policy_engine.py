from ipaddress import ip_network


def missing_required_tag(tags: dict | None, tag_name: str) -> bool:
    normalized = {str(key).casefold() for key in (tags or {}).keys()}
    return tag_name.casefold() not in normalized


def is_open_to_any_ipv4(source_prefix: str | None, access: str | None = "Allow", direction: str | None = "Inbound") -> bool:
    if (access or "").casefold() != "allow" or (direction or "").casefold() != "inbound":
        return False
    if not source_prefix:
        return False
    try:
        network = ip_network(source_prefix, strict=False)
    except ValueError:
        return False
    return network.version == 4 and network.prefixlen == 0
