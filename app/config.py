import os
import secrets
from pathlib import Path
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
DATABASE_URL = os.getenv(
	"DATABASE_URL",
	"postgresql+psycopg2://claimiq:YOUR_DATABASE_PASSWORD@127.0.0.1:5432/claimiq",
)
# Never use the visible template placeholder as a signing key. Set JWT_SECRET
# in .env or the deployment environment to keep tokens valid across restarts.
_configured_jwt_secret = os.getenv("JWT_SECRET", "")
JWT_SECRET = (
	_configured_jwt_secret
	if _configured_jwt_secret and not _configured_jwt_secret.startswith("YOUR_")
	else secrets.token_urlsafe(32)
)
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "120"))
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "")
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "policy-documents")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "")
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "policy-chunks")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
RAG_TOP_K = max(1, min(int(os.getenv("RAG_TOP_K", "5")), 10))
RAG_MIN_SEARCH_SCORE = float(os.getenv("RAG_MIN_SEARCH_SCORE", "0.5"))
MAX_DOCUMENT_SIZE_BYTES = int(os.getenv("MAX_DOCUMENT_SIZE_MB", "10")) * 1024 * 1024
