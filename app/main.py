from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.db.init import initialize_database
from app.api import routes_auth, routes_health, routes_subscriptions, routes_policies
from app.api import routes_scans, routes_findings, routes_approvals, routes_audit


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One-click initialization: create missing tables and seed initial users/policies.
    initialize_database()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="CloudGuard Phase 1: Azure VM tag compliance and NSG inbound exposure detection.",
    lifespan=lifespan,
)

app.include_router(routes_health.router, prefix=settings.api_prefix)
app.include_router(routes_auth.router, prefix=settings.api_prefix)
app.include_router(routes_subscriptions.router, prefix=settings.api_prefix)
app.include_router(routes_policies.router, prefix=settings.api_prefix)
app.include_router(routes_scans.router, prefix=settings.api_prefix)
app.include_router(routes_findings.router, prefix=settings.api_prefix)
app.include_router(routes_approvals.router, prefix=settings.api_prefix)
app.include_router(routes_audit.router, prefix=settings.api_prefix)
