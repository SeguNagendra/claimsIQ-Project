# ClaimIQ — Step-by-Step Local Setup and Swagger Testing

This guide is written for someone who has not run the project before. Follow the steps in order. It covers PostgreSQL from Docker Hub, Python setup, starting the API, testing the claim workflow, uploading a policy document, processing it for RAG, and asking a policy question.

> **Important:** Run PowerShell commands from the project root — the folder containing `requirements.txt`, `app`, `dashboard`, `scripts`, and `tests`. This guide does not change application logic. It is for local demonstration only.

## What you need

- Windows with Docker Desktop installed and running.
- Python 3.12 (recommended for this project) and PowerShell.
- The ClaimIQ project ZIP extracted to a normal folder.
- Access/configuration for the Azure services used by RAG: Azure Blob Storage, Azure AI Search, and Azure OpenAI.
- A PDF or DOCX policy file for the RAG demo.

## 1. Open the project folder

Extract the ZIP. Open PowerShell and change to the extracted project directory. Example (replace the path if you extracted it somewhere else):

```powershell
cd "C:\Users\<your-user>\Desktop\claimq"
```

Confirm you are in the right folder:

```powershell
Get-ChildItem
```

You should see `requirements.txt`, `app`, `dashboard`, `scripts`, and `tests`.

## 2. Pull PostgreSQL from Docker Hub

Make sure Docker Desktop is open. In PowerShell, run:

```powershell
docker pull postgres:17-alpine
```

This downloads PostgreSQL 17 with Alpine Linux. Alpine is a small Linux base image used to keep the image relatively lightweight.

## 3. Create and start the PostgreSQL container

The following commands create a Docker volume for persistent database files and start PostgreSQL with a database named `claimiq`. They publish port 5433 on your Windows computer and forward it to port 5432 inside the container.

Use a local demo password and keep it consistent with the `DATABASE_URL` in Step 5.

```powershell
docker volume create claimiq_pgdata
docker run --name claimiq-postgres --detach --restart unless-stopped --publish 5433:5432 --env POSTGRES_DB=claimiq --env POSTGRES_USER=claimiq_local --env POSTGRES_PASSWORD=ClaimIQLocal123 --volume claimiq_pgdata:/var/lib/postgresql/data postgres:17-alpine
```

If Docker says a container named `claimiq-postgres` already exists, do not run `docker run` again. Start the existing container:

```powershell
docker start claimiq-postgres
```

Check that it is running and ready:

```powershell
docker ps
docker exec -it claimiq-postgres pg_isready -U claimiq_local -d claimiq
```

Expected: `accepting connections`.

### If port 5433 is already in use

Choose another free host port (for example, 5434) in the `--publish` argument and use that same port in `DATABASE_URL` in Step 5.

## 4. Create and activate a Python virtual environment

In PowerShell, from the project root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run this in the same PowerShell window, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

If `py -3.12` is not available, install Python 3.12 or use the installed Python version supported by the dependencies. Keep the virtual environment activated for the remaining commands.

## 5. Configure the `.env` file

The `.env` file tells ClaimIQ which database and Azure services to use.

1. If `.env` already exists, make a backup and edit it; do not overwrite working Azure settings.
2. If `.env` does not exist, copy the template:

```powershell
Copy-Item .env.example .env
```

3. Open `.env` in Notepad:

```powershell
notepad .env
```

Set the database values to match Step 3. For the commands above, the local database entries should be:

```env
DATABASE_URL=postgresql+psycopg2://claimiq_local:ClaimIQLocal123@127.0.0.1:5433/claimiq
JWT_SECRET=replace-with-a-long-random-local-secret
ACCESS_TOKEN_MINUTES=120
```

Do not paste the example JWT secret into a production deployment. If your database password contains URL-special characters such as `@`, `:`, `/`, or `#`, URL-encode them in `DATABASE_URL`.

### Azure settings needed for RAG

Fill these values with the actual endpoints, deployment names, and credentials from your Azure resources. Do not leave the placeholder text from `.env.example`.

