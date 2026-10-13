# Linux (Ubuntu/Debian): run ClaimIQ with PostgreSQL

Commands below assume Ubuntu/Debian and a terminal in the extracted repository. Other distributions: install equivalent PostgreSQL/server/client and Python venv packages with your package manager, then use the same SQL and Python commands. Use only disposable local databases and localhost demo accounts.

## 1. Extract, install, start

```bash
unzip claimiq-backend-pure-local.zip
cd claimiq-backend-pure-local
sudo apt update
sudo apt install postgresql postgresql-client python3 python3-venv
sudo systemctl start postgresql
pg_isready -h 127.0.0.1 -p 5432
```

If already extracted, just `cd claimiq-backend-pure-local`. Expected `pg_isready` output: `accepting connections`. On systems without systemd, use your distro's PostgreSQL service manager.

## 2. Create role and separate databases

```bash
sudo -u postgres psql
```

At `postgres=#` run these, replacing the sample password:

```sql
CREATE ROLE claimiq_local LOGIN PASSWORD 'replace-with-your-own-strong-password';
CREATE DATABASE claimiq OWNER claimiq_local;
CREATE DATABASE claimiq_test OWNER claimiq_local;
\q
```

Do not drop an existing database until verifying it has no valuable data. `claimiq_test` is **disposable**: tests destroy its tables. Check both connections (enter your password when prompted):

```bash
psql -h 127.0.0.1 -p 5432 -U claimiq_local -d claimiq -W -c 'SELECT current_database(), current_user;'
psql -h 127.0.0.1 -p 5432 -U claimiq_local -d claimiq_test -W -c 'SELECT current_database(), current_user;'
```

## 3. Python environment and configuration

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg2://claimiq_local:replace-with-your-own-strong-password@127.0.0.1:5432/claimiq'
export TEST_DATABASE_URL='postgresql+psycopg2://claimiq_local:replace-with-your-own-strong-password@127.0.0.1:5432/claimiq_test'
export JWT_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
python -c 'from sqlalchemy import text; from app.db import engine; c=engine.connect(); print(c.execute(text("select current_database(), current_user")).one()); c.close()'
```

Replace the password in both URL values. URL-encode reserved characters (`@` -> `%40`, `%` -> `%25`) in passwords. The final query must report database `claimiq`. Exports are per-shell; repeat when opening another shell to run tests. The secret must remain stable if you want old tokens to keep working.

## 4. Migrate, seed twice, serve

```bash
python -m alembic upgrade head
python -m alembic current
python -m app.seed
python -m app.seed
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Expected revision: `0001 (head)`; repeated seed should not duplicate data. Leave Uvicorn running. Open http://127.0.0.1:8000/docs (Swagger), http://127.0.0.1:8000/redoc, http://127.0.0.1:8000/openapi.json, or http://127.0.0.1:8000/health. Health does **not** test PostgreSQL; step 3 does.

## 5. Log in and call API (another terminal)

```bash
BASE=http://127.0.0.1:8000
for role in admin reviewer adjuster customer; do
  printf '%s: ' "$role"
  curl -s -X POST "$BASE/auth/token" -d "username=$role&password=demo123" | python3 -c 'import json,sys; r=json.load(sys.stdin);print(r.get("token_type",r))'
done
TOKEN=$(curl -s -X POST "$BASE/auth/token" -d 'username=admin&password=demo123' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -H "Authorization: Bearer $TOKEN" "$BASE/users/me"
curl -H "Authorization: Bearer $TOKEN" "$BASE/policies"
curl -H "Authorization: Bearer $TOKEN" "$BASE/claims"
curl -H "Authorization: Bearer $TOKEN" "$BASE/analytics/summary"
```

All demo roles use password `demo123` and are localhost-only. In Swagger click **Authorize**, log in and try the APIs; re-authorize to change role. The README includes extended curl examples for policies, claims, assignments, notes, status, uploads/approval, local RAG and audit. Never share bearer tokens.

## 6. Tests (separate shell, with step 3 exports and activated venv)

```bash
python -m pytest -q
python -m ruff check .
python -m mypy app migrations tests
python -m compileall -q app migrations tests
python -m coverage run -m pytest -q
python -m coverage report -m
```

Tests recreate all tables in `claimiq_test` and reject any URL with a different database name; **do not store valuable data there**. A skipped PostgreSQL test is not a passed test.

## 7. Shutdown, storage, recovery and safe reset

Ctrl-C stops Uvicorn. Uploads default to `uploads/` in your working directory (or set `UPLOAD_DIR` before starting the server); metadata/text chunks are in PostgreSQL. RAG works offline: only approved, active chunks are retrieved with citations, no external AI/API dependencies.

- Connection refused: `pg_isready -h 127.0.0.1 -p 5432`, check service, URL host/port.
- Bad password: check `psql` login and `pg_hba.conf` loopback authentication; URL-encode reserved password characters.
- `permission denied for schema public`: connect to each affected database as administrator and `GRANT USAGE, CREATE ON SCHEMA public TO claimiq_local;`.
- Port 8000 taken: use `--port 8001` and change browser/curl URLs.
- Missing revision: `python -m alembic heads`; check cwd/URL; do not stamp an unknown DB.
- Expired JWT: log in again; ensure stable `JWT_SECRET` and `Bearer ` prefix.
- Upload issues: check writable `UPLOAD_DIR`, file size and disk space.

To reset **only disposable** `claimiq`: stop the server; verify names/data with `psql -l`. Then:

```bash
sudo -u postgres dropdb claimiq
sudo -u postgres createdb -O claimiq_local claimiq
python -m alembic upgrade head
python -m app.seed
```

Do not reset `claimiq_test` or any valuable/production database. Uploads remain on disk after a database reset.
