from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_EXPIRE_HOURS: int = 12
    UPLOAD_DIR: str = "/home/hipo/app/uploads"
    MAX_UPLOAD_MB: int = 50
    ENVIRONMENT: str = "production"

    class Config:
        env_file = ".env"

settings = Settings()
