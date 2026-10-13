# Validation record

Environment: Python 3.12; dependencies installed successfully with pip. No local PostgreSQL server/tools were available; port 5432 refused connections. Do not interpret skipped integration tests as passing.

| Command / inspection | Result |
| --- | --- |
| `pip install` runtime and development dependencies | PASS |
| AST parse every project Python file; `python -m compileall -q app migrations tests` | PASS |
| `python -c 'import app.main; ...openapi...'` | PASS: 17 paths, 12 tags (system, auth, users, policies, claims, assignments, notes, status, documents, rag, analytics, audit) |
| `ruff check .` | PASS after import sorting |
| `mypy app migrations tests` | PASS: 10 source files |
| `alembic upgrade head --sql` | PASS: offline SQL includes all model tables and revision 0001 |
| `alembic current` | NOT EXECUTABLE: local PostgreSQL unavailable; connection refused. Alembic import path corrected and offline migration checked. |
| `python -m app.seed` | NOT EXECUTABLE: local PostgreSQL unavailable; connection refused. Idempotency not verified against a running DB. |
| `pytest -q` | 2 passed, 1 skipped (PostgreSQL-backed workflow); PostgreSQL integration tests **were not executed**. |
| `coverage run -m pytest -q && coverage report -m` | 2 passed, 1 skipped; 50% overall (DB workflow not run). |
| `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` | Port 8000 in use (address already in use); alternate port 18763 passed. Server stopped afterwards. |
| `/health`, `/docs`, `/redoc`, `/openapi.json` on alternate port | HTTP 200 each. |
| Actual database-backed role login, bearer token, curl/Swagger workflow | NOT EXECUTED; requires PostgreSQL and migrations/seed. Full manual commands supplied in README. |
| Model/Alembic alignment | Offline migration imports same `Base.metadata` as application models; generated SQL inspected; live schema comparison unavailable. |
| Filename and content search for prohibited provider/deployment assumptions | No prohibited runtime files or runtime provider calls; omission terms appear only in checklist and README explanations. |
| `.env`, credentials, archives, caches, uploaded files in final ZIP | Excluded; no `.env` or generated credentials included. |

Limitations: test schema is recreated via `Base.metadata` rather than via migration fixture. SQL-level status history immutability is not enforced; API exposes no history mutation route. Local lexical RAG does not perform semantic similarity or answer synthesis. Real database acceptance criteria must be verified locally with PostgreSQL before operational use.

## Local PostgreSQL setup guide update

`LOCAL_SETUP.md` added with step-by-step Ubuntu/Debian setup, macOS/Windows differences, role and database creation, connection verification, Alembic, seeding, localhost Uvicorn, four demo logins, token usage, safe test database setup, and troubleshooting. The guide has not been tested end-to-end against PostgreSQL here because this environment has no PostgreSQL server.

## Per-OS setup documentation update

Added `SETUP_WINDOWS.md` (PowerShell and official PostgreSQL installer), `SETUP_LINUX.md` (Ubuntu/Debian), and `SETUP_MACOS.md` (Homebrew), and linked them in README. Commands have been reviewed for app configuration and test database safety. Windows and macOS commands were not executed in this Linux environment. PostgreSQL-backed integration remains unexecuted here.
