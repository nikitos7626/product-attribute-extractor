"""
Скрипт выборки реальных товарных карточек из полного каталога М.Видео (skus.pkl).
Формирует репрезентативный датасет data/sample_cards.json по всем ключевым категориям
для масштабного стресс-тестирования, бенчмаркинга и пакетного экспорта предсказаний.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PKL_CANDIDATES = [
    Path(r"c:\Users\nikit\Downloads\cu_ws\skus.pkl"),
    REPO_ROOT / "data" / "skus.pkl",
    Path("skus.pkl"),
]


def find_skus_pkl() -> Path | None:
    for p in PKL_CANDIDATES:
        if p.exists():
            return p
    return None


def main(limit_per_category: int = 150) -> None:
    pkl_path = find_skus_pkl()
    if not pkl_path:
        print("[!] Файл skus.pkl не найден в локальных путях.")
        return

    print(f"📦 Загрузка каталога из {pkl_path}...")
    with open(pkl_path, "rb") as f:
        data = pickle.load(f)

    offers = data["yml_catalog"]["shop"]["offers"]["offer"]
    categories = data["yml_catalog"]["shop"]["categories"]["category"]
    cat_map = {c["@id"]: c["#text"] for c in categories}

    target_cats = {
        "Смартфоны": "smartphones",
        "Ноутбуки": "laptops",
        "Телевизоры": "tvs",
        "Встраиваемый телевизор": "tvs",
        "Роботы-пылесосы": "vacuum_cleaners",
        "Пылесосы напольные": "vacuum_cleaners",
        "Пылесосы вертикальные": "vacuum_cleaners",
        "Холодильники": "refrigerators",
        "Встраиваемые холодильники": "refrigerators",
        "Наушники": "headphones",
        "Наушники игровые True Wireless": "headphones",
        "Наушники для компьютеров": "headphones",
    }

    selected = []
    cat_counts: dict[str, int] = {}

    for o in offers:
        cats = o.get("categories")
        cid = cats.get("categoryId") if isinstance(cats, dict) else None
        cname = cat_map.get(cid, "")
        if cname in target_cats:
            cat_key = target_cats[cname]
            cnt = cat_counts.get(cat_key, 0)
            if cnt < limit_per_category:
                name = (o.get("name") or "").strip()
                if len(name) >= 15:
                    oid = o.get("@id", f"gen-{len(selected)}")
                    selected.append({
                        "external_id": f"mvideo-{oid}",
                        "title": name,
                        "category": cname,
                        "vendor": o.get("vendor"),
                        "description": "",
                    })
                    cat_counts[cat_key] = cnt + 1

    print("📊 Отобрано карточек по категориям каталога:")
    for k, v in sorted(cat_counts.items()):
        print(f"  • {k}: {v} шт.")
    print(f"Всего отобрано реальных карточек: {len(selected)}")

    out_path = REPO_ROOT / "data" / "sample_cards.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)

    print(f"✅ Сохранено в {out_path}")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    main(limit)
