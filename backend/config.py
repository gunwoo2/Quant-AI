from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    DB_HOST: str     = os.getenv("DB_HOST", "localhost")
    DB_PORT: int     = int(os.getenv("DB_PORT", 5432))
    DB_NAME: str     = os.getenv("DB_NAME", "quantai")
    DB_USER: str     = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # ── 한국투자증권 API ──
    KIS_APP_KEY:    str = os.getenv("KIS_APP_KEY", "")
    KIS_APP_SECRET: str = os.getenv("KIS_APP_SECRET", "")
    KIS_BASE_URL:   str = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")

    # ── External APIs ──
    FMP_API_KEY:    str = os.getenv("FMP_API_KEY", "")
    NEWS_API_KEY:   str = os.getenv("NEWS_API_KEY", "")
    FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")

    @property
    def DSN(self) -> str:
        return (
            f"host={self.DB_HOST} port={self.DB_PORT} "
            f"dbname={self.DB_NAME} user={self.DB_USER} "
            f"password={self.DB_PASSWORD}"
        )

settings = Settings()
