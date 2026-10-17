from app.config import AZURE_OPENAI_EMBEDDING_DEPLOYMENT
from app.services.azure_auth import get_openai_client

class EmbeddingService:
    def __init__(self):
        if not AZURE_OPENAI_EMBEDDING_DEPLOYMENT:
            raise ValueError("AZURE_OPENAI_EMBEDDING_DEPLOYMENT is missing from .env")
        self.client = get_openai_client()

    def generate_embedding(self, text):
        response = self.client.embeddings.create(model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT, input=text)
        return response.data[0].embedding
