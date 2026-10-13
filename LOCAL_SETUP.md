# Combined reference: run ClaimIQ with PostgreSQL on localhost

For self-contained OS-specific steps, use [SETUP_WINDOWS.md](SETUP_WINDOWS.md), [SETUP_LINUX.md](SETUP_LINUX.md), or [SETUP_MACOS.md](SETUP_MACOS.md).

This guide assumes **Ubuntu/Debian, Python 3.10+, and local PostgreSQL**. Run commands in a terminal; run the SQL as the PostgreSQL administrator. Windows/macOS differences follow below. The FastAPI server connects to PostgreSQL using `DATABASE_URL`; there is **no SQLite fallback**. All data in this guide is disposable demo data. Do not expose the demo server to the internet.

## 1. Extract the ZIP and enter the project

```bash
unzip claimiq-backend-pure-local.zip
cd claimiq-backend-pure-local
```

All subsequent commands run from this project directory unless explicitly indicated. If you already extracted it, just `cd` into it.

## 2. Install and start PostgreSQL

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install postgresql postgresql-client python3 python3-venv
sudo systemctl start postgresql
sudo systemctl enable postgresql
pg_isready -h 127.0.0.1 -p 5432
```

Expected: `127.0.0.1:5432 - accepting connections`. If your Linux system has no systemd, use its PostgreSQL service manager. On macOS, install PostgreSQL with Homebrew (`brew install postgresql@16`) and start its service (`brew services start postgresql@16`); make sure its binaries are on PATH. Windows: install PostgreSQL using the official installer, select port 5432, ensure its Windows service is running, and use `psql` in SQL Shell or add its `bin` folder to PATH.

## 3. Create a local login and two databases

Ubuntu/Debian (replace the example password with a strong password of your own):

```bash
sudo -u postgres psql
```

In the `postgres=#` prompt, run each line separately:

```sql
CREATE ROLE claimiq_local LOGIN PASSWORD 'choose-a-strong-local-password';
CREATE DATABASE claimiq OWNER claimiq_local;
CREATE DATABASE claimiq_test OWNER claimiq_local;
\q
```

If these objects already exist, **do not drop valuable databases**. Instead confirm the names, owner and access; use an existing PostgreSQL role/password if appropriate. On macOS where `sudo -u postgres` is unavailable, connect as your local PostgreSQL administrator with `psql postgres` or `psql -U postgres -h 127.0.0.1`; on Windows use the installed SQL Shell as `postgres`.

Check authentication (enter password when prompted):

```bash
psql -h 127.0.0.1 -p 5432 -U claimiq_local -d claimiq -W -c 'SELECT current_database(), current_user, version();'
psql -h 127.0.0.1 -p 5432 -U claimiq_local -d claimiq_test -W -c 'SELECT current_database(), current_user;'
```

The first query must report `claimiq`; the second must report `claimiq_test`. PostgreSQL must accept password authentication over loopback (its `pg_hba.conf` typically has `scram-sha-256` for `127.0.0.1/32`). If you get `password authentication failed`, verify password and user, then check `pg_hba.conf` and restart PostgreSQL after changes.

## 4. Create a Python environment and install dependencies

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell (use `py` if `python` is not on PATH):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use `Set-ExecutionPolicy -Scope Process Bypass` only in that PowerShell session, then activate. Do not package or commit `.venv`.

## 5. Configure the PostgreSQL connection (each terminal)

Linux/macOS (substitute your chosen password; if password contains `@`, `/`, `:`, `#`, or `%`, URL-encode those characters or use a simpler local-only password):

```bash
export DATABASE_URL='postgresql+psycopg2://claimiq_local:choose-a-strong-local-password@127.0.0.1:5432/claimiq'
export TEST_DATABASE_URL='postgresql+psycopg2://claimiq_local:choose-a-strong-local-password@127.0.0.1:5432/claimiq_test'
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

PowerShell:

```powershell
$env:DATABASE_URL='postgresql+psycopg2://claimiq_local:choose-a-strong-local-password@127.0.0.1:5432/claimiq'
$env:TEST_DATABASE_URL='postgresql+psycopg2://claimiq_local:choose-a-strong-local-password@127.0.0.1:5432/claimiq_test'
$env:JWT_SECRET=python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

The test URL must point to the separate, disposable database named **exactly** `claimiq_test`. The app uses `DATABASE_URL`; pytest uses `TEST_DATABASE_URL`. If you use another terminal for tests, repeat the exports there. The JWT secret should be stable during a server session; restarting with a different secret invalidates existing tokens. Avoid sharing URLs or passwords in screenshots or logs. Environment variables are only set for the current shell and are not stored in the ZIP. Without `DATABASE_URL`, the app defaults to a local peer/OS-user connection which may fail; explicitly setting the URL is recommended.

Verify the Python connection without displaying the password:

```bash
python -c 'from app.db import engine; from sqlalchemy import text; c=engine.connect(); print(c.execute(text("select current_database(), current_user")).one()); c.close()'
```

Expected: `('claimiq', 'claimiq_local')` (format can vary).

## 6. Create schema with Alembic; seed demo data

```bash
alembic upgrade head
alembic current
python -m app.seed
python -m app.seed
```

Expected Alembic revision: `0001 (head)`; the second seed execution should succeed without duplicating users, policy or the demo claim. Confirm the database tables:

