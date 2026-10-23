from app.core.security import hash_password, verify_password, create_access_token, decode_access_token


def test_password_hash_and_verify():
    hashed = hash_password("sample-password")
    assert hashed != "sample-password"
    assert verify_password("sample-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_jwt_round_trip():
    token = create_access_token(user_id=7, username="security", role="SECURITY_OFFICER")
    payload = decode_access_token(token)
    assert payload["sub"] == "7"
    assert payload["role"] == "SECURITY_OFFICER"
