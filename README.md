# ClaimIQ Backend — Local Setup and API Guide

ClaimIQ is a local FastAPI backend backed by PostgreSQL. It provides demo accounts, policies, claims, claim workflow endpoints, document handling, retrieval, analytics, and audit endpoints.

The application runs locally with Uvicorn. It does **not** require an external AI service, AI API key, hosted search service, or external vector database. Its document retrieval is local and lexical; it is not a generative AI service.

## How the pieces connect

```text
Browser / Swagger UI
        |
        | HTTP, usually port 8000
        v
FastAPI (Uvicorn)
        |
        | DATABASE_URL
        v
PostgreSQL, using your configured port
```

- **FastAPI port:** `8000` in the commands below.
- **PostgreSQL port:** commonly `5432`, but your installation may use another port, such as `5433`.
- **Application database:** `claimiq`.
- **Test database:** `claimiq_test`.
- **Recommended PostgreSQL application user:** `claimiq_local`.
- **PostgreSQL password:** you choose it when creating `claimiq_local`; it is **not supplied by this repository**.

The PostgreSQL credentials are different from the demo accounts used to log in to the API.

## Prerequisites

- Python 3.12 **64-bit** recommended on Windows
- A running local PostgreSQL **server** (pgAdmin and `psql` alone are not the server)
- PowerShell for the Windows commands below

Run project commands from the repository root: the folder containing `requirements.txt`, `alembic.ini`, and `app`.

Separate OS guides are also available:

- [Windows setup](SETUP_WINDOWS.md)
- [Linux setup](SETUP_LINUX.md)
- [macOS setup](SETUP_MACOS.md)

## 1. Check PostgreSQL on Windows

In PowerShell, list PostgreSQL services:

```powershell
Get-Service *postgres*
```

Check which port is listening:

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $$_.LocalPort -ge 5432 -and $$_.LocalPort -le 5440 } |
    Format-Table LocalAddress,LocalPort,OwningProcess
```

Test the port you found. For example, if PostgreSQL is on **5433**:

```powershell
Test-NetConnection 127.0.0.1 -Port 5433
```

Look for `TcpTestSucceeded : True`. Substitute your actual PostgreSQL port throughout this guide if it differs from `5433`.

> If `Get-Service *postgres*` shows nothing, or no PostgreSQL port accepts connections, install or start the PostgreSQL **server** before continuing.

## 2. Create the PostgreSQL role and databases

Connect as the PostgreSQL administrator. This example uses port **5433**:

```powershell
psql -h 127.0.0.1 -p 5433 -U postgres -d postgres
```

Enter the `postgres` administrator password set during PostgreSQL installation. At the `postgres=#` prompt, check whether the role or databases already exist:

```sql
\du
\l
```

If they do **not** already exist, create them. Choose your own password in place of `choose-your-own-password`:

```sql
CREATE ROLE claimiq_local LOGIN PASSWORD 'choose-your-own-password';
CREATE DATABASE claimiq OWNER claimiq_local;
CREATE DATABASE claimiq_test OWNER claimiq_local;
\q
```

Do not recreate or drop an existing role or database without checking what it contains.

> `claimiq` is the **database name**, not a table name. Application tables are normally created in the `public` schema of that database by Alembic.

## 3. Create a Python environment and install dependencies

From the repository root in PowerShell:

```powershell
py -3.12 -c "import platform; print(platform.architecture())"
py -3.12 -m venv .venv64
.\.venv64\Scripts\python.exe -m pip install --upgrade pip
.\.venv64\Scripts\python.exe -m pip install -r requirements.txt
```

The architecture check should report `64bit`. Verify that key dependencies installed:

```powershell
.\.venv64\Scripts\python.exe -c "import fastapi, sqlalchemy, pandas, psycopg2; print('Dependencies OK')"
```

Use `.\.venv64\Scripts\python.exe` for subsequent commands so installation and execution use the same environment. **Do not run `py .\app\main.py`**; start the API with Uvicorn.

