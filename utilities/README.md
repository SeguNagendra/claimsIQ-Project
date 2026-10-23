# Container and AKS deployment

The FastAPI application image and deployment files are kept here. PostgreSQL
runs as a container in Docker Compose locally and as a Kubernetes StatefulSet
inside AKS; no Azure Database for PostgreSQL service is created. AKS provisions
a persistent volume for the PostgreSQL StatefulSet using the cluster's default
storage class.

## Run locally

1. Copy `.env.example` to `.env` in this directory.
2. Replace all example passwords and the JWT secret. Use the same
   URL-safe password in `POSTGRES_PASSWORD` and `DATABASE_URL`.
3. Start both containers from the repository root:

   ```powershell
   docker compose --env-file utilities/.env -f utilities/docker-compose.yml up --build
   ```

4. Open `http://localhost:8000/docs`. To stop the containers, run:

   ```powershell
   docker compose --env-file utilities/.env -f utilities/docker-compose.yml down
   ```

The named `cloudguard_pgdata` volume is retained when containers stop. Remove
it separately only when intentionally discarding local database data.

## GitHub Actions prerequisites

The workflow at `.github/workflows/azure-aks.yml` tests the code, builds and
pushes an immutable image to ACR, then deploys it to AKS on pushes to `main`
or when manually started.

Configure these **GitHub repository variables**:

| Variable | Value |
| --- | --- |
| `ACR_NAME` | ACR resource name, without `.azurecr.io` |
| `AZURE_RESOURCE_GROUP` | Resource group containing the AKS cluster |
| `AKS_CLUSTER_NAME` | AKS cluster name |

Configure these **GitHub repository secrets**:

| Secret | Value |
| --- | --- |
| `AZURE_CLIENT_ID` | Entra application/service principal client ID |
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `DATABASE_URL` | `postgresql+psycopg://<user>:<password>@postgres:5432/<database>` |
| `POSTGRES_DB` | Database name; must match `DATABASE_URL` |
| `POSTGRES_USER` | Database user; must match `DATABASE_URL` |
| `POSTGRES_PASSWORD` | Database password; must match `DATABASE_URL` |
| `JWT_SECRET_KEY` | Long, randomly generated signing key |
| `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD` | Initial admin account |
| `SEED_ENGINEER_USERNAME` / `SEED_ENGINEER_PASSWORD` | Initial engineer account |
| `SEED_SECURITY_USERNAME` / `SEED_SECURITY_PASSWORD` | Initial security account |

Set up a GitHub Actions federated identity credential for the Entra
application/service principal so `azure/login` can use OIDC. Grant it permission
to push to the ACR, retrieve AKS user credentials, and deploy Kubernetes
resources to the cluster. The agent must be allowed to create the `cloudguard`
namespace and its namespaced resources. Ensure AKS can pull from the ACR (for
example, attach the registry to the cluster).

The AKS API Service is configured as a public `LoadBalancer`. Once the
deployment completes, retrieve its external address with:

```sh
kubectl get service cloudguard-api --namespace cloudguard
```

The PostgreSQL service is cluster-internal only. Back up the persistent volume
before deleting the database StatefulSet or its PVC.

## Azure SDK authentication note

The existing application code uses `AzureCliCredential` for live Azure scans
and remediations. A normal application container in AKS does not have an Azure
CLI login session. This deployment does not change that application logic;
live Azure operations will require an appropriate credential approach in the
application/container environment. `CLOUDGUARD_AZURE_MOCK` is set to `false` in
the AKS ConfigMap; setting it to `true` enables the existing mock behavior,
not live Azure access.
