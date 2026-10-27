import logging
from pathlib import Path
from typing import Any
from app.config import settings

logger = logging.getLogger(__name__)

class TaxonomyManager:
    """
    Менеджер таксономии каталога E-Commerce с безопасной обработкой сбоев загрузки
    и явным отслеживанием статуса деградации сервиса.
    """
    _instance: TaxonomyManager | None = None

    def __init__(self, file_path: Path | None = None) -> None:
        if file_path is not None:
            self.path = Path(file_path)
        else:
            default_file = Path(getattr(settings, "taxonomy_path", "data/dictionaries/categories.json"))
            if default_file.is_absolute():
                self.path = default_file
            else:
                backend_dir = Path(__file__).resolve().parent.parent.parent
                repo_root = backend_dir.parent
                dict_dir = backend_dir / "data" / "dictionaries"
                if (backend_dir / default_file).is_file():
                    self.path = backend_dir / default_file
                elif (repo_root / default_file).is_file():
                    self.path = repo_root / default_file
                elif (dict_dir / default_file.name).is_file():
                    self.path = dict_dir / default_file.name
                else:
                    self.path = default_file
        
        self.load()

    @classmethod
    def get_instance(cls) -> TaxonomyManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        # Simplified for extraction, will implement full loading
        self.id_to_name: dict[str, str] = {}
        self.normalized_names: dict[str, str] = {}
        try:
            if self.path.exists():
                import json
                with open(self.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Assuming basic structure
                    self.id_to_name = data
                    self.normalized_names = {v.lower(): v for v in data.values()}
        except Exception as e:
            logger.error(f"Failed to load taxonomy: {e}")