```env
AZURE_STORAGE_ACCOUNT_NAME=your-storage-account-name
AZURE_STORAGE_CONTAINER=policy-documents
AZURE_STORAGE_CONNECTION_STRING=your-storage-connection-string
AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
AZURE_SEARCH_INDEX_NAME=policy-chunks
AZURE_SEARCH_API_KEY=your-search-admin-key
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/openai/v1/
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=your-embedding-deployment-name
AZURE_OPENAI_CHAT_DEPLOYMENT=your-chat-deployment-name
AZURE_OPENAI_API_KEY=your-openai-api-key
RAG_TOP_K=5
RAG_MIN_SEARCH_SCORE=0.5
MAX_DOCUMENT_SIZE_MB=10
```

Use the exact deployment names configured in your Azure OpenAI resource. The embedding deployment must return vectors compatible with the search index. The app's index setup script calculates the embedding dimension from the configured embedding deployment.

Keep `.env` private. Do not share it or commit it to source control.

## 6. Create the database tables, demo accounts, and Azure AI Search index

Make sure PostgreSQL is running and `.env` is saved. From the project root, run:

```powershell
python -m app.init_db
```

This command:
- creates any missing PostgreSQL tables;
- inserts demo users, 50 sample policies, and a sample claim if they are not already present;
- creates or updates the Azure AI Search index named in `.env`.

It does **not** drop the database or re-create all existing records from scratch. If it fails during Azure index creation, check the Azure settings and permissions before proceeding.

## 7. Start the FastAPI backend

In the same PowerShell window, run:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Leave this window open. It is running the API.

Open Swagger UI in your browser:

**http://127.0.0.1:8000/docs**

If Swagger does not open, check the PowerShell error and make sure port 8000 is not already occupied.

## 8. Sign in to Swagger

In Swagger, expand `POST /auth/token` and click **Try it out**. This endpoint uses form fields, not a JSON request body:

- `username`: `admin`
- `password`: `demo123`

Click **Execute**. A successful response contains `access_token`.

Then click the green **Authorize** button near the top of Swagger. Enter the token as a bearer token if the dialog asks for it. In many Swagger setups, pasting the access token alone is sufficient; do not type the word `Bearer` twice. Click **Authorize**, then close the dialog.

The seed script creates these demo users with password `demo123`:

| Username | Role | Use |
|---|---|---|
| `admin` | `admin` | Manage policies/documents, assign claims, analytics and audit |
| `reviewer` | `reviewer` | Review claims, assign adjusters, approve/deny, analytics |
| `adjuster` | `adjuster` | Work assigned claims, add notes, ask policy questions |
| `customer` | `customer` | Submit and view own claims |
| `customer2` to `customer50` | `customer` | Separate demo customer accounts |
| `adjuster1` to `adjuster5` | `adjuster` | Additional demo adjusters |
| `support_agent` | `support_agent` | Read permitted claim/document data and ask policy questions |

To switch roles, log in again using `POST /auth/token`, then use **Authorize** with the new token.

## 9. Test the claims workflow

Swagger is grouped by endpoint tags. Use the live schemas displayed in Swagger; they are the source of truth for required fields.

### 9.1 Check the API

- Expand `GET /health`.
- Click **Try it out** → **Execute**.
- Expected: `200` and `{"status":"ok"}`.

### 9.2 Check your login and role

- Use `GET /users/me` after authorization.
- Expected: your username and role.

### 9.3 Find a policy owned by the customer

- Sign in as `customer`.
- Expand `GET /policies` and execute it.
- Find the policy number `POL-0001`. The seed data assigns it to `customer`.
- Record its numeric `id`. The claim API needs `policy_id`, which is this database ID, not the policy number.

### 9.4 Submit a claim

- Stay authorized as `customer`.
- Expand `POST /claims` → **Try it out**.
- Enter JSON using the policy ID you just looked up. Example:

```json
{
  "policy_id": 1,
  "description": "Hospitalization for fever and viral infection, including doctor consultation, diagnostic tests, medicines, and treatment.",
  "amount": 25000
}
```

Replace `1` with the actual ID returned by `GET /policies`. Click **Execute**.

Expected: `201 Created`, with a claim `id` and status `submitted`. A claim is automatically assigned to an active adjuster. Record the returned claim ID for later steps.

