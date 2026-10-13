# Windows: PostgreSQL + ClaimIQ, step by step

**Use PowerShell** for all `powershell` blocks below; use the PostgreSQL SQL Shell (`psql`) only where explicitly indicated. Python 3.10+, PostgreSQL, and this extracted repository must be on your machine. All accounts/data below are for **local development only**. Do not expose the demo API to other computers.

## 1. Install Python and PostgreSQL

1. Install a supported Python 3 version from python.org. During setup tick **Add python.exe to PATH**. Open a **new PowerShell** and run:

   ```powershell
   py --version
   ```

2. Install PostgreSQL with the official Windows installer. Keep port **5432** and remember the password you set for PostgreSQL's `postgres` administrator account. Accept installation of command-line tools (including **SQL Shell (psql)**). The optional Stack Builder is not needed.
3. From Start, open **Services** (`services.msc`), find `postgresql-x64-<version>` and ensure it shows **Running**. If stopped, right-click and Start. You can also run `Get-Service postgresql*` in PowerShell; if needed start the service from an elevated PowerShell with `Start-Service -Name 'postgresql-x64-<version>'` (replace the name with the one shown by `Get-Service`).
4. `psql` may not be on PATH. The installer supplies **SQL Shell (psql)** in Start, which you can use without PATH changes. Alternatively find `C:\Program Files\PostgreSQL\<version>\bin\psql.exe` and run it using PowerShell's call operator `&`. For example:

   ```powershell
   # Change 16 to the version installed on your PC; this line is optional.
   & 'C:\Program Files\PostgreSQL\16\bin\pg_isready.exe' -h 127.0.0.1 -p 5432
   ```

   Expected: `accepting connections`. **Do not** type `<version>` literally: it is a placeholder.

## 2. Unzip the project

Use Windows Explorer **Extract All**, or from the directory holding the downloaded ZIP:

```powershell
Expand-Archive -LiteralPath .\claimiq-backend-pure-local.zip -DestinationPath . -Force
Set-Location .\claimiq-backend-pure-local
Get-ChildItem README.md,requirements.txt,alembic.ini
```

If you already extracted it, just `Set-Location` to the extracted `claimiq-backend-pure-local` directory. Every later PowerShell command assumes you are **inside that directory**.

## 3. Create the local PostgreSQL role and databases

Open **SQL Shell (psql)** from the Start menu. For prompts `Server`, `Database`, `Port`, `Username` accept the defaults (`localhost`, `postgres`, `5432`, `postgres`), and enter the PostgreSQL administrator password you chose in step 1. At the `postgres=#` prompt enter, **one SQL statement per line**:

```sql
CREATE ROLE claimiq_local LOGIN PASSWORD 'replace-with-your-own-strong-password';
CREATE DATABASE claimiq OWNER claimiq_local;
CREATE DATABASE claimiq_test OWNER claimiq_local;
\q
```

Use an actual strong local password in place of the sample. The names `claimiq` and `claimiq_test` must match exactly; **tests drop/recreate tables in claimiq_test**. If a role/database already exists, do not drop anything until you have verified it contains no important data. PostgreSQL on Windows normally accepts password logins over loopback; if login fails, review the password and PostgreSQL `pg_hba.conf` (typically in its `data` directory).

To verify the application account, open SQL Shell again and enter `127.0.0.1` for Server, `claimiq` for Database, `5432` for Port, `claimiq_local` for Username, and your **local role** password. Run:

```sql
SELECT current_database(), current_user;
\q
```

Expected names: `claimiq` and `claimiq_local`. Repeat with database `claimiq_test` to check your test database.

## 4. Set up Python in PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If activation is blocked, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in **this PowerShell window only**, then try activation again. This does not permanently change system policy. You should see `(.venv)` in your prompt. If `py` does not exist but `python --version` works, use `python -m venv .venv` instead.

## 5. Configure the database URLs (current PowerShell session)

