def test_document_and_rag_routes_are_registered(client):
    paths=client.get("/openapi.json").json()["paths"]
    assert "/documents" in paths
    assert "/documents/{document_id}/process" in paths
    assert "/documents/{document_id}/activation" in paths
    assert "/ai/query" in paths
    assert "/api/v1/documents" in paths
    assert "/api/v1/ai/query" in paths

def test_document_upload_requires_admin(client,auth_headers):
    response=client.post("/documents",headers=auth_headers("adjuster"),data={"policy_code":"MOTOR-001","document_name":"Motor Policy","version":"1","effective_from":"2026-01-01"})
    assert response.status_code==403

def test_ai_query_requires_authentication(client):
    assert client.post("/ai/query",json={"question":"What is covered?"}).status_code==401
