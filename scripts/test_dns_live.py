import json
import os
import sys

# Настройка UTF-8 для вывода в консоль Windows
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Подключаем backend нашего пайплайна
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dns_shop_mcp import server
from app.services.pipeline import CascadedExtractionPipeline

QUERIES = [
    "смартфон Xiaomi Poco X6 Pro",
    "ноутбук Apple MacBook Air 13",
    "робот-пылесос Dreame D9 Max",
    "телевизор LG 55 OLED",
    "холодильник Haier No Frost",
]

def unwrap_mcp_result(res):
    if hasattr(res, "content") and res.content:
        first = res.content[0]
        if hasattr(first, "text"):
            return json.loads(first.text)
    if isinstance(res, str):
        return json.loads(res)
    return res

def main():
    print("=" * 80)
    print("🌐 ИНТЕГРАЦИОННОЕ ТЕСТИРОВАНИЕ: DNS-SHOP → М.ВИДЕО EXTRACTION PIPELINE")
    print("=" * 80)
    
    pipeline = CascadedExtractionPipeline(use_gliner=True, use_llm=False)
    
    for q in QUERIES:
        print(f"\n" + "-" * 80)
        print(f"🔎 ПОИСК В DNS: '{q}'")
        print("-" * 80)
        
        try:
            search_res = unwrap_mcp_result(server.search_products(query=q, page=1))
            items = search_res.get("items", [])
            if not items:
                print("❌ Товары не найдены в DNS")
                continue
                
            top_item = items[0]
            code = top_item.get("code")
            dns_title = top_item.get("name")
            dns_url = top_item.get("url")
            print(f"📦 Найден товар: {dns_title}")
            print(f"   Код DNS: {code} | URL: {dns_url}")
            
            # Получаем полные данные карточки товара (включая текстовое описание и характеристики)
            print(f"   Загрузка полной карточки товара (get_product)...")
            prod_res = unwrap_mcp_result(server.get_product(product=str(code), include_characteristics=True))
            
            description = prod_res.get("description") or top_item.get("short_specs") or ""
            chars = prod_res.get("characteristics") or {}
            
            # Собираем реальный текст, как если бы продавец заполнил карточку
            combined_text = f"{dns_title}\n\n{description}".strip()
            
            print(f"\n📝 ИСХОДНОЕ ТЕКСТОВОЕ ОПИСАНИЕ ИЗ DNS:")
            preview = (description[:300] + "...") if len(description) > 300 else description
            print(f"   {preview}\n")
            
            # Прогоняем через наш пайплайн извлечения атрибутов
            extraction = pipeline.process_card({
                "external_id": f"dns-{code}",
                "title": dns_title,
                "description": description,
                "raw_text": combined_text,
            })
            
            print(f"🤖 РЕЗУЛЬТАТ ПАЙПЛАЙНА М.ВИДЕО:")
            print(f"   Категория:          {extraction.get('category')}")
            print(f"   Общая уверенность:  {extraction.get('overall_confidence'):.1%}")
            needs_review = extraction.get('needs_review')
            status_badge = "⚠️ ТРЕБУЕТ ПРОВЕРКИ (HITL)" if needs_review else "✅ АВТОПУБЛИКАЦИЯ"
            print(f"   Статус публикации:  {status_badge}")
            if extraction.get('missing'):
                print(f"   Недостающие поля:   {', '.join(extraction.get('missing'))}")
                
            print(f"\n   📋 ИЗВЛЕЧЁННЫЕ АТРИБУТЫ:")
            for p in extraction.get("predictions", []):
                tier_str = p.get('source', '')
                print(f"     • {p['attribute']:<18} : {p['value']:<25} | {p['confidence']:.0%} [{tier_str}] (спан: '{p.get('raw', '')}')")
                
        except Exception as e:
            print(f"❌ Ошибка при обработке '{q}': {type(e).__name__}: {e}")

    print("\n" + "=" * 80)
    print("✅ ТЕСТИРОВАНИЕ НА РЕАЛЬНЫХ ДАННЫХ DNS-SHOP ЗАВЕРШЕНО")
    print("=" * 80)

if __name__ == "__main__":
    main()
