from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # MongoDB
    mongodb_url: str
    db_name: str = "insurancezone"

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Google Sheets
    google_sheets_url: str = ""

    # Geo-fence
    office_lat: float = 25.5747
    office_lng: float = 83.5718
    office_radius_meters: float = 200.0

    # App
    allowed_origins: str = "http://localhost:3000"
    app_env: str = "development"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()