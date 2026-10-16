from app.config import AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX_NAME, RAG_TOP_K
from app.services.azure_auth import get_search_credential

class SearchService:
    def __init__(self):
        from azure.search.documents import SearchClient
        if not AZURE_SEARCH_ENDPOINT:
            raise ValueError("AZURE_SEARCH_ENDPOINT is missing from .env")
        self.client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=AZURE_SEARCH_INDEX_NAME, credential=get_search_credential())

    def upload_chunks(self, chunks):
        if not chunks: return
        failed = [r for r in self.client.upload_documents(documents=chunks) if not r.succeeded]
        if failed: raise RuntimeError(f"{len(failed)} search records failed to index")

    def deactivate_chunks(self, ids):
        if not ids: return
        failed = [r for r in self.client.merge_documents(documents=[{"id": i, "is_active": False} for i in ids]) if not r.succeeded]
        if failed: raise RuntimeError(f"{len(failed)} search records failed to deactivate")

    def search(self, vector, policy_code=None, top_k=None):
        from azure.search.documents.models import VectorizedQuery
        filters = ["is_active eq true"]
        if policy_code: filters.append("policy_code eq '" + policy_code.replace("'", "''") + "'")
        k = top_k or RAG_TOP_K
        query = VectorizedQuery(vector=vector, k_nearest_neighbors=k, fields="content_vector")
        results = self.client.search(search_text=None, vector_queries=[query], filter=" and ".join(filters), select=["id", "document_id", "policy_code", "document_name", "version", "chunk_text", "page_number"], top=k)
        matches = []
        for item in results:
            row = dict(item); row["search_score"] = item.get("@search.score", 0.0); matches.append(row)
        return matches
