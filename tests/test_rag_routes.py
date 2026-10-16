def test_document_upload_requires_admin(client,auth_headers):
    response=client.post("/documents",headers=auth_headers("adjuster"),data={"policy_code":"MOTOR-001","document_name":"Motor Policy","version":"1","effective_from":"2026-01-01"})
    assert response.status_code==403

def test_ai_query_requires_authentication(client):
    assert client.post("/ai/query",json={"question":"What is covered?"}).status_code==401