### 9.5 View the claim

- Use `GET /claims` as the customer to see claims belonging to that customer.
- Use `GET /claims/{claim_id}` and replace the path parameter with the claim ID from the response.
- If the claim is not visible to the customer you logged in as, check that the policy belongs to that customer.

### 9.6 Assign an adjuster (optional; a claim is already assigned automatically)

- Authorize as `admin` or `reviewer`.
- Run `GET /users` and find an active user whose role is `adjuster`. Record their numeric user ID.
- Run `POST /claims/{claim_id}/assignment` with body:

```json
{
  "user_id": 4
}
```

Replace `4` with the actual adjuster user ID and use your claim ID in the URL.

### 9.7 Move the claim to Under Review

- Authorize as the assigned `adjuster` (or admin/reviewer where permitted by the route).
- Run `POST /claims/{claim_id}/status` with:

```json
{
  "status": "under_review"
}
```

Expected: status `under_review`.

### 9.8 Add an adjuster note

Authorize as the assigned adjuster, admin, or reviewer. Run `POST /claims/{claim_id}/notes`:

```json
{
  "text": "Review the hospital bill, discharge summary, prescriptions, diagnostic reports, policy limits, waiting periods, and applicable exclusions before making a decision."
}
```

This is a sample note for demo purposes. Run `GET /claims/{claim_id}/notes` to see the saved note.

### 9.9 View status history

Run `GET /claims/{claim_id}/history`. The response shows each recorded status, the previous status, and any justification saved for an admin override.

### 9.10 Make a decision and close the claim (optional)

A reviewer or admin can decide the claim after review. Run `POST /claims/{claim_id}/status` with one of these bodies:

Approve:
```json
{"status": "approved"}
```

Deny:
```json
{"status": "denied"}
```

Only choose one. After a decision, a later status update can close the claim:
```json
{"status": "closed"}
```

Do not close a claim unless you want to complete this demo workflow. Status transitions are enforced by the API.

### 9.11 Analytics and audit

- Authorize as `admin` or `reviewer`; run `GET /analytics/summary`.
- Authorize as `admin`; run `GET /audit`.
- The analytics response includes claim counts/statuses, amount totals, SLA/TAT metrics, and adjuster workload. Audit shows selected action metadata.

## 10. Test the policy-document RAG workflow

This is separate from submitting a claim. The policy document must be uploaded and processed before asking questions about it.

### 10.1 Upload a policy PDF/DOCX

Authorize as `admin`.

- Expand `POST /documents`.
- Click **Try it out**.
- Fill the form fields:
  - `policy_code`: for example `POL-0001`
  - `document_name`: `Health Insurance Policy`
  - `version`: `1`
  - `effective_from`: `2026-01-01` (use a date appropriate for your demo)
  - `replaces_document_id`: leave blank for a new document
  - `file`: select the local PDF or DOCX file
- Click **Execute**.

Expected: `201 Created`, with `document_id` and status `UPLOADED`. Copy the returned `document_id`.

> A policy document's `policy_code` is metadata for the document search. It is not the numeric `policy_id` used when creating a claim.

### 10.2 Process the document

- Expand `POST /documents/{document_id}/process`.
- Paste the exact `document_id` from the upload response into the path field.
- Click **Execute**.

Expected: status `ACTIVE` and `is_active: true`. Processing extracts text, splits it into chunks, generates embeddings, and indexes them in Azure AI Search.

If it returns `503`, inspect the terminal running Uvicorn for the detailed error. Confirm the Blob Storage, Azure AI Search, and Azure OpenAI settings in `.env`, that the index exists, and that the service credentials are valid.

### 10.3 Ask a policy question

Authorize as `admin`, `reviewer`, `adjuster`, or `support_agent`.

- Expand `POST /ai/query`.
- Click **Try it out** and enter:

```json
{
  "question": "What documents should the adjuster verify for a hospitalization claim, and what policy conditions or exclusions should be checked?"
}
```

Optionally, add `"policy_code": "POL-0001` to restrict retrieval to that policy code:

