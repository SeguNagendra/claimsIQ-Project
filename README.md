# ClaimIQ — pure-local backend

Local FastAPI + PostgreSQL application. No external AI/API dependencies, external credentials, network inference, or hosted search. RAG is deterministic lexical retrieval over locally extracted document chunks; it is **not** generative AI. Demo passwords and fallback JWT secret are for loopback-only development; set `JWT_SECRET` to a random value before any shared use. Do not use synthetic demo accounts in production.

**First-time users: choose your OS-specific, step-by-step PostgreSQL setup guide:**

- **Windows (PowerShell + PostgreSQL installer):** [SETUP_WINDOWS.md](SETUP_WINDOWS.md)
- **Linux (Ubuntu/Debian):** [SETUP_LINUX.md](SETUP_LINUX.md)
- **macOS (Homebrew):** [SETUP_MACOS.md](SETUP_MACOS.md)

Each guide covers database role/creation, separate `claimiq_test`, Python setup, credentials, Alembic migrations, seeding, Uvicorn, Swagger, authentication, tests, files, troubleshooting and safe reset. [LOCAL_SETUP.md](LOCAL_SETUP.md) is an additional combined reference. The abbreviated Unix commands below assume local PostgreSQL is already configured; **Windows users should follow SETUP_WINDOWS.md instead**.

## Local setup (Python 3.10+, PostgreSQL)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Start your OS PostgreSQL service and provision two disposable databases, e.g.:
createdb claimiq
createdb claimiq_test
# Set credentials appropriate to your local PostgreSQL installation:
export DATABASE_URL='postgresql+psycopg2://localhost/claimiq'
export TEST_DATABASE_URL='postgresql+psycopg2://localhost/claimiq_test'
export JWT_SECRET='replace-with-a-long-random-local-secret'
alembic upgrade head
alembic current
python -m app.seed
python -m app.seed  # safe to repeat
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs (Swagger), `/redoc` (ReDoc), `/openapi.json`, `/health`. Swagger **Authorize** uses username/password via `/auth/token`. Demo roles: `admin`, `reviewer`, `adjuster`, `customer`; each has password `demo123`. Use localhost only.

## End-to-end session (another terminal)

```bash
BASE=http://127.0.0.1:8000
for role in admin reviewer adjuster customer; do
  curl -s -X POST "$BASE/auth/token" -d "username=$role&password=demo123"
done
TOKEN=$(curl -s -X POST "$BASE/auth/token" -d 'username=admin&password=demo123' | python -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
H="Authorization: Bearer $TOKEN"
curl -H "$H" "$BASE/users/me"
curl -H "$H" "$BASE/users"
curl -H "$H" "$BASE/policies"
curl -H "$H" "$BASE/claims"
curl -H "$H" "$BASE/claims/1"
ADJUSTER_ID=$(curl -s -H "$H" "$BASE/users" | python -c 'import json,sys;print(next(u["id"] for u in json.load(sys.stdin) if u["role"]=="adjuster"))')
curl -H "$H" -H 'Content-Type: application/json' -d "{\"user_id\":$ADJUSTER_ID}" "$BASE/claims/1/assignment"
curl -H "$H" -H 'Content-Type: application/json' -d '{"status":"under_review"}' "$BASE/claims/1/status"
curl -H "$H" "$BASE/claims/1/history"
curl -H "$H" -H 'Content-Type: application/json' -d '{"text":"Synthetic review"}' "$BASE/claims/1/notes"
curl -H "$H" "$BASE/claims/1/notes"
printf 'Water damage deductible is 500 dollars.\n' > /tmp/claimiq-example.txt
curl -H "$H" -F file=@/tmp/claimiq-example.txt "$BASE/documents"
curl -H "$H" -H 'Content-Type: application/json' -X PATCH -d '{"active":true,"approved":true}' "$BASE/documents/1"
curl -H "$H" "$BASE/documents"
curl -H "$H" -H 'Content-Type: application/json' -d '{"question":"water deductible"}' "$BASE/rag/ask"
curl -H "$H" -H 'Content-Type: application/json' -d '{"question":"intergalactic platypus"}' "$BASE/rag/ask"
curl -H "$H" "$BASE/analytics/summary"
curl -H "$H" "$BASE/audit"
```

Use Swagger to exercise `POST /policies`, `POST /claims`, `GET /documents/{id}/download`, status override (admin, nonempty justification), and all role-specific requests; replace example IDs with actual returned IDs. Claims require active policies. An adjuster only sees assigned claims; customers only see their own. Reviewers and admins see all. Only approved, active document chunks are searchable. Source text plus `[document:id:chunk:id]` citations is returned, or explicit no-match. Audit records only actor ID, action, resource type and time; it does not record passwords, tokens or full PII.

## Tests and checks

```bash
pytest -q
ruff check .
mypy app migrations tests
python -m compileall -q app migrations tests
python -c 'import app.main; print(app.main.app.openapi()["paths"].keys())'
coverage run -m pytest -q && coverage report -m
```

Tests **only** connect to `claimiq_test`; a strict name and driver guard runs before write operations. Integration tests skip if PostgreSQL cannot be reached; a skip does not constitute a pass. Test fixture recreates **all tables in claimiq_test**, so it must be disposable. Never set `TEST_DATABASE_URL` to a valuable database.

## Troubleshooting and reset

- PostgreSQL refused: start local service (`sudo systemctl start postgresql` on systems using systemd), check `pg_isready`, host/port, firewall and `psql` connectivity. Authentication failure: set correct credentials in `DATABASE_URL` and `TEST_DATABASE_URL`, configure local role/`pg_hba.conf`; percent-encode special characters in URL passwords.
- Port 8000 occupied: stop previous Uvicorn process or select `--port 8001`; change curl base accordingly. Shut down the Uvicorn terminal with Ctrl-C.
- Migration revision mismatch: run `alembic current`, `alembic heads`, verify working directory and URL, then `alembic upgrade head`; never stamp an incompatible valuable database.
- Upload permissions: set `UPLOAD_DIR` to a writable directory. Defaults to `uploads/` relative to the working directory; UUID filenames on disk, original basename in the database. Do not serve the directory directly. Remove orphan files manually after test runs if needed.
- JWT error: repeat login after secret rotation/expiry; check `Authorization: Bearer <token>` and system clock. Do not paste tokens into logs.
- Test safety guard: `TEST_DATABASE_URL` must be PostgreSQL and its exact database path must be `/claimiq_test`.

**Disposable dev reset only**: stop the server; verify target database names with `psql -l` and confirm no valuable data. Then `dropdb claimiq && createdb claimiq && alembic upgrade head && python -m app.seed`. This must **not** drop `claimiq_test`, other databases, or production data. Files in `UPLOAD_DIR` are separate and not removed by database reset; clean only disposable files after verifying the directory.
