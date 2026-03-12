from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    DB_HOST: str     = os.getenv("DB_HOST", "localhost")
    DB_PORT: int     = int(os.getenv("DB_PORT", 5432))
    DB_NAME: str     = os.getenv("DB_NAME", "quantai")
    DB_USER: str     = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")  # .env의 DB_PASSWORD 읽기

    @property
    def DSN(self) -> str:
        return (
            f"host={self.DB_HOST} port={self.DB_PORT} "
            f"dbname={self.DB_NAME} user={self.DB_USER} "
            f"password={self.DB_PASSWORD}"
        )

settings = Settings()
