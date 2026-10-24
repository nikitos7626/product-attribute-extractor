# backend/scripts/demo_real_data.py
"""
Демонстрация работы каскадного пайплайна на реальных товарах из датасета E-Commerce (sku_desc.parquet).

Запуск:
    cd backend
    python -m scripts.demo_real_data
"""
from __future__ import annotations

import json
import sys

from app.services.pipeline import CascadedExtractionPipeline

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


REAL_DATASET_CARDS = [
    {
        "id": "SKU-400030828",
        "category": "Смартфоны",
        "title": "Смартфон Samsung Galaxy A32 6/128Gb White",
        "description": (
            "Смартфон Samsung Galaxy A32 White обладает безрамочным 6,4-дюймовым дисплеем разрешением 1080х2400 пикселей, "
            "который создан по технологии SuperAMOLED. В основе девайса лежит восьмиядерный процессор MediaTek, который работает "
            "при поддержке оперативной памяти объемом 6 Гб. Объем встроенной памяти равен 128 Гб. Корпус выполнен из пластика. "
            "Аккумулятор емкостью 5000 мА*ч поддерживает быструю зарядку. Вес модели равен 184 г."
        ),
        "seller_attributes": {"brand": "Samsung", "color": "white", "rom": "128gb"},
    },
    {
        "id": "SKU-400191026",
        "category": "Ноутбуки",
        "title": "Ноутбук Lenovo IdeaPad 3 Gen7 82RK003TRU",
        "description": (
            "Ноутбук Lenovo IdeaPad 3 Gen7 82RK003TRU оборудован шестиядерным процессором Intel Core i3 1215U 1.2 ГГц. "
            "Конфигурацией устройства предусмотрено наличие экрана разрешением 1920х1080 пикселей и диагональю 15,6\". "
            "Частота обновления экрана составляет 60 Гц. Оперативный модуль для хранения данных обладает объемом 8 ГБ, "
            "объем жесткого диска — 512 ГБ."
        ),
        "seller_attributes": {},
    },
    {
        "id": "SKU-10028310",
        "category": "Телевизоры",
        "title": "Телевизор Sony KD50X85TJ",
        "description": (
            "Sony KD50X8TJ — телевизор с экраном, созданным на основе матрицы Triluminos Pro. Его диагональ — 50 дюймов, "
            "разрешение — 3840 х 2160 пикселей. Фирменный процессор X1 обеспечивает масштабирование изображения до 4K Ultra HD. "
            "В модели реализованы технологии HDR10, HLG и X-Reality Pro 1000. Мощность фронтальных динамиков — 20 Вт."
        ),
        "seller_attributes": {},
    },
    {
        "id": "SKU-20067809",
        "category": "Роботы-пылесосы",
        "title": "Робот-пылесос Mi Robot Vacuum-Mop P White (SKV4110GL)",
        "description": (
            "Робот-пылесос Mi Robot Vacuum-Mop P справится с сухой и влажной уборкой совершенно без вашего участия. "
            "Цвет корпуса: белый. Модель оснащена 11 датчиками определения препятствий. Емкий аккумулятор обеспечивает "
            "до 1 часа 50 минут непрерывной работы."
        ),
        "seller_attributes": {"color": "white"},
    },
    {
        "id": "SKU-20075598",
        "category": "Холодильники",
        "title": "Холодильник AEG RCR736E5MB",
        "description": (
            "Холодильник AEG RCR736E5MB оснащен зоной свежести объемом 22 л. Морозильная камера с тремя ящиками не требует разморозки (No Frost). "
            "Сенсорный дисплей отображает режим работы и температуру. Мощность замораживания составляет 8 кг в сутки. Цвет: черный металлик."
        ),
        "seller_attributes": {},
    },
]


def main() -> None:
    pipeline = CascadedExtractionPipeline(use_gliner=True)
    print("================================================================================")
    print(" ТЕСТИРОВАНИЕ КАСКАДНОГО ПАЙПЛАЙНА НА РЕАЛЬНЫХ ТОВАРАХ E-COMMERCE (sku_desc.parquet)")
    print("================================================================================\n")

    for card in REAL_DATASET_CARDS:
        res = pipeline.process_card(card)
        status_label = "⚠️ ТРЕБУЕТ ПРОВЕРКИ" if res["needs_review"] else "✅ ОПУБЛИКОВАНО"
        print(f"📦 [{card['id']}] {card['category']}: {card['title']}")
        print(f"   Статус: {status_label} | Общая уверенность: {res['overall_confidence'] * 100:.1f}%")
        print(f"   Незаполненные поля: {res['missing'] or 'Все закрыты (100%)'}")
        print("   Извлеченные характеристики:")
        for p in res["predictions"]:
            print(f"     • {p['attribute']:<16}: {p['value']:<22} [conf: {p['confidence']:.2f}, src: {p['source']}]")
        print("-" * 80)


if __name__ == "__main__":
    main()
