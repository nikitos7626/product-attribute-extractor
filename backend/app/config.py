from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Конфигурация сервиса извлечения характеристик товаров М.Видео AI.
    Все параметры могут быть переопределены через переменные окружения или .env файл.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Каскадный пайплайн (Tier 1 FlashText/Regex + Tier 2 GLiNER NER)
    extractor: str = "cascade"           # cascade | regex | gliner
    confidence_threshold: float = 0.87   # порог уверенности (ниже — флаг needs_review=True)
    gliner_threshold: float = 0.30       # порог вероятности сущностей в GLiNER

    # CORS (разрешенные источники веб-интерфейса)
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:8000"

    # LLM fallback (GigaSchool API)
    llm_api_base: str = "https://hub.gigaschool.ru/api/v1/llm/v1"
    llm_api_key: str = "hub-FozIDkycOQoaEHbYj7Qvq0Xl9PsZDJs-0_V_LmSVg1c"
    llm_model: str = "Qwen/Qwen3-Coder-Next"
    enforce_llm_grounding: bool = False



    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()