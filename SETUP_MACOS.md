# macOS: run ClaimIQ with PostgreSQL

Use Terminal or zsh on macOS. Prerequisites: Homebrew, Python 3.10+ and the extracted repository. Use disposable local databases and localhost-only demo accounts. This guide uses **Homebrew PostgreSQL 16**; if you installed another version, update `postgresql@16` and the binary path accordingly.

## 1. Extract and install prerequisites

If you downloaded the ZIP into Downloads:

```bash
cd ~/Downloads
unzip claimiq-backend-pure-local.zip
cd claimiq-backend-pure-local
brew install python postgresql@16
brew services start postgresql@16
```

If it is already extracted elsewhere, simply enter the extracted `claimiq-backend-pure-local` folder. Add the PostgreSQL commands to this Terminal session's PATH (works for both Apple Silicon and Intel Homebrew):

```bash
export PATH="$(brew --prefix postgresql@16)/bin:$PATH"
pg_isready -h 127.0.0.1 -p 5432
python3 --version
```

Expected `pg_isready`: `accepting connections`. Repeat the PATH export in new terminals if necessary. macOS installations using Postgres.app or EnterpriseDB instead of Homebrew must use that installation's tools and service control; do not start two servers on port 5432.

## 2. Create the application role and two databases

Homebrew commonly sets up your macOS username as a PostgreSQL administrator. Try `psql postgres` (if that fails, try `psql -U postgres -h 127.0.0.1 -d postgres` using your admin credentials). At its prompt, replace the sample password and run:

```sql
CREATE ROLE claimiq_local LOGIN PASSWORD 'replace-with-your-own-strong-password';
CREATE DATABASE claimiq OWNER claimiq_local;
CREATE DATABASE claimiq_test OWNER claimiq_local;
\q
```

If your account lacks the `CREATEROLE` privilege, use your existing PostgreSQL administrator account. Do not drop existing valuable databases. The `claimiq_test` database is **disposable**: pytest drops and recreates its tables.

Verify both databases with the local role (enter its password):

```bash
psql -h 127.0.0.1 -U claimiq_local -d claimiq -W -c 'SELECT current_database(), current_user;'
psql -h 127.0.0.1 -U claimiq_local -d claimiq_test -W -c 'SELECT current_database(), current_user;'
```

## 3. Prepare Python and configure PostgreSQL URL

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

Replace both sample passwords with the real one; URL-encode reserved password characters, e.g., `@` as `%40`. Python's final query must report `claimiq`. Variables apply only to this terminal; export them again for tests in another terminal. Keep `JWT_SECRET` consistent between server restarts or old tokens will expire.

## 4. Initialize schema and synthetic users, then run Uvicorn

```bash
python -m alembic upgrade head
python -m alembic current
python -m app.seed
python -m app.seed
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Revision should show `0001 (head)`; repeated seed is idempotent. Open http://127.0.0.1:8000/docs (Swagger), http://127.0.0.1:8000/redoc, http://127.0.0.1:8000/openapi.json, and http://127.0.0.1:8000/health. Health shows API availability, not DB connectivity: the step 3 query checks DB.

## 5. Try all demo roles and authenticated calls

In another Terminal window:

```bash
BASE=http://127.0.0.1:8000
for role in admin reviewer adjuster customer; do
  printf '%s: ' "$role"
  curl -s -X POST "$BASE/auth/token" -d "username=$role&password=demo123" | python3 -c 'import json,sys; d=json.load(sys.stdin);print(d.get("token_type",d))'
done
TOKEN=$(curl -s -X POST "$BASE/auth/token" -d 'username=admin&password=demo123' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -H "Authorization: Bearer $TOKEN" "$BASE/users/me"
curl -H "Authorization: Bearer $TOKEN" "$BASE/policies"
curl -H "Authorization: Bearer $TOKEN" "$BASE/claims"
curl -H "Authorization: Bearer $TOKEN" "$BASE/analytics/summary"
```

The four usernames shown in the loop all use password `demo123`. Swagger's **Authorize** button lets you authenticate and try the entire API; re-authorize to change roles. README contains a longer curl walkthrough covering policy, claim, assignment, status, notes, document approval, RAG and audit. Don't share tokens.

## 6. Run tests and quality checks

From an activated venv with BOTH `DATABASE_URL` and `TEST_DATABASE_URL` set:

```bash
python -m pytest -q
python -m ruff check .
python -m mypy app migrations tests
python -m compileall -q app migrations tests
python -m coverage run -m pytest -q
python -m coverage report -m
```

Tests reject any URL that does not target a database named **exactly `claimiq_test`** and drop/recreate its tables. Verify this database is disposable. A skipped integration test is **not** a database test pass.

## 7. Stop and troubleshoot

Ctrl-C stops Uvicorn. Stop the Homebrew database service, only if desired, with `brew services stop postgresql@16`. Files uploaded via API default to `uploads/` under the current working directory (or your `UPLOAD_DIR`), while chunks/metadata live in PostgreSQL. Local lexical RAG needs no external AI/API.

- `connection refused`: check `brew services list`, `pg_isready -h 127.0.0.1 -p 5432`, and URL/port.
- Password error: retry `psql` with `-W`, confirm `claimiq_local` credentials and URL escaping.
- `permission denied for schema public`: as DB admin connect to the specific database and run `GRANT USAGE, CREATE ON SCHEMA public TO claimiq_local;`.
- Port 8000 occupied: start API with `--port 8001` and update URLs.
- Alembic mismatch: check `python -m alembic heads`, URL and cwd; don't blindly stamp revisions.
- JWT 401: log in again; check `Bearer ` prefix and stable `JWT_SECRET`.
- Upload errors: check free space and `UPLOAD_DIR` write permission.

To reset **only disposable** `claimiq`, stop the API, inspect `psql -l`, then **as a PostgreSQL admin** run:

```bash
dropdb claimiq
createdb -O claimiq_local claimiq
python -m alembic upgrade head
python -m app.seed
```

If these commands report insufficient privileges, run the `dropdb`/`createdb` commands as your PostgreSQL admin role. Never drop `claimiq_test` or valuable databases. Database reset does not remove files in `uploads/`.
