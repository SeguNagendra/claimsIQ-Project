# CloudGuard — From Fresh Setup to End-to-End Swagger Testing

This guide is for **Windows + PowerShell**. It follows the current repository code: FastAPI runs on your computer, PostgreSQL runs in Docker, and live Azure authentication uses `az login` / `AzureCliCredential` (not UAMI).

> **Safety:** First test against a development/test subscription and non-production resources. The VM policy writes tags automatically. The NSG approval endpoint changes an Azure security rule. Do not approve a live NSG change until the replacement CIDR is confirmed by your network/security team.

## What you will have at the end

- PostgreSQL running in Docker on host port `5433`.
- Python virtual environment and dependencies installed.
- CloudGuard tables and seed data created automatically at application startup.
- FastAPI running at `http://127.0.0.1:8000`.
- Login tested, subscription registered, policies listed, scan run, findings checked, low-risk tag verified, and high-risk approval workflow tested.

## 0. Prerequisites

Install/verify:

- Python 3.11 or newer (Python 3.12 is fine).
- Docker Desktop and Docker Compose.
- Azure CLI.
- Access to the repository and a test Azure subscription.

Open PowerShell in the extracted repository root (the folder containing `app`, `requirements.txt`, and `docker-compose.yml`).

```powershell
Get-Location
Get-ChildItem
```

## 1. Create `.env`

If you are setting up a fresh copy:

```powershell
Copy-Item .env.example .env
notepad .env
```

Edit the settings to match your local environment. **The included `docker-compose.yml` publishes PostgreSQL host port `5433` to container port `5432`**, so when the FastAPI app runs on Windows, `DATABASE_URL` should use port `5433`.

Example shape (replace values locally; do not commit secrets):

```dotenv
APP_NAME=CloudGuard
APP_ENV=development
API_PREFIX=/api/v1
DATABASE_URL=postgresql+psycopg://cloudguard:<DB_PASSWORD>@127.0.0.1:5433/cloudguard
JWT_SECRET_KEY=<LONG_RANDOM_LOCAL_SECRET>
JWT_EXPIRE_MINUTES=60
AZURE_SUBSCRIPTION_ID=<YOUR_TEST_SUBSCRIPTION_GUID>
CLOUDGUARD_AZURE_MOCK=false
SEED_ADMIN_USERNAME=admin
SEED_ADMIN_PASSWORD=<YOUR_ADMIN_PASSWORD>
SEED_ENGINEER_USERNAME=engineer
SEED_ENGINEER_PASSWORD=<YOUR_ENGINEER_PASSWORD>
SEED_SECURITY_USERNAME=security
SEED_SECURITY_PASSWORD=<YOUR_SECURITY_OFFICER_PASSWORD>
```

Use the same database password as the `POSTGRES_PASSWORD` configured in `docker-compose.yml` **when initializing a new Docker volume**. In the current supplied Compose file, the default is `image123`; change it if desired, but match `.env`. If an old persistent volume already exists, changing `POSTGRES_PASSWORD` in Compose does not reset the password stored inside PostgreSQL. Do not delete a volume containing data you need.

The current `azure_service.py` uses `AzureCliCredential`; `AZURE_CLIENT_ID` is not required for this authentication mode.

### URL-encoding note

If the database password contains URL-special characters such as `@`, `:`, `/`, or `#`, URL-encode those characters in `DATABASE_URL`, or use a password without those characters for local development.

## 2. Start PostgreSQL in Docker

```powershell
docker --version
docker compose version
docker compose up -d postgres
docker compose ps
docker compose logs --tail 50 postgres
```

Docker Compose pulls `postgres:16-alpine` if it is not present. Confirm the service is running/healthy and that port mapping shows `5433` on the host and `5432` inside the container.

Optional readiness check:

```powershell
docker exec -it cloudguard-postgres pg_isready -U cloudguard -d cloudguard
```

Expected response resembles `accepting connections`.

## 3. Verify PostgreSQL database and tables

Connect from PowerShell:

```powershell
docker exec -it cloudguard-postgres psql -U cloudguard -d cloudguard
```

At the `cloudguard=#` prompt:

```sql
\conninfo
\dt
SELECT id, username, role, is_active FROM users ORDER BY id;
SELECT id, code, name, severity, enabled FROM policy_rules ORDER BY id;
\q
```