```json
{
  "question": "What documents should the adjuster verify for a hospitalization claim, and what policy conditions or exclusions should be checked?",
  "policy_code": "POL-0001"
}
```

Expected: a response containing `answer`, `sources`, `response_time_ms`, and `status`. The status may be `ANSWERED`, `NO_MATCH`, `LOW_CONFIDENCE`, or `ERROR` depending on retrieval and service configuration. Check the source document/version/page references and verify the answer against the policy before relying on it. RAG does not automatically approve or deny a claim.

### 10.4 List documents and check status

- `GET /documents` lists document metadata (authorized roles).
- `GET /documents/{document_id}` shows one document's metadata.
- `PATCH /documents/{document_id}/activation` can activate/deactivate a processed document. This endpoint uses a form field named `active` (`true` or `false`) and is admin-only.

## 11. Start the dashboard (optional)

Keep the FastAPI terminal running. Open a second PowerShell terminal, go to the project root, and activate the same virtual environment:

```powershell
cd "C:\path\to\claimq"
.\.venv\Scripts\Activate.ps1
python -m streamlit run dashboard/app.py
```

Open **http://localhost:8501**. Sign in with `admin` or `reviewer` and password `demo123`. The dashboard calls the API at `http://127.0.0.1:8000` by default. To change that address, set `CLAIMIQ_API_URL` before starting Streamlit.

## 12. Inspect PostgreSQL data (optional)

Open another PowerShell terminal:

```powershell
docker exec -it claimiq-postgres psql -U claimiq_local -d claimiq
```

At the `claimiq=#` prompt, list tables:

```sql
\dt
```

Read-only examples:

```sql
SELECT id, username, role, active FROM users ORDER BY id;
SELECT id, number, holder, owner_id, active FROM policies ORDER BY id;
SELECT id, policy_id, owner_id, assigned_to, amount, status FROM claims ORDER BY id;
SELECT id, claim_id, old_status, new_status, justification, created_at
FROM claim_status_history ORDER BY id;
SELECT id, claim_id, author_id, text, created_at FROM claim_notes ORDER BY id;
SELECT id, actor_id, action, resource, created_at FROM audit_logs ORDER BY id DESC;
SELECT id, policy_code, document_name, version, status, is_active FROM documents ORDER BY uploaded_at DESC;
SELECT question, answer, status, response_time_ms FROM chat_query_logs ORDER BY created_at DESC;
```

Exit PostgreSQL with `\q`.

## 13. Common problems

### Docker says the container name already exists
Use `docker start claimiq-postgres`. Do not create another container with the same name.

### The application cannot connect to PostgreSQL
Check `docker ps`, then run `docker exec -it claimiq-postgres pg_isready -U claimiq_local -d claimiq`. Check that `DATABASE_URL` uses the host port you published (5433 in this guide) and the same username/password as the container.

### `python -m app.init_db` fails
Read the full error in the terminal. Database table creation/seed needs PostgreSQL; the index setup additionally needs working Azure OpenAI embedding configuration and Azure AI Search access.

### Swagger returns `401 Unauthorized`
Use `POST /auth/token`, then click **Authorize** and supply the new access token. PostgreSQL credentials are not the same as ClaimIQ login credentials.

### Swagger returns `403 Forbidden`
The signed-in user may not have permission for that endpoint. Re-authorize as a role listed for that endpoint.

### Claim creation returns `422` or `409`
Check that `policy_id` is the numeric ID of an active policy owned by the signed-in customer. The seeded `POL-0001` belongs to `customer`; `POL-0002` belongs to `customer2`, and so on.

### RAG document processing returns `503`
Check the Uvicorn terminal for the detailed exception. Confirm `.env` has correct Blob Storage, Azure AI Search, and Azure OpenAI configuration, the `policy-chunks` index is available, and the selected PDF/DOCX contains extractable text. Scanned/image-only PDFs are not OCR-processed.

### RAG returns `NO_MATCH` or `LOW_CONFIDENCE`
Confirm the document was successfully processed and is active, ask a question covered by the uploaded document, and check that `RAG_MIN_SEARCH_SCORE` is appropriate for your search configuration. Do not invent or assume an answer when no supporting policy passages are returned.
