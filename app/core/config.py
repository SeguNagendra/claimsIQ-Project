from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CloudGuard"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://cloudguard:ChangeThisDbPassword@localhost:5432/cloudguard"
    jwt_secret_key: str = "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET"
    jwt_expire_minutes: int = 60

    azure_subscription_id: str = ""
    azure_client_id: str = ""
    cloudguard_azure_mock: bool = False

    seed_admin_username: str = "admin"
    seed_admin_password: str = "ChangeMe_Admin_123!"
    seed_engineer_username: str = "engineer"
    seed_engineer_password: str = "ChangeMe_Engineer_123!"
    seed_security_username: str = "security"
    seed_security_password: str = "ChangeMe_Security_123!"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
