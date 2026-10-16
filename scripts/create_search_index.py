from app.config import AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX_NAME

def main():
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import HnswAlgorithmConfiguration, SearchField, SearchFieldDataType, SearchIndex, SearchableField, SimpleField, VectorSearch, VectorSearchProfile
    from app.services.azure_auth import get_search_credential
    from app.services.embedding_service import EmbeddingService
    if not AZURE_SEARCH_ENDPOINT: raise ValueError("AZURE_SEARCH_ENDPOINT is missing from .env")
    dimension = len(EmbeddingService().generate_embedding("ClaimIQ vector dimension check"))
    fields = [SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True), SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True), SimpleField(name="policy_code", type=SearchFieldDataType.String, filterable=True), SearchableField(name="document_name", type=SearchFieldDataType.String), SimpleField(name="version", type=SearchFieldDataType.String, filterable=True), SimpleField(name="chunk_number", type=SearchFieldDataType.Int32, sortable=True), SearchableField(name="chunk_text", type=SearchFieldDataType.String), SimpleField(name="page_number", type=SearchFieldDataType.Int32, filterable=True), SimpleField(name="is_active", type=SearchFieldDataType.Boolean, filterable=True), SearchField(name="content_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), searchable=True, vector_search_dimensions=dimension, vector_search_profile_name="claimiq-vector-profile")]
    vector = VectorSearch(algorithms=[HnswAlgorithmConfiguration(name="claimiq-hnsw")], profiles=[VectorSearchProfile(name="claimiq-vector-profile", algorithm_configuration_name="claimiq-hnsw")])
    SearchIndexClient(AZURE_SEARCH_ENDPOINT, get_search_credential()).create_or_update_index(SearchIndex(name=AZURE_SEARCH_INDEX_NAME, fields=fields, vector_search=vector))
    print(f"Search index '{AZURE_SEARCH_INDEX_NAME}' is ready ({dimension} dimensions).")
if __name__ == "__main__": main()
