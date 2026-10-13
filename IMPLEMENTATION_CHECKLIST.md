# Implementation checklist

No SRS was attached; no SRS IDs are available to map. Status below identifies implemented scope; database integration requires local PostgreSQL verification.

| Requirement / rule / entity / API | Source | Test / acceptance |
| --- | --- | --- |
| PostgreSQL schema, migrations; User, Policy, Claim, StatusHistory, Note, Document, Chunk, Audit | `app/models.py`, `app/db.py`, `migrations/env.py`, `migrations/versions/0001_initial.py` | `alembic upgrade head`, `alembic current`; database integration not verified here |
| Idempotent synthetic data, four demo roles | `app/seed.py`, `app/security.py` | run seed twice; `tests/test_app.py::test_workflow` (requires PostgreSQL) |
| Login, bearer JWT, PBKDF2 password verification, RBAC | `app/security.py`, `app/main.py` `/auth/token`, `/users/me`, `/users` | `tests/test_app.py::test_hash`, `test_workflow` |
| Policies and active-policy claim validation; claim row visibility | `app/main.py` `/policies`, `/claims` | `test_workflow`; verify inactive policy rejection separately |
| Assignment, notes, workflow/justified admin override, append-only history via API | `app/main.py` `/claims/{id}/assignment`, `/notes`, `/status`, `/history`; `app/models.py` | `test_workflow`; direct SQL update/delete protection **not implemented** |
| Local UUID uploads, PDF/TXT extraction, approval, retrieval | `app/main.py` `/documents`, `/documents/{id}/download`, `/documents/{id}`; `app/config.py` | `test_workflow`; local storage under `UPLOAD_DIR` |
| Approved and active lexical retrieval; citations, explicit no match; no external AI/API calls | `app/main.py` `/rag/ask` | `test_workflow` |
| Pandas metrics: counts by status, total/average amount, assigned | `app/main.py` `/analytics/summary` | `test_workflow` |
| Minimal audit without passwords, tokens or full PII | `app/main.py` `/audit`; `app/models.py` | `test_workflow`; inspect stored rows |
| Local PostgreSQL installation, connection, migration, Swagger, tests, troubleshooting | `SETUP_WINDOWS.md`, `SETUP_LINUX.md`, `SETUP_MACOS.md`, `LOCAL_SETUP.md`, `README.md`, `app/config.py`, `app/db.py` | Follow steps on a host with PostgreSQL; not executable in this environment |
| OpenAPI, Swagger, ReDoc, health | `app/main.py` | `test_openapi_and_health` |
| Test database name guard | `tests/test_app.py` | inspect fixture; test writes only to `claimiq_test` |
| Docker | — | Intentionally omitted for this pure-local version per explicit user instruction. |
| Containerization | — | Intentionally omitted for this pure-local version per explicit user instruction. |
| CI/CD | — | Intentionally omitted for this pure-local version per explicit user instruction. |
| Cloud deployment | — | Intentionally omitted for this pure-local version per explicit user instruction. |
| External LLM | — | Intentionally omitted for this pure-local version per explicit user instruction. |
| External vector-store | — | Intentionally omitted for this pure-local version per explicit user instruction. |
