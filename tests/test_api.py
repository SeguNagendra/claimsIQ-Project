def test_health_and_openapi(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    assert "/claims" in spec["paths"]
    assert "/analytics/summary" in spec["paths"]
    assert not any(path.startswith("/documents") for path in spec["paths"])
    assert not any(path.startswith("/rag") for path in spec["paths"])


def test_password_login_and_me(client, auth_headers):
    headers = auth_headers("customer")
    response = client.get("/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["username"] == "customer"
    assert response.json()["role"] == "customer"


def test_invalid_login(client):
    response = client.post("/auth/token", data={"username": "customer", "password": "wrong"})
    assert response.status_code == 401


def test_role_protection(client, auth_headers):
    assert client.get("/users", headers=auth_headers("customer")).status_code == 403
    assert client.post(
        "/policies",
        headers=auth_headers("reviewer"),
        json={"number": "NOPE", "holder": "Test", "owner_id": 4, "active": True},
    ).status_code == 403
    assert client.get("/analytics/summary", headers=auth_headers("adjuster")).status_code == 403
    assert client.get("/audit", headers=auth_headers("reviewer")).status_code == 403


def test_policy_creation_duplicate_and_validation(client, auth_headers):
    admin = auth_headers("admin")
    customer_id = next(
        user["id"] for user in client.get("/users", headers=admin).json()
        if user["username"] == "customer"
    )
    response = client.post(
        "/policies",
        headers=admin,
        json={"number": "NEW-001", "holder": "Example Holder",
              "owner_id": customer_id, "active": True},
    )
    assert response.status_code == 201
    assert response.json()["number"] == "NEW-001"
    duplicate = client.post(
        "/policies",
        headers=admin,
        json={"number": "NEW-001", "holder": "Example Holder",
              "owner_id": customer_id, "active": True},
    )
    assert duplicate.status_code == 409


def test_claim_requires_active_policy(client, auth_headers):
    customer = auth_headers("customer")
    assert client.post(
        "/claims",
        headers=customer,
        json={"policy_id": 999, "description": "Test claim", "amount": 100},
    ).status_code == 422
    inactive_policy_id = next(
        policy["id"] for policy in client.get("/policies", headers=customer).json()
        if policy["number"] == "INACTIVE-001"
    )
    assert client.post(
        "/claims",
        headers=customer,
        json={"policy_id": inactive_policy_id, "description": "Test claim", "amount": 100},
    ).status_code == 422


def test_customer_cannot_submit_claim_against_another_customers_policy(client, auth_headers):
    customer = auth_headers("customer")
    customer2 = auth_headers("customer2")
    policy_id = client.get("/policies", headers=customer).json()[1]["id"]

    response = client.post(
        "/claims",
        headers=customer,
        json={"policy_id": policy_id, "description": "Unauthorized claim", "amount": 100},
    )
    assert response.status_code == 403

    allowed = client.post(
        "/claims",
        headers=customer2,
        json={"policy_id": policy_id, "description": "Authorized claim", "amount": 100},
    )
    assert allowed.status_code == 201, allowed.text
    customer2_id = next(
        user["id"] for user in client.get("/users", headers=auth_headers("admin")).json()
        if user["username"] == "customer2"
    )
    assert allowed.json()["owner_id"] == customer2_id


def test_claim_workflow_assignment_and_append_only_history(client, auth_headers):
    customer = auth_headers("customer")
    admin = auth_headers("admin")
    reviewer = auth_headers("reviewer")
    adjuster = auth_headers("adjuster")

    policy_id = client.get("/policies", headers=customer).json()[0]["id"]
    created = client.post(
        "/claims",
        headers=customer,
        json={"policy_id": policy_id, "description": "Water damage in kitchen", "amount": 1200},
    )
    assert created.status_code == 201, created.text
    claim_id = created.json()["id"]
    assert created.json()["status"] == "submitted"

    initial_history = client.get(f"/claims/{claim_id}/history", headers=customer).json()
    assert len(initial_history) == 1
    assert initial_history[0]["old_status"] is None
    assert initial_history[0]["new_status"] == "submitted"

    # New claims are automatically assigned to an active adjuster.
    assert client.get(f"/claims/{claim_id}", headers=adjuster).status_code == 200
    adjuster_id = next(
        user["id"] for user in client.get("/users", headers=admin).json()
        if user["username"] == "adjuster"
    )
    assigned = client.post(
        f"/claims/{claim_id}/assignment",
        headers=reviewer,
        json={"user_id": adjuster_id},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_to"] == adjuster_id

    under_review = client.post(
        f"/claims/{claim_id}/status",
        headers=adjuster,
        json={"status": "under_review"},
    )
    assert under_review.status_code == 200
    assert under_review.json()["status"] == "under_review"

    # Adjusters can process claims but cannot make approval/denial decisions.
    assert client.post(
        f"/claims/{claim_id}/status",
        headers=adjuster,
        json={"status": "approved"},
    ).status_code == 403

    approved = client.post(
        f"/claims/{claim_id}/status",
        headers=reviewer,
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    history = client.get(f"/claims/{claim_id}/history", headers=customer).json()
    assert [item["new_status"] for item in history] == ["submitted", "under_review", "approved"]


def test_admin_override_requires_justification(client, auth_headers):
    customer = auth_headers("customer")
    admin = auth_headers("admin")
    policy_id = client.get("/policies", headers=customer).json()[0]["id"]
    claim = client.post(
        "/claims",
        headers=customer,
        json={"policy_id": policy_id, "description": "Accidental damage", "amount": 250},
    ).json()
    claim_id = claim["id"]

    denied = client.post(
        f"/claims/{claim_id}/status",
        headers=admin,
        json={"status": "closed"},
    )
    assert denied.status_code == 409

    accepted = client.post(
        f"/claims/{claim_id}/status",
        headers=admin,
        json={"status": "closed", "justification": "Reviewed by management"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "closed"


def test_claim_data_is_filtered_by_role(client, auth_headers):
    customer = auth_headers("customer")
    customer2 = auth_headers("customer2")
    policy_id = client.get("/policies", headers=customer).json()[1]["id"]
    claim_response = client.post(
        "/claims",
        headers=customer2,
        json={"policy_id": policy_id, "description": "Customer private claim", "amount": 500},
    )
    assert claim_response.status_code == 201, claim_response.text
    claim = claim_response.json()
    assert client.get("/claims", headers=customer).json() == []
    assert len(client.get("/claims", headers=customer2).json()) == 1
    assert client.get(f"/claims/{claim['id']}", headers=customer).status_code == 404


def test_notes_and_audit(client, auth_headers):
    customer = auth_headers("customer")
    reviewer = auth_headers("reviewer")
    admin = auth_headers("admin")
    policy_id = client.get("/policies", headers=customer).json()[0]["id"]
    claim = client.post(
        "/claims",
        headers=customer,
        json={"policy_id": policy_id, "description": "Vehicle damage", "amount": 300},
    ).json()
    claim_id = claim["id"]

    created_note = client.post(
        f"/claims/{claim_id}/notes",
        headers=reviewer,
        json={"text": "Please review the submitted estimate."},
    )
    assert created_note.status_code == 201
    assert client.get(f"/claims/{claim_id}/notes", headers=customer).json()[0]["text"] == \
        "Please review the submitted estimate."

    logs = client.get("/audit", headers=admin)
    assert logs.status_code == 200
    assert any(item["action"] == "create" and item["resource"] == "claim" for item in logs.json())


def test_analytics_empty_and_populated(client, auth_headers):
    admin = auth_headers("admin")
    reviewer = auth_headers("reviewer")
    customer = auth_headers("customer")

    empty = client.get("/analytics/summary", headers=admin).json()
    assert empty["total_claims"] == 0
    assert empty["by_status"] == {}

    policy_id = client.get("/policies", headers=customer).json()[0]["id"]
    for amount in (100, 300):
        response = client.post(
            "/claims",
            headers=customer,
            json={"policy_id": policy_id, "description": f"Sample claim amount {amount}", "amount": amount},
        )
        assert response.status_code == 201

    summary = client.get("/analytics/summary", headers=reviewer).json()
    assert summary["total_claims"] == 2
    assert summary["by_status"] == {"submitted": 2}
    assert summary["total_amount"] == 400
    assert summary["average_amount"] == 200.0
    assert summary["assigned_claims"] == 2
    assert summary["unassigned_claims"] == 0


def test_unauthenticated_protected_endpoint(client):
    assert client.get("/claims").status_code == 401