## 4. Configure the FastAPI-to-PostgreSQL connection

The app reads its connection string from the `DATABASE_URL` environment variable. The test suite uses `TEST_DATABASE_URL`. Set these in the **same PowerShell window** in which you will run migrations and start Uvicorn.

This example prompts for the `claimiq_local` password and safely constructs a URL, including when the password contains special characters:

```powershell
$env:DATABASE_URL = & .\.venv64\Scripts\python.exe -c "from getpass import getpass; from sqlalchemy.engine import URL; print(URL.create('postgresql+psycopg2', username='claimiq_local', password=getpass('claimiq_local password: '), host='127.0.0.1', port=5433, database='claimiq').render_as_string(hide_password=False))"
```

Set a local JWT signing secret:

```powershell
$env:JWT_SECRET = & .\.venv64\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Do not commit passwords, connection URLs, JWT secrets, or `.env` files to Git.** Environment variables set this way last only for the current PowerShell session. Set them again when opening a new window. Keep the same `JWT_SECRET` for the lifetime of a server session; changing it invalidates previously issued tokens.

### Verify the actual application connection

```powershell
.\.venv64\Scripts\python.exe -c "from sqlalchemy import text; from app.db import engine; c=engine.connect(); print(c.execute(text('select current_database(), current_user')).one()); c.close()"
```

Expected output:

```text
('claimiq', 'claimiq_local')
```

This check confirms that the **project's SQLAlchemy configuration** reaches the intended database. A successful port test alone does not prove that.

## 5. Create tables and seed demo data

Run the migration **before** the seed script:

```powershell
.\.venv64\Scripts\python.exe -m alembic upgrade head
.\.venv64\Scripts\python.exe -m alembic current
.\.venv64\Scripts\python.exe -c "from sqlalchemy import inspect; from app.db import engine; print(inspect(engine).get_table_names())"
.\.venv64\Scripts\python.exe -m app.seed
```

The table list should include `users`. If seeding reports `relation "users" does not exist`, stop: the migration has not successfully created the schema in the database the seed script is using.

The seed is designed to be safe to rerun for its demo data:

```powershell
.\.venv64\Scripts\python.exe -m app.seed
```

## 6. Start FastAPI

In the **same PowerShell window** where `DATABASE_URL` and `JWT_SECRET` are set:

```powershell
.\.venv64\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Leave this terminal open. Uvicorn should report an address like:

```text
http://127.0.0.1:8000
```

Open:

| URL | Purpose |
|---|---|
| http://127.0.0.1:8000/docs | Swagger UI |
| http://127.0.0.1:8000/redoc | ReDoc |
| http://127.0.0.1:8000/openapi.json | OpenAPI specification |
| http://127.0.0.1:8000/health | Basic API health response |

**Important:** `/health` does not establish that PostgreSQL works. Use the connection check above or a database-backed endpoint such as login.

Press **Ctrl+C** in the Uvicorn terminal to stop the server.

## 7. Verify login and database access in Swagger

The seed creates these **demo API users**:

| Username | Password | Role |
|---|---|---|
| `admin` | `demo123` | Admin |
| `reviewer` | `demo123` | Reviewer |
| `adjuster` | `demo123` | Adjuster |
| `customer` | `demo123` | Customer |

These are **API credentials**, not PostgreSQL credentials. Use them for local development only.

1. Open http://127.0.0.1:8000/docs.
2. Click **Authorize**.
3. Enter username `admin` and password `demo123`, then authorize.
4. Swagger should display **Authorized**. This means it received an API bearer token.
5. Close the authorization dialog.
6. Expand **`GET /users/me`**, click **Try it out**, then **Execute**.
7. Check for a successful response containing `username: "admin"` and `role: "admin"`.
8. Try **`GET /policies`** and **`GET /claims`** to inspect database-backed data.
9. Repeat authorization with another demo role to explore role-based permissions.

