from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Default path to Delhi wards GeoPackage (relative to this file: api/app/core -> testing/backend_tests)
BASE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_GPKG = BASE_DIR / "data" / "delhi_wards.gpkg"


class Settings(BaseSettings):
    PROJECT_NAME: str = "CivicCare API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    SECRET_KEY: str = "super_secret_temporary_key_for_development_replace_in_prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/civiccare"

    # Path to Delhi wards GeoPackage for ward-from-location lookup (empty = disabled)
    DELHI_WARDS_GPKG_PATH: str = ""

    @property
    def delhi_wards_gpkg_path(self) -> Path | None:
        if self.DELHI_WARDS_GPKG_PATH:
            p = Path(self.DELHI_WARDS_GPKG_PATH)
            return p if p.is_absolute() else (Path.cwd() / p).resolve()
        if _DEFAULT_GPKG.exists():
            return _DEFAULT_GPKG
        return None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
