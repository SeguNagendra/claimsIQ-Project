# CloudGuard — Phase 1 (local Swagger testing)

This package implements the agreed Phase 1 scope:
- FastAPI application, run directly with Python.
- PostgreSQL runs as a Docker container.
- Database tables and initial records are created automatically on application startup.
- JWT login and role-based access control.
- Azure VM `Environment` tag policy: if missing, add `Environment=dev` automatically.
- NSG inbound source `0.0.0.0/0` policy: create a high-severity finding and require Security Officer approval before remediation.
- Unit tests for policy evaluation and JWT/password utilities.
- Azure access via a User-Assigned Managed Identity (UAMI).

## Important managed identity limitation

A UAMI can only be used by an application running in an Azure environment where that UAMI is attached and available through the managed identity endpoint. Creating a UAMI in Azure does **not** make it usable by a Python process running directly on your Windows laptop.

For real Azure scans with UAMI, run the Python application on an Azure VM with the UAMI attached. You can open Swagger locally through an SSH tunnel. For offline code testing on a laptop, set `CLOUDGUARD_AZURE_MOCK=true`; mock mode does not contact or modify Azure.

## Prerequisites

- Python 3.11+
- Docker Desktop (Windows) or Docker Engine
- Azure CLI for provisioning Azure resources
- An Azure subscription and permission to assign RBAC roles / attach a UAMI
- For live Azure operations: an Azure VM with the UAMI attached and appropriate RBAC permissions

## 1. Extract and configure

Open PowerShell in the extracted `cloudguard_phase1` folder:

```powershell
Copy-Item .env.example .env
```

Edit `.env`. Set:
- `DATABASE_URL` to match the PostgreSQL password in `docker-compose.yml` / `POSTGRES_PASSWORD`.
- `JWT_SECRET_KEY` to a long random secret.
- `AZURE_SUBSCRIPTION_ID` to the subscription you intend to scan.
- `AZURE_CLIENT_ID` to the UAMI **client ID**, not its resource ID or principal/object ID.
- `CLOUDGUARD_AZURE_MOCK=false` for live Azure access, or `true` for offline mock testing.

Set the same DB password in `.env` and the Compose environment. Example default for a quick dev-only start:
`DATABASE_URL=postgresql+psycopg://cloudguard:ChangeThisDbPassword@localhost:5432/cloudguard`
and `POSTGRES_PASSWORD=ChangeThisDbPassword`.

Change the three seed passwords in `.env` before running outside a disposable development environment.

## 2. Start PostgreSQL (pulls image automatically)

```powershell
docker compose up -d postgres
docker compose ps
docker compose logs postgres
```

Compose pulls `postgres:16-alpine` if it is not already available. Persistent data is stored in the `cloudguard_pgdata` Docker volume.

## 3. Create Python environment and install packages

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On Linux, use `python3 -m venv .venv` and `source .venv/bin/activate`.

## 4. One-click DB/table initialization and start API

There is no separate table-creation command. Starting the API creates missing tables and seeds the initial users and policies automatically:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/docs>.

If the database connection fails, verify that `DATABASE_URL` credentials match `POSTGRES_PASSWORD` and that the container is healthy.

## 5. Development-only offline test (no Azure calls)

For laptop-only API / mock-scan testing, set this in `.env`:

```dotenv
CLOUDGUARD_AZURE_MOCK=true
```

Keep a valid-looking `AZURE_SUBSCRIPTION_ID` value. Restart Uvicorn after changing `.env`. In mock mode, the scan returns two sample VMs and one sample NSG finding; it does not change Azure. Register that subscription in Swagger before scanning.

## 6. Provision a UAMI for live Azure access

Run from an account allowed to create identities and assign roles. Replace the placeholders:

```powershell
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az identity create --resource-group "<IDENTITY_RESOURCE_GROUP>" --name "uami-cloudguard"
az identity show --resource-group "<IDENTITY_RESOURCE_GROUP>" --name "uami-cloudguard" --query "{clientId:clientId,principalId:principalId,id:id}" -o json
```

Record:
- `clientId` -> `AZURE_CLIENT_ID`
- `principalId` -> RBAC role assignment / identity attachment
- `id` -> resource ID for attaching the identity to the Azure VM

### Attach the UAMI to the Azure VM running CloudGuard

```powershell
az vm identity assign --resource-group "<APP_VM_RESOURCE_GROUP>" --name "<APP_VM_NAME>" --identities "<UAMI_RESOURCE_ID>"
```

