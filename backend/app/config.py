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

    # Флаги активности уровней каскада
    use_gliner: bool = True
    use_catalog_enricher: bool = True
    use_llm: bool = True

    # CORS (разрешенные источники веб-интерфейса)
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:8000"

    # Безопасность и авторизация API (если задан, эндпойнты требуют заголовок X-API-Key или Bearer токен)
    api_key: str = ""

    # LLM fallback (GigaSchool API / OpenAI-совместимый эндпоинт)
    # Ключи и секреты НИКОГДА не зашиваются в код и передаются через окружение
    llm_api_base: str = "https://hub.gigaschool.ru/api/v1/llm/v1"
    llm_api_key: str = ""
    llm_model: str = "GigaChat/GigaChat-3-Pro"
    enforce_llm_grounding: bool = True
    llm_timeout_seconds: float = 3.5

    # Предохранитель Circuit Breaker для внешних сервисов
    circuit_breaker_max_failures: int = 3
    circuit_breaker_cooldown_seconds: float = 60.0

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()