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
    fast_mode: bool = False              # Быстрый/автономный режим (без тяжелых внешних нейросетей GLiNER/LLM)

    # Гиперпараметры калибровки уверенности (Platt scaling & Snorkel consensus)
    gliner_temperature: float = 1.25
    catalog_kb_version: str = "1.4.0"
    catalog_kb_path: str = "data/dictionaries/catalog_models_kb.json"
    brands_csv_path: str = "data/dictionaries/brands.csv"

    # CORS (разрешенные источники веб-интерфейса)
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:8000"

    # Окружение развертывания и безопасность (development | test | production)
    environment: str = "development"

    # Безопасность и авторизация API (если задан, эндпойнты требуют заголовок X-API-Key или Bearer токен)
    api_key: str = ""

    # LLM fallback (GigaSchool API / OpenAI-совместимый эндпоинт)
    # Ключи и секреты НИКОГДА не зашиваются в код и передаются через окружение
    llm_api_base: str = "https://hub.gigaschool.ru/api/v1/llm/v1"
    llm_api_key: str = ""
    llm_model: str = "ai-sage/GigaChat3-10B-A1.8B"
    llm_pro_model: str = "GigaChat/GigaChat-3-Pro"
    enforce_llm_grounding: bool = True
    llm_timeout_seconds: float = 3.5
    llm_max_retries: int = 2
    llm_retry_backoff_factor: float = 0.2

    # Предохранитель Circuit Breaker для внешних сервисов
    circuit_breaker_max_failures: int = 3
    circuit_breaker_cooldown_seconds: float = 60.0

    # Априорные веса надежности источников (Confidence Calibrator Priors)
    prior_catalog_kb: float = 0.94
    prior_flashtext: float = 0.95
    prior_rule_subbrand: float = 0.96
    prior_regex_bounded: float = 0.93
    prior_regex: float = 0.90
    prior_gliner: float = 0.88
    prior_llm_grounded: float = 0.86
    force_review_on_llm: bool = True     # Строгий контроль качества: при использовании LLM всегда отправлять на проверку человеку
    prior_default: float = 0.75

    # Гиперпараметры калибратора уверенности и многоисточникового консенсуса
    calibrator_title_bonus: float = 0.03
    consensus_conflict_penalty: float = 0.12
    consensus_min_confidence: float = 0.40
    card_required_attrs_weight: float = 0.80
    card_optional_attrs_weight: float = 0.20
    completeness_penalty_power: float = 1.5
    gliner_weight_prior: float = 0.40
    gliner_weight_prob: float = 0.60
    regex_title_bonus: float = 0.03

    # Таксономия каталога М.Видео
    taxonomy_path: str = "data/dictionaries/mvideo_categories.json"

    # Лимиты пакетной обработки (Batch Processing Limits)
    max_batch_file_size_bytes: int = 50 * 1024 * 1024  # 50 МБ
    max_batch_items: int = 10000

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()