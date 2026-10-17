from app.config import AZURE_STORAGE_ACCOUNT_NAME, AZURE_STORAGE_CONNECTION_STRING, AZURE_STORAGE_CONTAINER

class BlobStorageService:
    def __init__(self):
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
        if AZURE_STORAGE_CONNECTION_STRING:
            self.client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        else:
            if not AZURE_STORAGE_ACCOUNT_NAME:
                raise ValueError("AZURE_STORAGE_ACCOUNT_NAME is missing from .env")
            self.client = BlobServiceClient(
                f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
                credential=DefaultAzureCredential(),
            )
        self.container_client = self.client.get_container_client(AZURE_STORAGE_CONTAINER)

    def upload_bytes(self, path, content, content_type):
        from azure.storage.blob import ContentSettings
        blob = self.container_client.get_blob_client(path)
        blob.upload_blob(content, overwrite=False, content_settings=ContentSettings(content_type=content_type))
        return blob.url

    def download_bytes(self, path):
        return self.container_client.get_blob_client(path).download_blob().readall()
