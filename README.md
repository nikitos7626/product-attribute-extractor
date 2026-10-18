# М.Видео AI · Автоматическое извлечение и валидация характеристик товаров

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tests 123 PASS](https://img.shields.io/badge/Tests-123%20PASS%20(100%25)-brightgreen.svg)](backend/tests/)
[![Throughput](https://img.shields.io/badge/Throughput->550%20cards%2Fs-blue.svg)](#-производительность)
[![Macro-F1 0.99](https://img.shields.io/badge/Macro--F1-0.99-success.svg)](output/metrics_report.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🌐 **Публичный веб-интерфейс:** [https://tochka-sborki-2026-team-059.hub.gigaschool.ru](https://tochka-sborki-2026-team-059.hub.gigaschool.ru)  
> 📑 **Интерактивная документация OpenAPI (Swagger):** [https://tochka-sborki-2026-team-059.hub.gigaschool.ru/docs](https://tochka-sborki-2026-team-059.hub.gigaschool.ru/docs)  
> ⚡ **Скорость экстракции:** `< 1.8 мс` на карточку (> 550 товаров/сек на 1 ядре CPU)

---

## 📌 Описание проекта

Промышленный сервис для автоматического структурирования и валидации характеристик товаров e-commerce каталога. Сервис принимает неструктурированный текст селлера (название, описание, технические характеристики) и извлекает нормализованные атрибуты с проверкой физической корректности.

### Поддерживаемые категории и атрибуты:
- **Смартфоны:** бренд, модель, цвет, диагональ экрана, разрешение, частота обновления (Гц), объем RAM и ROM, процессор, емкость аккумулятора (мА·ч), ОС.
- **Ноутбуки:** бренд, модель, цвет, диагональ, объем RAM и SSD/HDD, процессор, видеокарта (GPU), ОС.
- **Телевизоры:** бренд, модель, диагональ экрана, разрешение, технология матрицы (OLED/QLED/LED), Smart TV.
- **Холодильники:** бренд, модель, цвет, полезный объем, система разморозки (No Frost), габариты.
- **Пылесосы и роботы-пылесосы:** бренд, модель, тип уборки (сухая/влажная), объем пылесборника, мощность, время работы.
- **Наушники и гарнитуры:** бренд, модель, цвет, тип подключения, время автономной работы.
- **Внешние аккумуляторы (Powerbank):** бренд, модель, цвет, емкость аккумулятора (мА·ч), выходная мощность (Вт).
- **Микроволновые печи (СВЧ):** бренд, модель, цвет, внутренний объем (л), мощность микроволн (Вт).

---

## 🚀 Ключевые возможности

1. **Гибридный многоуровневый каскад:**
   - **Tier 1 (FlashText + Regex):** сверхбыстрое детерминированное ядро на алгоритме Ахо-Корасик и регулярных выражениях. Обрабатывает карточку за `< 1.8 мс` на CPU без видеокарты, закрывая свыше 95% каталога.
   - **Tier 2 (Zero-Shot NER):** легковесный экстрактивный трансформер GLiNER для извлечения редких моделей, серий и процессоров.
   - **Tier 3.5 (Catalog KB):** база знаний на 9 700+ верифицированных моделей каталога для восполнения пропущенных селлером характеристик.
   - **Tier 3.8 (LLM Fallback):** точечное подключение языковых моделей с предохранителем `Circuit Breaker` и проверкой заземления фактов (`GroundingVerifier`).
2. **100% экстрактивность и защита от галлюцинаций:**
   - Значения атрибутов извлекаются строго из текста оффера или верифицированной заводской базы. Модель не додумывает несуществующие характеристики.
3. **Физическая валидация (Sanity Gate):**
   - Проверка физических диапазонов (смартфон не может иметь экран 65" или батарею 100 000 мА·ч).
   - Строгие белые списки атрибутов по категориям (в холодильниках исключена ОС, а в микроволновках — видеокарта).
4. **Контроль качества (Human-in-the-Loop):**
   - Расчет уверенности (`confidence`) для каждого атрибута.
   - Карточки с нехваткой ключевых данных или спорными значениями автоматически маркируются `needs_review: true` и отправляются контент-модераторам.
5. **Пакетная обработка и экспорт:**
   - Поддержка форматов JSON и CSV через веб-интерфейс, REST API и командную строку (CLI).

---

## ⚡ Быстрый старт

### 1. Установка зависимостей
```bash
git clone https://github.com/nikitos7626/product-attribute-extractor.git
cd product-attribute-extractor
pip install -r requirements.txt
```

### 2. Запуск сервиса
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```
- Веб-интерфейс: `http://localhost:8000`
- Swagger UI документация: `http://localhost:8000/docs`

### 3. Запуск через Docker
```bash
docker compose up -d
```

### 4. Консольная утилита (CLI)
```bash
# Извлечение из одной строки:
python extract.py "Смартфон Xiaomi Redmi Note 13 8/256GB Black 5000mAh AMOLED 120Hz"

# Пакетная обработка файла с экспортом в JSON и CSV:
python scripts/export_predictions.py --input data/sample_cards.json --format both
```

---

## 📡 Основные эндпоинты API

| Метод | Путь | Описание |
| :--- | :--- | :--- |
| `POST` | `/extract` | Основной эндпоинт извлечения характеристик (карточка $\to$ атрибуты) |
| `POST` | `/api/extract` | Канонический REST-эндпоинт с расширенным ответом и метриками уверенности |
| `POST` | `/api/extract/batch` | Пакетная обработка списка карточек товаров |
| `POST` | `/api/extract/export` | Пакетный экспорт в стандартизированные файлы `predictions.json` / `predictions.csv` |
| `GET` | `/api/extract/taxonomy`| Схемы категорий, обязательные атрибуты и белые списки |
| `POST` | `/api/extract/brands/register` | Динамическое добавление нового бренда в словарь без перезапуска |
| `GET` | `/api/info` | Служебная информация о сервисе и активных компонентах |
| `GET` | `/docs` | Интерактивная документация Swagger UI |

---

## 🧪 Тестирование
 
Запуск полного набора unit- и интеграционных тестов (123 теста, 100% green):
```bash
pytest backend/tests
```

---

## 📊 Воспроизводимость артефактов кейса М.Видео

Все обязательные артефакты кейса воспроизводятся в одну команду:

```bash
# 1. Расчёт Per-Attribute метрик качества (Precision, Recall, F1) на Gold Benchmark:
python scripts/evaluate_metrics.py
# Результат сохраняется в output/metrics_report.md и output/metrics_report.json (Macro-F1 = 0.9889)

# 2. Пакетная выгрузка стандартизированных предсказаний в JSON и CSV (900 карточек):
python scripts/export_predictions.py --format both
# Результат сохраняется в output/predictions.json и output/predictions.csv

# 3. Разведочный анализ данных (EDA) по каталогу М.Видео (546 000 товаров):
python scripts/eda_analysis.py
# Отчёт в output/eda_report.md, интерактивный ноутбук: notebooks/eda_mvideo_dataset.ipynb

# 4. Динамическая валидация случайного среза реальных карточек М.Видео:
python scripts/evaluate_catalog_sample.py --size 10
```

### Комплект обязательных артефактов кейса:
1. **Код решения:** директория `backend/` с реализацией многоуровневого пайплайна (Tier 1 rules + Tier 2 GLiNER NER + Tier 3 LLM fallback).
2. **README:** подробная инструкция по установке, запуску, эндпоинтам и тестированию.
3. **Разведочный анализ (EDA):** `notebooks/eda_mvideo_dataset.ipynb`, `scripts/eda_analysis.py`, `output/eda_report.md`.
4. **Пайплайн извлечения:** `backend/app/services/pipeline.py` и REST API `/api/extract`.
5. **Файлы предсказаний:** `output/predictions.json`, `output/predictions.csv`.
6. **Калибровка уверенности и защита от галлюцинаций:**
   - Температурное масштабирование ($T=1.25$, Platt Scaling для логитов нейросети).
   - Многоисточниковый байесовский консенсус (Snorkel Weak Supervision).
   - Степенной штраф за неполноту карточки $(found / total)^{1.5} \to needs\_review = true$.
   - Программный Guardrail против галлюцинаций `_verify_grounding()` и физический валидатор `AttributeSanityValidator`.

---

## 👥 Команда
**Точка сборки (`team-059`)** · М.Видео · VolgaDev 2026