The tables are normally created automatically when the API starts for the first time. If this is a truly fresh database, `\dt` may show no tables until you start the API in Step 6.

## 4. Create and activate Python virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `py -3.12` is not available, use the installed Python launcher version, for example `py -3.11`. If PowerShell blocks activation, run this only for the current terminal session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 5. Authenticate to Azure using Azure CLI

In the same user account that will run Uvicorn:

```powershell
az login
az account list --output table
az account set --subscription "<YOUR_TEST_SUBSCRIPTION_GUID>"
az account show --output table
```

Confirm the correct subscription is active. The identity returned by `az account show` must have read permissions for the resources to scan and appropriate narrowly scoped write permissions for remediation. `az login` does **not** log you into CloudGuard; CloudGuard login happens in Step 7.

## 6. Start the API and let it initialize the database

Keep PostgreSQL running. In the repository root with `.venv` activated:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On first startup, CloudGuard attempts to:
1. connect to PostgreSQL and create the configured database if it is missing;
2. create missing tables;
3. seed initial users and the two policy definitions if they do not already exist.

The DB account must have enough privilege to create the database if it is missing. The Compose setup normally creates the `cloudguard` database before the app starts.

Open a browser to:

- Swagger: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/api/v1/health>

Keep this terminal running. Use a second PowerShell window for Docker, SQL, or Azure CLI commands.

### If startup fails with a PostgreSQL port/password error

- Confirm `.env` `DATABASE_URL` points to `127.0.0.1:5433` for the provided Compose port mapping.
- Confirm database username/password match the initialized PostgreSQL user.
- Check `docker compose ps` and `docker compose logs postgres`.
- A change to `POSTGRES_PASSWORD` does not rotate a password in an already initialized volume.
- Do not delete the volume unless you intentionally want to discard its data.

## 7. Log in to CloudGuard in Swagger

