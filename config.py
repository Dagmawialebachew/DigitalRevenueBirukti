import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Settings(BaseSettings):
    # Bot
    BOT_TOKEN: str = Field(default="", description="Telegram Bot API Token")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/biruktawit_bot",
        description="AsyncPG database connection string",
    )

    # Admins & Groups
    ADMIN_USER_IDS: str = Field(default="", description="Comma-separated admin Telegram IDs")
    ADMIN_CHANNEL_ID: int = Field(default=0, description="Fallback Telegram channel ID for payment reviews")
    ADMIN_PAYMENT_GID: int = Field(default=0, description="Telegram group/channel ID for payment reviews")
    ADMIN_NEWUSER_GID: int = Field(default=0, description="Telegram group/channel ID for new user notifications")
    ADMIN_ERROR_GID: int = Field(default=0, description="Telegram group/channel ID for error traceback alerts")

    # Creator & Support Identity
    CREATOR_NAME: str = "BIRUKTAWIT FIKRE"
    CREATOR_HANDLE: str = "@gebdaw"
    CREATOR_PHONE: str = "+251900000000"
    SUPPORT_BOT_USERNAME: str = "coachbiruktawitsupportbot"

    # Server & Webhook (for Render / Docker hosting)
    PORT: int = Field(default=8080, description="Web server port for Render health checks")
    WEBHOOK_URL: str = Field(default="", description="Optional Telegram webhook base URL")

    # Product pricing
    DEFAULT_PRICE_ETB: int = 950

    # Banking accounts (CBE & BOA only)
    CBE_ACCOUNT: str = "1000XXXXXXXXX"
    CBE_ACCOUNT_HOLDER: str = "BIRUKTAWIT FIKRE"
    BOA_ACCOUNT: str = "XXXXXXXX"
    BOA_ACCOUNT_HOLDER: str = "BIRUKTAWIT FIKRE"

    # Storage paths
    PDF_STORAGE_DIR: str = os.path.join(BASE_DIR, "static", "pdfs")
    IMAGE_STORAGE_DIR: str = os.path.join(BASE_DIR, "static", "images")

    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def admin_ids_list(self) -> List[int]:
        if not self.ADMIN_USER_IDS.strip():
            return []
        return [int(uid.strip()) for uid in self.ADMIN_USER_IDS.split(",") if uid.strip().isdigit()]

    @property
    def resolved_pdf_dir(self) -> str:
        if os.path.isabs(self.PDF_STORAGE_DIR):
            return self.PDF_STORAGE_DIR
        return os.path.join(BASE_DIR, self.PDF_STORAGE_DIR)

    @property
    def resolved_image_dir(self) -> str:
        if os.path.isabs(self.IMAGE_STORAGE_DIR):
            return self.IMAGE_STORAGE_DIR
        return os.path.join(BASE_DIR, self.IMAGE_STORAGE_DIR)


settings = Settings()