The Python app must run on this Azure VM for UAMI authentication. It cannot use the VM's UAMI from a separate Windows laptop.

### Grant least-privilege RBAC

For read-only scanning, Reader at the target subscription scope is the simplest starting point:

```powershell
az role assignment create --assignee-object-id "<UAMI_PRINCIPAL_ID>" --assignee-principal-type ServicePrincipal --role "Reader" --scope "/subscriptions/<SUBSCRIPTION_ID>"
```

For VM tag remediation, grant the required tag-write permission at the narrowest applicable scope, for example the target VM or resource group. For approved NSG changes, grant `Network Contributor` only at the target NSG or its resource group scope. Do not grant write permissions at subscription scope unless specifically justified and approved by your organization.

Example role assignment commands (choose the correct target scope):
```powershell
az role assignment create --assignee-object-id "<UAMI_PRINCIPAL_ID>" --assignee-principal-type ServicePrincipal --role "Tag Contributor" --scope "<TARGET_VM_RESOURCE_ID>"
az role assignment create --assignee-object-id "<UAMI_PRINCIPAL_ID>" --assignee-principal-type ServicePrincipal --role "Network Contributor" --scope "<TARGET_NSG_RESOURCE_ID>"
```

Your account needs permission to create these role assignments. Allow time for RBAC propagation. Validate exact role availability and scope requirements in your Azure environment before applying write permissions.

## 7. Access Swagger locally while the app runs on an Azure VM

For safer testing, bind Uvicorn to loopback on the Azure VM:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From your local machine, establish an SSH tunnel (replace username and VM public IP/DNS):

```powershell
ssh -L 8000:127.0.0.1:8000 <VM_USERNAME>@<VM_PUBLIC_IP_OR_DNS>
```

Keep the SSH session open, then browse to <http://127.0.0.1:8000/docs> on your laptop. Ensure SSH access is appropriately restricted by your organization. Do not expose the API publicly for this initial test.

## 8. Test in Swagger

1. `POST /api/v1/auth/login` with one of the seeded users, e.g. `admin` and the password from `.env`.
2. Copy `access_token` from the response.
3. Click **Authorize** in Swagger and enter `Bearer <access_token>` if the UI asks for the full header value.
4. As Admin, `POST /api/v1/subscriptions` with `name` and `subscription_id`.
5. `GET /api/v1/policies` to see the two seeded policies.
6. `POST /api/v1/scans` with the registered `subscription_id`.
7. `GET /api/v1/findings` to review findings.
8. Log in as `security` and authorize with that token.
9. `GET /api/v1/approvals/pending`.
10. Approve an NSG finding with `POST /api/v1/approvals/findings/{finding_id}/approve`, body such as `{"replacement_source_cidr":"203.0.113.10/32"}`. This CIDR is documentation-only and should **not** be used as a real allowlist; use your approved corporate/VPN IP range for real remediation.
11. Log in as `admin` and call `GET /api/v1/audit-logs`.

The approve endpoint both records approval and executes the NSG source change. It rejects `0.0.0.0/0` as a replacement. Do not test live remediation against production resources.

## 9. Unit tests

```powershell
pytest
```

The tests cover policy evaluation and password/JWT helpers. Azure calls are not made by these unit tests.

## Seed accounts (development only)

- `admin` — role `ADMIN`
- `engineer` — role `CLOUD_ENGINEER`
- `security` — role `SECURITY_OFFICER`

Passwords are set by `SEED_*_PASSWORD` in `.env`. The accounts are created automatically if missing; changing a seed password after the account already exists does not reset that existing account's password.

## Notes and boundaries

- This is a practical Phase 1 scaffold, not a production-hardened compliance product.
- NSG scan currently examines NSGs in the registered subscription, not only NSGs attached to VM NICs.
- Detection is based on enabled inbound `Allow` rules with a source IPv4 prefix of `/0`, including `0.0.0.0/0`.
- The NSG remediation requires the officer to provide a restricted replacement IPv4 CIDR. CloudGuard cannot safely guess which corporate IP range should be allowed.
- Email notifications, scheduling, additional resource types, application containerization, Kubernetes, and CI/CD are deferred.
- The hash-linked audit entries are tamper-evident within the database chain but are not immutable against a database administrator rewriting the whole chain. Production needs protected/externally anchored audit storage.