Replace the example password in both strings with the `claimiq_local` password from step 3. Do not insert spaces or angle brackets. If the password contains URL-reserved characters such as `@`, `:`, `/`, `#`, or `%`, URL-encode those characters (for example, `@` becomes `%40`, `%` becomes `%25`). Do not put working credentials into the repository.

```powershell
$env:DATABASE_URL = 'postgresql+psycopg2://claimiq_local:replace-with-your-own-strong-password@127.0.0.1:5432/claimiq'
$env:TEST_DATABASE_URL = 'postgresql+psycopg2://claimiq_local:replace-with-your-own-strong-password@127.0.0.1:5432/claimiq_test'
$env:JWT_SECRET = python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

These variables last only in the current PowerShell session. **The app uses `DATABASE_URL`; tests use `TEST_DATABASE_URL`**. When starting a new PowerShell window for pytest or restarting the API, re-enter these assignments. Keep `JWT_SECRET` unchanged while you want existing tokens to remain valid.

Prove the Python app can connect before migrating:

```powershell
python -c 'from sqlalchemy import text; from app.db import engine; c=engine.connect(); print(c.execute(text("select current_database(), current_user")).one()); c.close()'
```

Expected output includes `claimiq` and `claimiq_local`. If you get `connection refused`, check Services, port and `DATABASE_URL`. If you get `password authentication failed`, check the role password, URL encoding and SQL Shell login.

## 6. Migrate and seed

```powershell
python -m alembic upgrade head
python -m alembic current
python -m app.seed
python -m app.seed
```

Expected migration: `0001 (head)`; running seed twice must not duplicate synthetic data. Demo users: `admin`, `adjuster`, `reviewer`, `customer`; each has password `demo123`. These passwords are **only for localhost development**. If PostgreSQL says `permission denied for schema public`, sign in as `postgres` to the **specific** database and run `GRANT USAGE, CREATE ON SCHEMA public TO claimiq_local;`, then retry the migration.

## 7. Start the server and open docs

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Keep this window open. In your browser visit:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json
- Health: http://127.0.0.1:8000/health

Health returns `{"status":"ok"}` but **does not check database connectivity**; use the query in step 5 to check the database. In Swagger, click **Authorize**, enter `admin` and `demo123`, press Authorize and try `GET /users/me`. Log out/re-authorize with each other role to test role permissions.

## 8. Use bearer tokens with PowerShell

Open a **second PowerShell window** for requests. Requests below do not require the venv or environment variables; the server window must still be open.

```powershell
$base = 'http://127.0.0.1:8000'
$token = (Invoke-RestMethod -Method Post -Uri "$base/auth/token" -Body @{username='admin';password='demo123'}).access_token
$auth = @{Authorization = "Bearer $token"}
Invoke-RestMethod -Uri "$base/users/me" -Headers $auth
Invoke-RestMethod -Uri "$base/policies" -Headers $auth
Invoke-RestMethod -Uri "$base/claims" -Headers $auth
Invoke-RestMethod -Uri "$base/analytics/summary" -Headers $auth
Invoke-RestMethod -Uri "$base/audit" -Headers $auth
```

Check all four demo logins without printing tokens:

```powershell
foreach ($role in @('admin','reviewer','adjuster','customer')) {
    $result = Invoke-RestMethod -Method Post -Uri "$base/auth/token" -Body @{username=$role;password='demo123'}
    Write-Host "$role : $($result.token_type) token received = $([bool]$result.access_token)"
}
```

Create a policy, then claim and process it (use the example returned IDs, not hard-coded IDs):

```powershell
$policy = Invoke-RestMethod -Method Post -Uri "$base/policies" -Headers $auth -ContentType 'application/json' -Body '{"number":"WIN-EXAMPLE-01","holder":"Synthetic Example","active":true}'
$claimBody = @{policy_id=$policy.id;description='Synthetic local example';amount=250} | ConvertTo-Json
$claim = Invoke-RestMethod -Method Post -Uri "$base/claims" -Headers $auth -ContentType 'application/json' -Body $claimBody
$adjuster = Invoke-RestMethod -Uri "$base/users" -Headers $auth | Where-Object role -EQ 'adjuster' | Select-Object -First 1
$assignBody = @{user_id=$adjuster.id} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/claims/$($claim.id)/assignment" -Headers $auth -ContentType 'application/json' -Body $assignBody
Invoke-RestMethod -Method Post -Uri "$base/claims/$($claim.id)/status" -Headers $auth -ContentType 'application/json' -Body '{"status":"under_review"}'
Invoke-RestMethod -Method Post -Uri "$base/claims/$($claim.id)/notes" -Headers $auth -ContentType 'application/json' -Body '{"text":"Synthetic review note"}'
Invoke-RestMethod -Uri "$base/claims/$($claim.id)/history" -Headers $auth
```

For document uploads, make a local sample and use **`curl.exe`** (not the PowerShell `curl` alias):

```powershell
'Synthetic water damage deductible is 500 dollars.' | Set-Content -Encoding utf8 .\sample-claimiq.txt
$uploaded = curl.exe -sS -H "Authorization: Bearer $token" -F "file=@sample-claimiq.txt" "$base/documents" | ConvertFrom-Json
$uploaded
```

Use the returned document ID:

```powershell
$documentId = $uploaded.id
Invoke-RestMethod -Method Patch -Uri "$base/documents/$documentId" -Headers $auth -ContentType 'application/json' -Body '{"active":true,"approved":true}'
Invoke-RestMethod -Method Post -Uri "$base/rag/ask" -Headers $auth -ContentType 'application/json' -Body '{"question":"water deductible"}'
Invoke-RestMethod -Method Post -Uri "$base/rag/ask" -Headers $auth -ContentType 'application/json' -Body '{"question":"intergalactic platypus"}'
```

Only active and approved documents participate in retrieval. A related question returns text with citations; unrelated queries return an explicit no-match response. In Swagger you can explore every API, including download and claim visibility for customer/adjuster roles. Do not share bearer tokens.

## 9. Run tests and quality checks

Open a PowerShell with the venv activated and set **both URLs** as in steps 4–5. **Important:** the database-backed test fixture drops/recreates all tables inside the disposable `claimiq_test`. Check that it contains no valuable data before testing. Tests refuse any URL whose database name is not exactly `claimiq_test`.

```powershell
python -m pytest -q
python -m ruff check .
python -m mypy app migrations tests
python -m compileall -q app migrations tests
python -m coverage run -m pytest -q
python -m coverage report -m
```

A skip means the PostgreSQL integration workflow **did not run**. Ensure PostgreSQL is running and that the test URL connects to `claimiq_test`; do not treat a skip as a pass.

## 10. Stop, reset and troubleshoot

Stop Uvicorn using **Ctrl+C** in the server PowerShell window. Files uploaded via the API are stored under `uploads\` in the current working directory unless `UPLOAD_DIR` is set; extracted chunks and metadata are in PostgreSQL. PostgreSQL resets do **not** delete files. RAG runs locally without any external AI/API dependency.

- Port 8000 occupied: stop the old server or use `--port 8001` and update `$base` and browser URLs.
- Alembic `revision not found`: run `python -m alembic heads`, verify the working directory and URL; do not stamp a database blindly.
- 401 JWT: log in again, use `Authorization: Bearer <token>`, and keep the same `JWT_SECRET` while the server is running.
- Write errors: verify `UPLOAD_DIR` is writable and the disk has free space.
- To reset **only disposable** `claimiq`: stop server, check database names and data carefully in SQL Shell as administrator; while connected to database `postgres`, execute `DROP DATABASE claimiq WITH (FORCE);` then `CREATE DATABASE claimiq OWNER claimiq_local;`. Do not drop `claimiq_test` or any other database; never do this against valuable data. Run step 6 again. UUID-named uploaded files remain until you safely remove them separately.
