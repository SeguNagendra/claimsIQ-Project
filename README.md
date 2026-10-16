# ClaimIQ — Claims Management and Analytics (Local API)

This phase contains **only** the Claims Management module and analytics. Document Management and RAG are separate future modules and are intentionally not included.

The FastAPI backend runs directly on your local machine. PostgreSQL is expected to be the PostgreSQL container you already started with Docker. This project does not build or run a backend/frontend Docker image and has no Docker Compose file.

## Included modules

- Authentication using JWT bearer tokens
- Role-based access control: `admin`, `reviewer`, `adjuster`, `customer`
- User listing for authorized roles
- Policy creation and listing
- Claim submission and retrieval
- Adjuster assignment
- Claim status workflow and append-only status history
- Claim notes
- Pandas-based analytics summary
- Audit log for key actions
- Automated unit/API tests using an isolated in-memory SQLite database

## Folder structure

```text
claimiq-claims-local/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── init_db.py
│   ├── models.py
│   ├── schemas.py
│   ├── security.py
│   ├── seed.py
│   └── main.py
├── tests/
│   ├── conftest.py
│   └── test_api.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 1. Check your existing PostgreSQL container

In PowerShell or a terminal:

```bash
docker ps
```

Find the PostgreSQL container and check its `PORTS` value. If it shows `127.0.0.1:5433->5432/tcp`, connect to host port `5433`. If it shows `0.0.0.0:5432->5432/tcp`, use host port `5432`.

Your container must publish a port to the host for the locally running Python process to connect to it.

## 2. Create the application database

If you have already created a `claimiq` database, keep using it; do not drop it. Otherwise, connect to the PostgreSQL container and create the database.

Example command (replace container name, host port and credentials with yours):

```bash
docker exec -it <your-postgres-container-name> psql -U postgres -d postgres
```

At the `psql` prompt, create the database only if it does not already exist:

```sql
CREATE DATABASE claimiq;
```

If you prefer to use a dedicated database user, create that role and make it the database owner. Use your own password:

```sql
CREATE ROLE claimiq_local LOGIN PASSWORD 'choose-a-local-password';
ALTER DATABASE claimiq OWNER TO claimiq_local;
```

If the role already exists, do not recreate it. Exit `psql` with `\q`.

## 3. Create `.env`

Copy `.env.example` to `.env` in the project root. Update `DATABASE_URL` with your actual database username, password, and published host port.

Example if PostgreSQL is published on port 5433:

```env
DATABASE_URL=postgresql+psycopg2://claimiq_local:choose-a-local-password@127.0.0.1:5433/claimiq
JWT_SECRET=use-a-long-random-local-secret
ACCESS_TOKEN_MINUTES=120
```

URL-encode special characters in the database password (for example, `@` as `%40`) or choose a local password without URL-reserved characters for this development setup.

## 4. Create a Python virtual environment and install dependencies

Run these commands from the `claimiq-claims-local` project root.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, run this in that terminal and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

If `.env` already exists, do not overwrite it; edit its `DATABASE_URL` instead.

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
cp .env.example .env
```

Edit `.env`, then install packages:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Create tables and demo data

From the project root with the virtual environment active:

```bash
python -m app.init_db
```

This creates missing tables and inserts demo accounts and a demo policy/claim only when they do not already exist. It does not drop or reset the database.

Demo users all have password `demo123`:

| Username | Role |
|---|---|
| `admin` | admin |
| `reviewer` | reviewer |
| `adjuster` | adjuster |
| `customer` | customer |
| `customer2` through `customer50` | customer |
| `adjuster1` through `adjuster5` | adjuster |
| `support_agent` | support_agent |

Demo users all have password `demo123`. The seed creates policies `POL-0001` through `POL-0050`; each sample policy is assigned to its matching customer account (`POL-0001` belongs to `customer`, `POL-0002` belongs to `customer2`, and so on). New claims are automatically assigned to the active adjuster with the fewest open claims. Demo data and passwords are for local development only.

**Policy ownership:** `POST /policies` is admin-only and requires `number`, `holder`, `owner_id`, and optional `active`. The `owner_id` must identify an active customer. Customers can submit claims only against their own policies. When upgrading an existing local database, `python -m app.init_db` adds the policy-owner column if needed and backfills the known sample policies. Other legacy policies are deliberately left unowned rather than guessing; assign their `owner_id` to the correct customer before accepting claims against them.

## 6. Start the API locally

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open Swagger UI:

- http://127.0.0.1:8000/docs
- Health endpoint: http://127.0.0.1:8000/health

In Swagger, click **Authorize** and log in using the `/auth/token` endpoint. The OAuth2 form expects `username` and `password`. After a successful login, Swagger uses the returned bearer token for protected endpoints.

## 7. Suggested Swagger testing sequence

1. `POST /auth/token` — sign in as `admin` or `customer`.
2. `GET /users/me` — verify the logged-in user and role.
3. `GET /policies` — list policies.
4. `GET /users` as admin — find the intended customer's numeric `id`.
5. `POST /policies` as admin — create a policy with `number`, `holder`, and that customer's `owner_id`.
6. `POST /claims` as the policy's customer — create a claim using the policy's numeric `id`. A different customer should receive `403`.
7. `GET /claims` — verify role-based filtering.
8. `POST /claims/{claim_id}/assignment` as admin/reviewer — assign to the adjuster user ID if reassignment is needed.
9. `POST /claims/{claim_id}/status` as adjuster — move the claim to `under_review`.
10. `POST /claims/{claim_id}/status` as reviewer/admin — move it to `approved` or `denied`.
11. `GET /claims/{claim_id}/history` — verify status history.
12. `POST /claims/{claim_id}/notes` and `GET /claims/{claim_id}/notes`.
13. `GET /analytics/summary` as admin/reviewer.
14. `GET /audit` as admin.

Valid workflow:

```text
submitted -> under_review -> approved -> closed
                           -> denied ----> closed
```

An admin may override a transition only by providing a non-empty `justification`. Adjusters cannot make approval/denial decisions.

## 8. Run tests

Tests use an isolated in-memory SQLite database and do **not** connect to, delete, or modify your PostgreSQL database.

```bash
python -m pytest -v
```

## Troubleshooting

- `connection refused`: check `docker ps`, the container's published port, and the `DATABASE_URL` host port.
- `password authentication failed`: correct the database credentials in `.env`.
- `database "claimiq" does not exist`: create the database inside the running PostgreSQL server first.
- `ModuleNotFoundError`: activate `.venv` and run `pip install -r requirements.txt`.
- `Address already in use`: use another API port, e.g. `--port 8001`, and open the matching URL.

This is a local development starter, not production deployment configuration. Do not expose it publicly or use demo credentials for real data.
