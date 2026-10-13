import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://localhost/claimiq")
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg2://localhost/claimiq_test")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads")).resolve()
JWT_SECRET = os.getenv("JWT_SECRET", "local-demo-only-change-before-shared-use")
