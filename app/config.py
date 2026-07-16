import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./subverify.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    upload_dir: str = "./uploads"
    expiry_alert_window_days: int = 30

    class Config:
        env_file = ".env"


settings = Settings()
os.makedirs(settings.upload_dir, exist_ok=True)
