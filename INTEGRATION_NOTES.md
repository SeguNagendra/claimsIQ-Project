# ClaimIQ RAG Integration Notes

## Added

- Azure Blob Storage-backed PDF/DOCX upload.
- Text extraction and configurable overlapping chunking.
- Azure OpenAI embeddings and Azure AI Search vector indexing/retrieval.
- Azure OpenAI Responses API answer generation with source references.
- Active/deactivated/superseded document filtering and version replacement support.
- JWT/RBAC protection: Admin manages documents; Admin/Reviewer/Adjuster/Support Agent can query approved policy content.
- Query logging with source references, latency and status; common phone/email/Aadhaar-like identifiers are redacted before persistence.
- Versioned SRS endpoint aliases under `/api/v1/` and unversioned aliases for consistency with existing routes.
- Search index setup script: `python -m scripts.create_search_index`.

## Setup

1. Install requirements: `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and configure Azure Blob Storage, Azure AI Search and Azure OpenAI. Use exact deployment names in `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` and `AZURE_OPENAI_CHAT_DEPLOYMENT`.
3. Authenticate with `az login` if using Microsoft Entra ID, and grant the identity appropriate Blob, Search and Azure OpenAI permissions.
4. Create the Search vector index: `python -m scripts.create_search_index`.
5. Create new tables in the existing database: `python -m app.init_db`. Existing Claims and Analytics tables are not dropped.
6. Run `uvicorn app.main:app --reload` and use `/docs`.

## Verification

- Added RAG route/security and chunking/redaction tests: 5 passed in the local test run.
- The full suite reports 3 existing failures also present when running the original `Claims.zip`: two tests expect a `POST /policies` endpoint that is absent from the original API, and one expects Adjusters to be blocked from approving claims although the original status route currently permits it. These were left unchanged to keep this task scoped to RAG integration.
- Azure service calls were not live-tested because this environment has no configured Azure endpoints/credentials.