1. Expand `POST /api/v1/auth/login` under **Authentication**.
2. Click **Try it out**.
3. Submit the username and password configured by `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD` (or the current existing user's password).
4. Click **Execute**.
5. Confirm `200` and copy the `access_token` from the response privately.
6. Click **Authorize** at the top of Swagger. Enter the token in the form Swagger requests. If it expects a bearer value, enter `Bearer <access_token>`.
7. Click **Authorize** and close the dialog.

Default fallback values in `app/core/config.py` are `admin` / `ChangeMe_Admin_123!`, `engineer` / `ChangeMe_Engineer_123!`, and `security` / `ChangeMe_Security_123!`; `.env` values override these. These only work if the user was created with those values. Existing users are not reset when the seed settings change.

## 8. Register the Azure subscription

CloudGuard scans only subscriptions registered in its database.

1. In Swagger, find `POST /api/v1/subscriptions`.
2. As `ADMIN`, click **Try it out** and submit:

```json
{
  "name": "My Test Subscription",
  "subscription_id": "<YOUR_TEST_SUBSCRIPTION_GUID>"
}
```

3. Click **Execute** and expect `201 Created`.
4. Run `GET /api/v1/subscriptions` and confirm the subscription is listed and active.

If the subscription already exists, the API returns `409 Subscription already registered`; do not register it again.

## 9. Verify the two seeded policies

Run `GET /api/v1/policies`. You should see these policy codes:

- `VM_REQUIRED_ENVIRONMENT_TAG` — LOW — missing VM `Environment` tag is auto-remediated to `dev`.
- `NSG_INBOUND_ANY_IPV4` — HIGH — inbound NSG allow rule open to all IPv4 is pending approval.

If a policy is disabled, an Admin can use `PATCH /api/v1/policies/{policy_id}/enabled?enabled=true`.

## 10. Case 1 — Low-risk VM tag auto-remediation

1. Confirm `.env` has `CLOUDGUARD_AZURE_MOCK=false` for live Azure access.
2. Run `POST /api/v1/scans` with:

```json
{
  "subscription_id": "<YOUR_TEST_SUBSCRIPTION_GUID>"
}
```

3. Expect a scan response with `status: COMPLETED` if the scan finished successfully.
4. Run `GET /api/v1/findings` and inspect findings for `VM_REQUIRED_ENVIRONMENT_TAG`.
5. If a VM lacked the tag, the scan service attempts the automatic update during the scan. The finding should become `RESOLVED` on success, or `OPEN` if the Azure update failed.
6. Verify the actual Azure VM tags using Azure CLI (read-only):

```powershell
az vm show --resource-group "<VM_RESOURCE_GROUP>" --name "<VM_NAME>" --subscription "<YOUR_TEST_SUBSCRIPTION_GUID>" --query tags --output json
```

Confirm `Environment` equals `dev` and any previous tags remain present. A `COMPLETED` scan alone is not proof of successful remediation; verify the finding/action and actual Azure resource.

## 11. Case 2 — High-risk NSG rule and Security Officer approval

1. Run a scan as in Step 10.
2. Run `GET /api/v1/findings`; locate `NSG_INBOUND_ANY_IPV4` findings with severity `HIGH` and status `PENDING_APPROVAL`.
3. Log in to CloudGuard using the `security` account and its configured password, or use an Admin token. Authorize Swagger with this token.
4. Run `GET /api/v1/approvals/pending` and confirm the finding is listed.
5. Before approving, identify the approved source CIDR with your network/security team. Do not guess it. The API rejects broad IPv4 `/0` replacement ranges.
6. Run `POST /api/v1/approvals/findings/{finding_id}/approve` with:

```json
{
  "replacement_source_cidr": "<APPROVED_RESTRICTED_IPV4_CIDR>"
}
```

7. The endpoint records the approver and executes the NSG rule update in the same API operation. A successful response should report `RESOLVED` and a successful action result.
8. Verify the actual NSG rule in Azure before declaring success. If the Azure operation fails, the endpoint returns an error and records the failed action; inspect the finding and audit log.

**Never copy a documentation/example CIDR into production without confirming it is the intended network range.** Use a dedicated test NSG/rule for practice.

## 12. Audit log and scans

- `GET /api/v1/scans/{scan_id}` — inspect scan status and timestamps.
- `GET /api/v1/audit-logs?limit=100` — Admin-only view of audit records. Limit is clamped to 1–500.
- `GET /api/v1/findings?status=PENDING_APPROVAL` — filter findings by status.
- `GET /api/v1/findings?severity=HIGH` — filter by severity.

## 13. Run unit tests

Open a separate terminal in the repository root, activate `.venv`, and run:

```powershell
pytest
```

The tests exercise policy predicates and security helpers; they do not call Azure to verify live resources.

## 14. Stop and restart

- Stop FastAPI with `Ctrl+C` in its terminal.
- Stop PostgreSQL without deleting its data:

```powershell
docker compose stop postgres
```

- Start PostgreSQL again:

```powershell
docker compose up -d postgres
```

- Restart the API with the Uvicorn command in Step 6.

To remove the container but preserve its database volume, use `docker compose down` (do not add `-v`). `docker compose down -v` deletes the volume and should be used only when you intentionally want to remove the database data.

## Troubleshooting quick reference

| Symptom | What to check |
|---|---|
| Password authentication failed | `.env` DB credentials vs actual PostgreSQL user password; existing volume password behavior |
| Connection refused on `5432` | Compose maps host `5433` to container `5432`; use host port `5433` in `DATABASE_URL` |
| `401 Invalid username or password` | Username/password values at the time that user was created; seed password changes do not reset existing users |
| `401 Invalid or expired token` | Login again and re-authorize Swagger with a fresh token |
| `403 Insufficient role` | Use an account with the required CloudGuard role |
| Subscription not registered | Register it with `POST /api/v1/subscriptions` as Admin |
| Azure authentication error | Run `az login` in the same Windows user context as Uvicorn; verify `az account show` |
| Azure authorization error | Verify Azure RBAC for the logged-in identity at the correct resource scope |
| Finding is `RESOLVED` but resource not changed | Verify Azure directly; inspect remediation action and audit records |
| Database tables not visible | Start the API successfully, then reconnect and run `\dt` |

## What is not included in this phase

The app is not containerized; only PostgreSQL runs in Docker. Kubernetes/AKS deployment, CI/CD, scheduled scanning, notifications, and additional policy/resource types are deferred. The existing audit hash chain is tamper-evident but not immutable against a database administrator rewriting the database.
