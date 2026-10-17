from app.services.chunking_service import ChunkingService
from app.services.rag_service import redact_sensitive_data


def test_chunking_keeps_overlap_and_page_numbers():
    chunks = ChunkingService(chunk_size=10, chunk_overlap=2).chunk_pages([
        {"page_number": 3, "text": "abcdefghijklmnop"}
    ])
    assert len(chunks) == 2
    assert chunks[0]["page_number"] == 3
    assert chunks[0]["chunk_text"] == "abcdefghij"
    assert chunks[1]["chunk_text"].startswith("ij")


def test_query_log_redacts_common_personal_identifiers():
    cleaned = redact_sensitive_data("ID 123456789012, phone 9876543210, email person@example.com")
    assert "123456789012" not in cleaned
    assert "9876543210" not in cleaned
    assert "person@example.com" not in cleaned
    assert "[REDACTED_ID]" in cleaned
