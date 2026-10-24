# 🎯 Отчёт верификации метрик и производительности E-Commerce

**Дата проверки:** 2026-10-23 01:45:44 MSK  
**Итоговый статус:** `✅ ВСЕ ЗАЯВЛЕННЫЕ МЕТРИКИ ПОДТВЕРЖДЕНЫ`

## 1. Сверка заявленных показателей из README.md с реальными замерами

| Показатель / Метрика | Заявлено в README | Измерено на стенде | Порог валидации | Статус | Соответствующий бейдж |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Macro-F1 Score** | 0.9889 (>= 0.98) | **1.0** | 0.98 | ✅ PASS | `Macro-F1 0.99` |
| **Category Detection Accuracy** | 100.0% | **100.0%** | >= 95.0% | ✅ PASS | `Category Accuracy 100%` |
| **Extraction Latency (Fast Mode)** | < 1.8 ms | **1.467 ms** | <= 2.50 ms | ✅ PASS | `Latency < 1.8 ms` |
| **Throughput (Cards/sec)** | > 550 cards/s | **681.2 cards/s** | >= 450 cards/s | ✅ PASS | `Throughput > 550 cards/s` |
| **Target Categories Supported** | 8 of 8 target categories | **8 categories (13 gold cards)** | >= 8 | ✅ PASS | `All 8 Target Categories` |
| **Mandatory Attributes Extracted** | 20 per-attribute metrics | **20 attributes** | >= 15 | ✅ PASS | `Per-Attribute F1` |

## 2. Детализация производительности и латентности (Throughput Benchmark)

- **Всего итераций:** 250
- **Пропускная способность (Throughput):** `681.2 карточек/сек` на 1 ядре CPU
- **Средняя латентность (Avg Latency):** `1.467 мс`
- **Медианная латентность (P50):** `1.358 мс`
- **95-й перцентиль (P95 Latency):** `2.298 мс`
- **99-й перцентиль (P99 Latency):** `2.886 мс`

## 3. Детализация точности по атрибутам (Per-Attribute Metrics)

- **Macro-F1:** `1.0`
- **Micro-F1:** `1.0`
- **Категорийная точность:** `100.0%`

| Атрибут | Precision | Recall | F1-Score | Support (эталонных карточек) |
| :--- | :---: | :---: | :---: | :---: |
| `battery` | 1.0 | 1.0 | **1.0** | 6 |
| `brand` | 1.0 | 1.0 | **1.0** | 13 |
| `cleaning_type` | 1.0 | 1.0 | **1.0** | 1 |
| `color` | 1.0 | 1.0 | **1.0** | 13 |
| `connection_type` | 1.0 | 1.0 | **1.0** | 1 |
| `cpu` | 1.0 | 1.0 | **1.0** | 5 |
| `defrost_system` | 1.0 | 1.0 | **1.0** | 1 |
| `display_tech` | 1.0 | 1.0 | **1.0** | 1 |
| `memory_ram` | 1.0 | 1.0 | **1.0** | 6 |
| `memory_rom` | 1.0 | 1.0 | **1.0** | 6 |
| `model` | 1.0 | 1.0 | **1.0** | 13 |
| `os` | 1.0 | 1.0 | **1.0** | 3 |
| `power` | 1.0 | 1.0 | **1.0** | 5 |
| `refresh_rate` | 1.0 | 1.0 | **1.0** | 6 |
| `resolution` | 1.0 | 1.0 | **1.0** | 2 |
| `screen_diagonal` | 1.0 | 1.0 | **1.0** | 8 |
| `volume` | 1.0 | 1.0 | **1.0** | 3 |
| `warranty` | 1.0 | 1.0 | **1.0** | 1 |
| `weight` | 1.0 | 1.0 | **1.0** | 7 |
| `working_time` | 1.0 | 1.0 | **1.0** | 2 |
