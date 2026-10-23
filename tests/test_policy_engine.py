from app.services.policy_engine import missing_required_tag, is_open_to_any_ipv4


def test_missing_environment_tag_when_no_tags():
    assert missing_required_tag({}, "Environment") is True


def test_tag_check_is_case_insensitive():
    assert missing_required_tag({"environment": "dev"}, "Environment") is False


def test_any_ipv4_open_inbound_allow_is_detected():
    assert is_open_to_any_ipv4("0.0.0.0/0", "Allow", "Inbound") is True


def test_restricted_cidr_is_not_detected():
    assert is_open_to_any_ipv4("10.10.1.0/24", "Allow", "Inbound") is False


def test_deny_rule_is_not_detected():
    assert is_open_to_any_ipv4("0.0.0.0/0", "Deny", "Inbound") is False


def test_outbound_rule_is_not_detected():
    assert is_open_to_any_ipv4("0.0.0.0/0", "Allow", "Outbound") is False


def test_invalid_source_is_not_detected():
    assert is_open_to_any_ipv4("not-a-cidr", "Allow", "Inbound") is False