You can also call **`POST /auth/token`** directly with a demo username and password. Keep returned access tokens private.

### Optional command-line API check

Open another PowerShell window while Uvicorn continues to run:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health

$login = Invoke-RestMethod -Method Post `
    -Uri 'http://127.0.0.1:8000/auth/token' `
    -ContentType 'application/x-www-form-urlencoded' `
    -Body @{ username = 'admin'; password = 'demo123' }

$$headers = @{ Authorization = "Bearer $$($login.access_token)" }

Invoke-RestMethod -Uri 'http://127.0.0.1:8000/users/me' -Headers $headers
```

This second window only calls the HTTP API; it does **not** need `DATABASE_URL`. The window running Uvicorn **does** need `DATABASE_URL`.

## 8. Run checks and tests

For database-backed tests, configure a separate `claimiq_test` database. **Never point tests at `claimiq`**. In the PowerShell window running the tests, set `TEST_DATABASE_URL` using the `claimiq_local` password:

```powershell
$env:TEST_DATABASE_URL = & .\.venv64\Scripts\python.exe -c "from getpass import getpass; from sqlalchemy.engine import URL; print(URL.create('postgresql+psycopg2', username='claimiq_local', password=getpass('claimiq_local password: '), host='127.0.0.1', port=5433, database='claimiq_test').render_as_string(hide_password=False))"
```

Then run:

```powershell
.\.venv64\Scripts\python.exe -m pytest -q
.\.venv64\Scripts\python.exe -m ruff check .
.\.venv64\Scripts\python.exe -m mypy app migrations tests
.\.venv64\Scripts\python.exe -m compileall -q app migrations tests
```

Read the pytest summary carefully: a **skipped** PostgreSQL integration test is **not a passed integration test**. The test database is disposable; do not store important data in `claimiq_test`.

## Troubleshooting

### `connection refused` on PostgreSQL port 5432

Your PostgreSQL server may be on **5433**. Check its listening port and set `DATABASE_URL` accordingly. The project's fallback URL uses port 5432 if `DATABASE_URL` is absent.

### `KeyError: 'DATABASE_URL'`

The variable is not set in the current PowerShell window. Set it again **before** running Alembic, the seed script, or Uvicorn.

### Login in Swagger returns HTTP 500 and the server log mentions port 5432

Stop Uvicorn. Set `DATABASE_URL` to the correct port in the window that will start Uvicorn, verify the Python database connection, then restart Uvicorn. Changing a variable in a different window does not update the running process.

### `relation "users" does not exist`

The application can connect, but its tables have not been created in that database. Run `alembic upgrade head` successfully before `python -m app.seed`. Check `alembic current` and the table list; do not use `alembic stamp` to hide a missing schema.

### `ModuleNotFoundError`

Install `requirements.txt` using the **same virtual-environment Python executable** that you use to start the app. For example:

```powershell
.\.venv64\Scripts\python.exe -m pip install -r requirements.txt
```

### Port 8000 is occupied

Stop the existing Uvicorn process or use another API port:

```powershell
.\.venv64\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Then open `http://127.0.0.1:8001/docs`. This does not change the PostgreSQL port.

### pgAdmin connects but the app does not

pgAdmin and FastAPI can use different connection settings. Verify **the app's** connection with the SQLAlchemy check in step 4. Make sure both use the intended database, user, and PostgreSQL port.

## Repository reference

- `app/main.py` — FastAPI application and API endpoints
- `app/config.py` — environment-based database and application configuration
- `app/db.py` — SQLAlchemy engine and sessions
- `app/models.py` — database models
- `app/security.py` — password and bearer-token handling
- `app/seed.py` — synthetic demo data
- `migrations/` — Alembic schema migration
- `tests/` — automated tests
- `IMPLEMENTATION_CHECKLIST.md` — requirement-to-code mapping
- `VALIDATION.md` — checks performed and their limitations

See the OS-specific setup guides for further installation and troubleshooting instructions.
