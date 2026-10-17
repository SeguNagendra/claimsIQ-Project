# ClaimIQ container and AKS deployment

The application runs as separate FastAPI and Streamlit containers. PostgreSQL
runs inside Docker Compose for local use and inside AKS as a single-replica
StatefulSet backed by a persistent volume claim. This setup does not provision
or connect to Azure Database for PostgreSQL.

## Run locally with Docker Compose

1. If the repository root has no `.env`, copy `utilities/.env.example` there.
   If `.env` already exists, merge the required settings from the example into
   it without overwriting existing values.
2. Replace all four required example values with unique values. Keep the
   PostgreSQL password URL-safe (letters, numbers, hyphens, and underscores)
   because Compose constructs the SQLAlchemy connection URL from it.
3. Start the containers from the repository root:

   ```sh
   docker compose -f utilities/docker-compose.yml up --build
   ```

4. Open the dashboard at <http://localhost:8501> or the API at
   <http://localhost:8000/docs>. Sign in with the administrator username and
   password from `.env`.
5. Stop the services with `docker compose -f utilities/docker-compose.yml down`.
   To also delete the local PostgreSQL data, explicitly add `--volumes`.

The bootstrap container creates the tables and initial administrator on first
startup. It does not add the demo users/passwords from `app.seed`. If that
administrator already exists, its password is left unchanged.

## Azure resources required before deployment

Create these resources in the target Azure subscription before running the
workflow:

- An Azure Container Registry (ACR).
- An AKS cluster with permission to pull images from that ACR. Attach the
  registry to the cluster once, for example:

  ```sh
  az aks update --resource-group <resource-group> --name <cluster-name> \
    --attach-acr <registry-name>
  ```

- A default AKS StorageClass that supports `ReadWriteOnce` Azure disk claims.
- A GitHub Actions service principal with permission to push to ACR and get
  AKS credentials/deploy workloads to the cluster.

The workflow uses a Kubernetes `LoadBalancer` service for both the API and
dashboard, which creates public Azure load balancer endpoints. Restrict access
or change the service types to `ClusterIP` if public access is not intended.
Configure TLS and ingress separately if required.

## GitHub Actions setup

The workflow is `.github/workflows/deploy-aks.yml`. It runs tests, builds and
pushes immutable commit-SHA-tagged API and dashboard images, initializes the
in-cluster PostgreSQL database, and deploys both services.

Set these repository **Variables**:

- `ACR_NAME`: ACR name without `.azurecr.io`.
- `AZURE_RESOURCE_GROUP`: resource group containing AKS.
- `AKS_CLUSTER_NAME`: AKS cluster name.

Set these repository **Secrets**:

- `AZURE_CREDENTIALS`: Azure service principal JSON accepted by `azure/login`.
- `POSTGRES_PASSWORD`: strong PostgreSQL password.
- `JWT_SECRET`: long, random signing secret.
- `CLAIMIQ_ADMIN_USERNAME`: initial administrator login name.
- `CLAIMIQ_ADMIN_PASSWORD`: strong initial administrator password.

Pushes to `main` or `master` that change application or deployment files run
the workflow automatically. It can also be started manually with
**Actions → Build and deploy ClaimIQ to AKS → Run workflow**.

AKS keeps PostgreSQL data on its persistent volume across pod restarts and
application deployments. Back up that volume/database separately; it is not
automatically replicated by this single-replica setup. Schema updates beyond
creating new tables require a migration process before deploying model changes.

Optional Azure Blob Storage, AI Search, and Azure OpenAI settings can be
provided by creating the `claimiq-config` ConfigMap entries and the
`claimiq-azure-services` Kubernetes Secret (keys:
`storage-connection-string`, `search-api-key`, and `openai-api-key`). The
application's non-secret endpoint/deployment variables belong in the
ConfigMap, not in the Secret.
