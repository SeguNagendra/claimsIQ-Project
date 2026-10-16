# ClaimIQ — Swagger UI Testing Guide (PostgreSQL in Docker)

This guide walks through testing the ClaimIQ API in Swagger UI in a practical order: start PostgreSQL, start FastAPI, log in, create a policy, log in as a customer, create a claim, process the claim, and inspect the saved data in PostgreSQL.

> Run all commands from the ClaimIQ repository root — the directory containing `requirements.txt`, `alembic.ini`, and the `app` folder. These are local development/demo steps; do not use the demo accounts or sample data in production.

## 1. Start PostgreSQL from Docker Hub

Make sure Docker Desktop is running. This guide uses the official PostgreSQL image with Alpine Linux and maps host port **5433** to container port **5432**. Port 5433 helps avoid conflicts with a PostgreSQL instance already running on your computer.

### 1.1 Pull the image

Open PowerShell or a terminal and run:

```powershell
docker pull postgres:17-alpine
```

### 1.2 Create and start the PostgreSQL container

The following creates a database named `claimiq`, an application user named `claimiq_local`, and persistent storage for the database files. Replace the example password with a local development password of your choice.

```powershell
docker volume create claimiq_pgdata

docker run --name claimiq-postgres `
  --detach `
  --restart unless-stopped `
  --publish 5433:5432 `
  --env POSTGRES_DB=claimiq `
  --env POSTGRES_USER=claimiq_local `
  --env POSTGRES_PASSWORD=ClaimIQ_Local_ChangeMe_123 `
  --volume claimiq_pgdata:/var/lib/postgresql/data `
  postgres:17-alpine
```

The password above is only an example. Use the same password in the application connection string below. Do not commit passwords to Git.

### 1.3 Confirm that PostgreSQL is running

```powershell
docker ps
docker logs claimiq-postgres
docker exec -it claimiq-postgres pg_isready -U claimiq_local -d claimiq
```

The last command should report that PostgreSQL is accepting connections.

If you already created a container named `claimiq-postgres`, do not run `docker run` again. Start the existing container instead:

```powershell
docker start claimiq-postgres
```

## 2. Configure the FastAPI application to use the Docker database

Open a **new PowerShell terminal** in the ClaimIQ repository root. The application runs on your computer, so its database host is `127.0.0.1` and its mapped port is `5433` — not the Docker container's internal port `5432`.

Set the database URL and a local JWT signing secret in that same terminal:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg2://claimiq_local:ClaimIQ_Local_ChangeMe_123@127.0.0.1:5433/claimiq'
$env:JWT_SECRET = 'replace-this-with-a-long-random-local-secret'
```

If you changed the password in Step 1.2, update it here too. If your password contains characters such as `@`, `:`, `/`, or `#`, URL-encode those characters or use the project's existing connection-URL configuration method.

Check that Python can connect to the intended database:

```powershell
python -c "from sqlalchemy import text; from app.db import engine; c=engine.connect(); print(c.execute(text('select current_database(), current_user')).one()); c.close()"
```

Expected result should identify database `claimiq` and user `claimiq_local`. If this command fails, fix the database connection before continuing.

> Use the Python executable from your project's virtual environment if you created one. For example, on Windows you may use `\.venv64\Scripts\python.exe` instead of `python` in the commands below.

## 3. Create the database tables and demo users

Run database migrations first, then seed the demo accounts:

```powershell
python -m alembic upgrade head
python -m alembic current
python -m app.seed
```

To list the tables created by the migration:

```powershell
python -c "from sqlalchemy import inspect; from app.db import engine; print('\n'.join(inspect(engine).get_table_names()))"
```

If the migration fails, do not continue to the Swagger tests until it succeeds. If the project version uses a different database module path, follow the import path in the existing project README; the main requirement is that Alembic and FastAPI use the same `DATABASE_URL`.

## 4. Start the API

In the same PowerShell terminal where you set `DATABASE_URL` and `JWT_SECRET`, run:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Leave this terminal open. Open Swagger UI in your browser:

**http://127.0.0.1:8000/docs**

Other useful URLs:

- `http://127.0.0.1:8000/health` — API health response. This alone does not confirm database connectivity.
- `http://127.0.0.1:8000/openapi.json` — generated API schema.

## 5. Demo accounts

The seed script creates these local demo accounts. All use password `demo123`.

| Username | Password | Role | Main use in this walkthrough |
|---|---|---|---|
| `admin` | `demo123` | Admin | Create a policy; inspect users; optional reassignment |
| `customer` | `demo123` | Customer | Submit a new claim and view their own claim |
| `reviewer` | `demo123` | Reviewer | Review and decide a claim; view analytics |
| `adjuster` | `demo123` | Adjuster | View assigned claims, update permitted workflow status, add notes |