```bash
psql -h 127.0.0.1 -U claimiq_local -d claimiq -W -c '\dt'
psql -h 127.0.0.1 -U claimiq_local -d claimiq -W -c 'SELECT username, role FROM users ORDER BY id;'
```

Expected roles: `admin`, `adjuster`, `reviewer`, `customer`. Demo password for each: `demo123` (loopback-only synthetic data).

## 7. Run the API; view interactive documentation

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Leave that terminal open. In a browser open:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- OpenAPI: http://127.0.0.1:8000/openapi.json
- Health: http://127.0.0.1:8000/health

Health returns `{"status":"ok"}`. Health does not itself test database connectivity; the connection check in step 5 does.

## 8. Log in and send authenticated requests

In **another terminal**, set up an environment and `DATABASE_URL` as in steps 4–5 if running Python commands or tests there. Basic `curl` requests need neither environment variable nor activated venv.

```bash
BASE=http://127.0.0.1:8000
curl -s -X POST "$BASE/auth/token" -d 'username=admin&password=demo123'
TOKEN=$(curl -s -X POST "$BASE/auth/token" -d 'username=admin&password=demo123' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/users/me"
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/policies"
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/claims"
```

For PowerShell, use `curl.exe` (PowerShell's `curl` alias differs), and set the token this way:

```powershell
$base='http://127.0.0.1:8000'
$token=(Invoke-RestMethod -Method Post -Uri "$base/auth/token" -Body @{username='admin';password='demo123'}).access_token
Invoke-RestMethod -Uri "$base/users/me" -Headers @{Authorization="Bearer $token"}
```

To log in as each role on Linux/macOS:

```bash
for role in admin reviewer adjuster customer; do
  printf '%s: ' "$role"
  curl -s -X POST "$BASE/auth/token" -d "username=$role&password=demo123" | python -c 'import json,sys; d=json.load(sys.stdin);print(d.get("token_type",d))'
done
```

In Swagger, click **Authorize**, enter one of the usernames and `demo123`, click Authorize, then try `GET /users/me`. Re-authorize to switch roles. Customers see only their claims; adjusters see assigned claims; reviewers/admins have broader access. Swagger includes endpoints for policy, claim, assignment, note, status/history, document approval/download, RAG, analytics and audit. See the README for a longer curl session. Do not share or log bearer tokens.

## 9. Test and inspect quality checks

In an activated venv, with `TEST_DATABASE_URL` pointed to **disposable** `claimiq_test`:

```bash
pytest -q
ruff check .
mypy app migrations tests
python -m compileall -q app migrations tests
coverage run -m pytest -q
coverage report -m
```

**Warning:** the PostgreSQL test fixture drops and recreates tables in `claimiq_test`! It rejects any URL whose database name is not exactly `/claimiq_test`; never use a valuable database named `claimiq_test`. If PostgreSQL is unavailable, tests skip the integration test; a skip is *not* a successful database test.

## 10. Files and local-only retrieval

Uploads default to the `uploads/` directory under the project working directory, or set `UPLOAD_DIR` to a writable local location before starting Uvicorn. TXT/PDF documents are saved under generated UUID filenames; extracted text chunks are stored in PostgreSQL. A reviewer/admin must set a document both active and approved for `/rag/ask` to retrieve it. RAG is local lexical retrieval with source citations, not a remote LLM or hosted vector service. No external AI/API dependencies are needed.

## 11. Stop, restart and troubleshoot

- Stop Uvicorn with Ctrl-C in its terminal. Start it again using the step 7 command; PostgreSQL data persists.
- `connection refused`: confirm PostgreSQL is running using `pg_isready -h 127.0.0.1 -p 5432`; check `DATABASE_URL` port/host and `psql` connection from step 3.
- `password authentication failed`: check PostgreSQL role/password and loopback `pg_hba.conf`; update `DATABASE_URL` in the current shell.
- `permission denied for schema public`: verify the database is owned by `claimiq_local`; on installations where ownership is not sufficient, an administrator can run `GRANT USAGE, CREATE ON SCHEMA public TO claimiq_local;` while connected to **each** respective database.
- `address already in use` on port 8000: stop the existing process or launch with `--port 8001` and update the browser/curl URLs.
- `revision not found`: confirm project directory, environment variables, and `alembic heads`; use `alembic upgrade head` on the correct database, rather than blindly stamping revisions.
- `401 Invalid or expired bearer token`: log in again, check the `Bearer ` prefix, `JWT_SECRET` stability and system time.
- Upload failure: check free disk space and `UPLOAD_DIR` write permissions. Uploaded files remain on disk after a database reset; verify paths before cleanup.
- Unexpected test skip: check `TEST_DATABASE_URL`, ensure `claimiq_test` exists, and connect with `psql` as in step 3.

**Reset only disposable development data**: stop the server; verify names with `psql -l`. As the local PostgreSQL admin, drop/recreate **only** `claimiq`, leaving `claimiq_test` and every other database untouched:

```bash
sudo -u postgres dropdb claimiq
sudo -u postgres createdb -O claimiq_local claimiq
alembic upgrade head
python -m app.seed
```

On non-Ubuntu systems use your local PostgreSQL administrator instead of `sudo -u postgres`. This does not delete uploaded files. Never run the reset against production or a non-disposable database.
