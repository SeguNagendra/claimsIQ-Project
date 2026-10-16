from app.config import AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_SEARCH_API_KEY


def get_openai_client():
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import OpenAI
    if not AZURE_OPENAI_ENDPOINT:
        raise ValueError("AZURE_OPENAI_ENDPOINT is missing from .env")
    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/") + "/"
    if AZURE_OPENAI_API_KEY:
        return OpenAI(base_url=endpoint, api_key=AZURE_OPENAI_API_KEY)
    provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
    return OpenAI(base_url=endpoint, api_key=provider)


def get_search_credential():
    from azure.core.credentials import AzureKeyCredential
    from azure.identity import DefaultAzureCredential
    return AzureKeyCredential(AZURE_SEARCH_API_KEY) if AZURE_SEARCH_API_KEY else DefaultAzureCredential()