The demo users may have generated IDs that differ between databases. Always use IDs returned by the API instead of assuming an ID such as `1`.

## 6. Swagger UI: test the APIs in order

### How to execute an endpoint

For each endpoint below:

1. Expand the endpoint row in Swagger.
2. Click **Try it out**.
3. Enter the request body if the endpoint has one.
4. Click **Execute**.
5. Check the **Response code** and **Response body**.

For protected endpoints, use the **Authorize** button to sign in. The API's login endpoint uses form fields, not a JSON request body.

### Step 1 — Check API health

- Endpoint: `GET /health`
- Click **Try it out** → **Execute**.
- Expected: HTTP `200` with a response similar to `{"status":"ok"}`.

This only checks that the API process is running.

### Step 2 — Log in as admin

Use Swagger's **Authorize** button and enter:

- Username: `admin`
- Password: `demo123`

Click **Authorize**, then close the dialog. Test `GET /users/me`.

Expected: HTTP `200` and a response showing the current user as `admin` with role `admin`.

You can also test `POST /auth/token` directly. Its request uses form fields:

- `username`: `admin`
- `password`: `demo123`

Expected response includes `access_token` and `token_type: "bearer"`. Do not share the token.

### Step 3 — List users and find an adjuster ID

- Endpoint: `GET /users`
- Stay authorized as `admin`.
- Click **Try it out** → **Execute**.

Expected: a list of users, including the `adjuster` account. Note the adjuster's `id` if you want to test manual assignment later. This endpoint is intended for admin/reviewer access.

### Step 4 — List existing policies

- Endpoint: `GET /policies`
- Stay authorized as `admin`.
- Click **Try it out** → **Execute**.

Review the returned policies. If the policy you want to use already exists and is active, you can use its `id` for the claim test. Otherwise, create a new policy in Step 5.

### Step 5 — Create a policy (admin)

- Endpoint: `POST /policies`
- Stay authorized as `admin`.
- Click **Try it out** and use this sample JSON:

```json
{
  "number": "POL-SWAGGER-1001",
  "holder": "Sample Customer",
  "active": true
}
```

Click **Execute**. Expected: successful creation and a response containing the new policy `id`.

**Record the returned policy ID.** Use that exact number in Step 7. If you execute the request again with the same policy number, the API may return HTTP `409` because policy numbers must be unique. If your Swagger schema shows a different request model, follow the schema displayed by your running application.

### Step 6 — Log in as the customer

Click **Authorize** again and switch the credentials to:

- Username: `customer`
- Password: `demo123`

Authorize and close the dialog. Run `GET /users/me` and confirm that the current user is `customer`.

You must switch roles for this step because a customer should submit a claim as themselves, rather than as an administrator.

### Step 7 — Create a claim (customer)

- Endpoint: `POST /claims`
- Stay authorized as `customer`.
- Click **Try it out** and enter the policy ID returned in Step 5:

```json
{
  "policy_id": 1,
  "description": "Water damage in the kitchen",
  "amount": 2500
}
```

Replace `1` with the actual policy ID. Click **Execute**.

Expected: HTTP `201` or another successful response, with fields such as `id`, `policy_id`, `owner_id`, `assigned_to`, `description`, `amount`, and `status`. Record the returned claim `id` for the next steps. The initial status should be `submitted`.

Important rules:

- The policy must exist and be active; otherwise, the API rejects the claim.
- The current implementation automatically assigns a claim to an active adjuster with the lowest open-claim count. The returned `assigned_to` field identifies that adjuster.
- If there is no active adjuster, claim creation may fail with a service-unavailable response.

### Step 8 — View the customer's claims

- Endpoint: `GET /claims`
- Stay authorized as `customer`.
- Click **Try it out** → **Execute**.

Expected: a list containing the claim you just created. Customer access is restricted to that customer's own claims.

### Step 9 — Get the claim by ID

- Endpoint: `GET /claims/{claim_id}`
- Enter the claim ID returned in Step 7.
- Click **Execute**.

Expected: HTTP `200` with that claim's details.

### Step 10 — Optional: assign or reassign the claim (admin/reviewer)

Claim creation already assigns an active adjuster automatically. This step is optional and is useful to test the assignment endpoint.

1. Click **Authorize** and sign in as `admin` (or `reviewer`): password `demo123`.
2. Run `GET /users` and note the ID of an active user whose role is `adjuster`.
3. Open `POST /claims/{claim_id}/assignment` and enter the claim ID from Step 7.
4. Use this JSON, replacing `2` with the real adjuster ID:

```json
{
  "user_id": 2
}
```

5. Execute and confirm that `assigned_to` matches the adjuster ID.

Only an active user with the `adjuster` role is valid for this endpoint.

### Step 11 — Move the claim to under review

- Endpoint: `POST /claims/{claim_id}/status`
- Authorize as the assigned `adjuster`, or as `reviewer`/`admin`.
- Enter the claim ID from Step 7.
- Request JSON:

```json
{
  "status": "under_review"
}
```

Click **Execute**. Expected: a successful response with status `under_review`.

If using the adjuster role, make sure that adjuster is assigned to the claim. The API enforces role-based access and valid status transitions.

### Step 12 — Review the claim history

- Endpoint: `GET /claims/{claim_id}/history`
- Enter the same claim ID.
- Click **Execute**.

Expected: an ordered list of status-history entries. It should include the initial `submitted` status and the change to `under_review`.

### Step 13 — Add a claim note

- Endpoint: `POST /claims/{claim_id}/notes`
- Authorize as `admin`, `reviewer`, or the assigned `adjuster`.
- Enter the claim ID and this JSON:

```json
{
  "text": "Reviewed the submitted claim details."
}
```

Click **Execute**. Expected: a successful response containing the new note ID and text.

### Step 14 — List claim notes

- Endpoint: `GET /claims/{claim_id}/notes`
- Use the same claim ID.
- Click **Execute**.

Expected: the note created in Step 13 appears in the response.

### Step 15 — Approve or deny the claim (reviewer/admin)

The workflow allows a decision from `under_review` to `approved` or `denied`. Use **one** of the following statuses for this test.

- Endpoint: `POST /claims/{claim_id}/status`
- Authorize as `reviewer` or `admin` (an adjuster cannot make the final decision).
- Example JSON to approve:

```json
{
  "status": "approved"
}
```

Click **Execute** and confirm the status is `approved`.

### Step 16 — Close the claim

- Endpoint: `POST /claims/{claim_id}/status`
- Stay authorized as `reviewer` or `admin`.
- Request JSON:

```json
{
  "status": "closed"
}
```

Click **Execute**. Expected: status becomes `closed`.

If you chose `denied` in Step 15 instead, you can still move from `denied` to `closed`.

### Step 17 — Check analytics

- Endpoint: `GET /analytics/summary`
- Authorize as `admin` or `reviewer`.
- Click **Try it out** → **Execute**.

Expected: a summary of claim counts/statuses, amounts, turnaround/SLA information, and adjuster workload, depending on the fields returned by your current code. The new claim should be reflected in the results.

### Step 18 — Check audit events

- Endpoint: `GET /audit`
- Authorize as `admin`.
- Click **Try it out** → **Execute**.

Expected: audit entries for supported actions such as policy creation, claim creation, assignment, status changes, and notes. Audit records are intended for action/resource/actor metadata, not passwords or bearer tokens.

## 7. Endpoint checklist

Use this as a final checklist. Swagger is the source of truth for the endpoints enabled in your current checkout.

| Order | Method | Endpoint | What to verify |
|---:|---|---|---|
| 1 | `GET` | `/health` | API process responds |
| 2 | `POST` | `/auth/token` | Demo credentials issue a token |
| 3 | `GET` | `/users/me` | Current role is correct |
| 4 | `GET` | `/users` | Admin/reviewer can see users |
| 5 | `GET` | `/policies` | Policies are listed |
| 6 | `POST` | `/policies` | Admin can create a policy |
| 7 | `POST` | `/claims` | Customer can submit a claim against an active policy |
| 8 | `GET` | `/claims` | Customer sees their own claims |
| 9 | `GET` | `/claims/{claim_id}` | Claim details are returned |
| 10 | `POST` | `/claims/{claim_id}/assignment` | Admin/reviewer can assign an active adjuster |
| 11 | `POST` | `/claims/{claim_id}/status` | Claim follows allowed workflow |
| 12 | `GET` | `/claims/{claim_id}/history` | Status history is persisted |
| 13 | `POST` | `/claims/{claim_id}/notes` | Note is saved |
| 14 | `GET` | `/claims/{claim_id}/notes` | Saved notes are returned |
| 15 | `GET` | `/analytics/summary` | Admin/reviewer can see analytics |
| 16 | `GET` | `/audit` | Admin can inspect audit events |

## 8. Inspect PostgreSQL tables and data

You can inspect the database directly from the PostgreSQL container. Open a **new** terminal and run:

```powershell
docker exec -it claimiq-postgres psql -U claimiq_local -d claimiq
```

You should now see a PostgreSQL prompt similar to `claimiq=#`.

### 8.1 List databases, tables, and table structure

Run these commands inside `psql`:

```sql
\conninfo
\l
\dt
\d users
\d policies
\d claims
\d status_history
\d notes
\d audit_logs
```

If a table name differs in your version, use `\dt` to get the exact names created by the migration, then use `\d actual_table_name`.

### 8.2 View data from each main table

```sql
SELECT id, username, role, active FROM users ORDER BY id;

SELECT id, number, holder, active FROM policies ORDER BY id;

SELECT id, policy_id, owner_id, assigned_to, description, amount, status
FROM claims
ORDER BY id;

SELECT id, claim_id, actor_id, old_status, new_status, justification, created_at
FROM status_history
ORDER BY id;

SELECT id, claim_id, author_id, text, created_at
FROM notes
ORDER BY id;

SELECT id, actor_id, action, resource, created_at
FROM audit_logs
ORDER BY id DESC;
```

These are read-only `SELECT` statements. If your migration uses different column names, inspect the table with `\d table_name` and adjust the query to match.

### 8.3 See the claim together with its policy and customer

```sql
SELECT
    c.id AS claim_id,
    p.number AS policy_number,
    p.holder AS policy_holder,
    c.owner_id AS customer_user_id,
    u.username AS customer_username,
    c.assigned_to AS adjuster_user_id,
    c.description,
    c.amount,
    c.status,
    c.created_at
FROM claims AS c
JOIN policies AS p ON p.id = c.policy_id
JOIN users AS u ON u.id = c.owner_id
ORDER BY c.id DESC;
```

### 8.4 Count records in the main tables

```sql
SELECT 'users' AS table_name, COUNT(*) FROM users
UNION ALL SELECT 'policies', COUNT(*) FROM policies
UNION ALL SELECT 'claims', COUNT(*) FROM claims
UNION ALL SELECT 'status_history', COUNT(*) FROM status_history
UNION ALL SELECT 'notes', COUNT(*) FROM notes
UNION ALL SELECT 'audit_logs', COUNT(*) FROM audit_logs;
```

To leave `psql`, run:

```sql
\q
```

### 8.5 Run a SQL query without opening the interactive prompt

For example:

```powershell
docker exec -it claimiq-postgres psql -U claimiq_local -d claimiq -c "SELECT id, number, holder, active FROM policies ORDER BY id;"
```

## 9. Common problems

### `connection refused` from the application

- Check `docker ps` and `docker logs claimiq-postgres`.
- Check PostgreSQL readiness with `docker exec -it claimiq-postgres pg_isready -U claimiq_local -d claimiq`.
- Confirm the application URL uses host port `5433` and the correct password.
- If you mapped a different host port, use that port in `DATABASE_URL`.

### `relation "users" does not exist`

The app connected to a database, but the migrations did not create the tables there. Confirm `DATABASE_URL` points to `claimiq`, then run:

```powershell
python -m alembic upgrade head
python -m alembic current
```

### Swagger returns `401 Unauthorized`

Click **Authorize** and log in again. Make sure you used the API demo account, not the PostgreSQL username/password. For role-restricted endpoints, switch to a role with permission.

### Creating a claim returns `422`

Check that `policy_id` is the ID of an existing **active** policy. Also check that `description` is not empty and `amount` is a non-negative number, following the request schema in Swagger.

### Claim creation returns `503`

The application could not find an active adjuster. Check `GET /users` as admin/reviewer and confirm the seed created an active adjuster account.

### A status update returns `409` or `403`

Use the allowed order: `submitted` → `under_review` → `approved` or `denied` → `closed`. A reviewer/admin should make the approve/deny decision. Admin-only overrides require a non-empty `justification`.

### Docker says the container name already exists

Start and reuse the existing container instead of creating a second one:

```powershell
docker start claimiq-postgres
```

## 10. Stop the application and database

Stop FastAPI by pressing **Ctrl+C** in the Uvicorn terminal. To stop PostgreSQL but keep its data:

```powershell
docker stop claimiq-postgres
```

To start it again later:

```powershell
docker start claimiq-postgres
```

The named Docker volume `claimiq_pgdata` retains PostgreSQL data when the container is stopped or removed. Do not remove the volume unless you intentionally want to delete the local database data.

---

**Reminder:** Use the Swagger request/response schema from your running application if it differs from an example in this guide. IDs are generated by the database, so always copy the actual returned IDs into subsequent requests.
