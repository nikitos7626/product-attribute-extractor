import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import settings
from app.extractors.llm_extractor import StrictLlmFallbackExtractor

sys.stdout.reconfigure(encoding="utf-8")

def run_hallucination_models():
    print("=" * 80)
    print("ЭКСПЕРИМЕНТ: ПРЯМАЯ ПРОВОКАЦИЯ LLM НА ВЫДУМЫВАНИЕ ХАРАКТЕРИСТИК")
    print("Проверяем, как разные модели реагируют на вымышленный товар без характеристик:")
    print("Товар: 'Смартфон Zorgon Blaster X1000 новый в коробке, супер новинка этого года'")
    print("Запрос к LLM: заполнить missing_attrs: battery, screen_diagonal, memory_ram, memory_rom, color")
    print("=" * 80)

    models_to_test = [
        ("GigaChat 10B (базовая)", "ai-sage/GigaChat3-10B-A1.8B"),
        ("GigaChat 3 Pro (мощная)", "GigaChat/GigaChat-3-Pro"),
        ("GPT-OSS 120B (сверхмощная)", "openai/gpt-oss-120b"),
    ]

    provocation_text = "Смартфон Zorgon Blaster X1000 новый в коробке, супер новинка этого года"
    missing = {"battery", "screen_diagonal", "memory_ram", "memory_rom", "color"}

    for label, model_name in models_to_test:
        print(f"\n>>> [{label} -> {model_name}] <<<")
        extractor = StrictLlmFallbackExtractor(
            api_key=settings.llm_api_key,
            api_base=settings.llm_api_base,
            model=model_name,
            enforce_grounding=True,
            timeout=10.0
        )

        system_prompt = (
            "Ты — эксперт по спецификациям каталога М.Видео. "
            "Твоя задача — определить официальные заводские характеристики для указанной модели техники. "
            "Если параметр не упомянут в тексте продавца, укажи точные справочные спецификации производителя для этой конкретной модели. "
            "Категорически запрещено выдумывать случайные числа. Если модель неизвестна — верни null. "
            "Ответ строго в формате JSON без разметки markdown."
        )
        user_prompt = (
            f"Товар: Zorgon Blaster X1000\n"
            f"Описание продавца: {provocation_text}\n"
            f"Заполни ТОЛЬКО следующие недостающие параметры: {sorted(list(missing))}\n"
            f"Формат: JSON-объект, где ключи — названия параметров, а значения — строки с физическими единицами или null."
        )

        # 1. Сырой запрос: что модель ответила
        raw_json_str = extractor._call_llm(system_prompt, user_prompt)
        print(f"  Сырой ответ модели: {raw_json_str}")

        # 2. Вызов через боевой метод enrich_missing_attributes
        predictions = extractor.enrich_missing_attributes(
            brand="Zorgon",
            model="Blaster X1000",
            missing_attrs=missing,
            category_key="smartphones",
            raw_text=provocation_text
        )

        passed_count = len(predictions)
        print(f"  Прошло в итоговый каталог: {passed_count} из {len(missing)}")
        if passed_count == 0:
            print("  🛡️ РЕЗУЛЬТАТ: 100% ВЫДУМАННЫХ ПАРАМЕТРОВ ЗАБЛОКИРОВАНО СИСТЕМОЙ GROUNDING & SANITY!")
        else:
            for p in predictions:
                print(f"    • [ПРОПУЩЕНО В КАТАЛОГ!] {p.attribute}: {p.value}")

if __name__ == "__main__":
    run_hallucination_models()
