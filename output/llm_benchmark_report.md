# Сравнительный отчёт качества LLM Fallback (М.Видео AI)

**Дата генерации:** 2026-10-21 20:17:10
**Количество тестовых карточек:** 8 (смартфоны, ноутбуки, ТВ, техника)
**Условие тестирования:** Каталог моделей М.Видео (Tier 2.5) отключен, характеристики восполняются моделью из знаний о товаре.

## Сводная таблица сравнения моделей

| Модель | Ср. Задержка (мс) | Валидность JSON | Точность атрибутов | Sanity Pass | Оценка |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **GigaChat/GigaChat-3-Pro** | 726.2 мс | 50.0% | 35.7% (5/14) | 50.0% | 🥇 ЛУЧШАЯ |
| **ai-sage/GigaChat3-10B-A1.8B** | 515.0 мс | 100.0% | 57.1% (8/14) | 100.0% | 🥇 ЛУЧШАЯ |
| **openai/gpt-oss-120b** | 2573.3 мс | 100.0% | 57.1% (8/14) | 100.0% | Стандарт |
| **Qwen/Qwen3.6-35B-A3B** | 8569.3 мс | 100.0% | 57.1% (8/14) | 100.0% | Стандарт |

## Подробные результаты по карточкам

### Модель: `GigaChat/GigaChat-3-Pro`

| Карточка | Целевые атрибуты | Ответ модели | Совпадение | Время |
| :--- | :--- | :--- | :--- | :---: |
| Смартфон Apple iPhone 15 Pro Max 256GB с... | battery, screen_diagonal | *ничего* | 0/2 | 734.7 мс |
| Смартфон Samsung Galaxy S24 Ultra 12/512... | battery, screen_diagonal | screen_diagonal: 6.8" | 1/2 | 821.0 мс |
| Смартфон Xiaomi Redmi Note 13 8/256GB Bl... | battery, screen_diagonal | *ничего* | 0/2 | 698.8 мс |
| Ноутбук Apple MacBook Air 13 M3/8/256GB ... | cpu, screen_diagonal | cpu: Apple M3, screen_diagonal: 13.6" | 2/2 | 825.0 мс |
| Холодильник Haier C2F637CFMV No Frost се... | volume | *ничего* | 0/1 | 586.3 мс |
| Вертикальный пылесос Dyson V15 Detect Ab... | volume, power | *ничего* | 0/2 | 658.4 мс |
| Микроволновая печь Gorenje MO20E1W белый... | volume, power | volume: 20 л, power: 700 Вт | 1/2 | 778.3 мс |
| Беспроводные наушники Sony WH-1000XM5 че... | working_time | working_time: 30 ч | 1/1 | 707.1 мс |

### Модель: `ai-sage/GigaChat3-10B-A1.8B`

| Карточка | Целевые атрибуты | Ответ модели | Совпадение | Время |
| :--- | :--- | :--- | :--- | :---: |
| Смартфон Apple iPhone 15 Pro Max 256GB с... | battery, screen_diagonal | battery: 4352 мАч, screen_diagonal: 6.1" | 0/2 | 666.1 мс |
| Смартфон Samsung Galaxy S24 Ultra 12/512... | battery, screen_diagonal | battery: 5000 мАч, screen_diagonal: 6.8" | 2/2 | 486.1 мс |
| Смартфон Xiaomi Redmi Note 13 8/256GB Bl... | battery, screen_diagonal | battery: 5000 мАч, screen_diagonal: 6.67" | 2/2 | 547.5 мс |
| Ноутбук Apple MacBook Air 13 M3/8/256GB ... | cpu, screen_diagonal | cpu: Apple M3, screen_diagonal: 13.3" | 1/2 | 503.2 мс |
| Холодильник Haier C2F637CFMV No Frost се... | volume | volume: 360 л | 0/1 | 476.2 мс |
| Вертикальный пылесос Dyson V15 Detect Ab... | volume, power | volume: 38.5 дБ, power: 215 Вт | 0/2 | 495.6 мс |
| Микроволновая печь Gorenje MO20E1W белый... | volume, power | volume: 20 литров, power: 800 Вт | 2/2 | 476.7 мс |
| Беспроводные наушники Sony WH-1000XM5 че... | working_time | working_time: 30 часов | 1/1 | 468.5 мс |

### Модель: `openai/gpt-oss-120b`

| Карточка | Целевые атрибуты | Ответ модели | Совпадение | Время |
| :--- | :--- | :--- | :--- | :---: |
| Смартфон Apple iPhone 15 Pro Max 256GB с... | battery, screen_diagonal | battery: 4352 мАч, screen_diagonal: 6.1" | 0/2 | 6692.2 мс |
| Смартфон Samsung Galaxy S24 Ultra 12/512... | battery, screen_diagonal | battery: 5000 мАч, screen_diagonal: 6.8" | 2/2 | 1249.7 мс |
| Смартфон Xiaomi Redmi Note 13 8/256GB Bl... | battery, screen_diagonal | battery: 5000 мАч, screen_diagonal: 6.67" | 2/2 | 1348.4 мс |
| Ноутбук Apple MacBook Air 13 M3/8/256GB ... | cpu, screen_diagonal | cpu: Apple M3, screen_diagonal: 13.6" | 2/2 | 1509.2 мс |
| Холодильник Haier C2F637CFMV No Frost се... | volume | volume: 363 л | 0/1 | 1366.9 мс |
| Вертикальный пылесос Dyson V15 Detect Ab... | volume, power | volume: 0.76 л, power: 600 Вт | 0/2 | 5981.7 мс |
| Микроволновая печь Gorenje MO20E1W белый... | volume, power | volume: 20 л, power: 800 Вт | 2/2 | 1190.0 мс |
| Беспроводные наушники Sony WH-1000XM5 че... | working_time | working_time: 30 ч | 0/1 | 1248.2 мс |

### Модель: `Qwen/Qwen3.6-35B-A3B`

| Карточка | Целевые атрибуты | Ответ модели | Совпадение | Время |
| :--- | :--- | :--- | :--- | :---: |
| Смартфон Apple iPhone 15 Pro Max 256GB с... | battery, screen_diagonal | battery: 3687 мАч, screen_diagonal: 6.1" | 0/2 | 8185.1 мс |
| Смартфон Samsung Galaxy S24 Ultra 12/512... | battery, screen_diagonal | battery: 5000 мАч, screen_diagonal: 6.8" | 2/2 | 8769.8 мс |
| Смартфон Xiaomi Redmi Note 13 8/256GB Bl... | battery, screen_diagonal | battery: 5000 мАч, screen_diagonal: 6.67" | 2/2 | 8584.1 мс |
| Ноутбук Apple MacBook Air 13 M3/8/256GB ... | cpu, screen_diagonal | cpu: Apple M3, screen_diagonal: 13.3" | 1/2 | 8728.8 мс |
| Холодильник Haier C2F637CFMV No Frost се... | volume | volume: 360 л | 0/1 | 8653.6 мс |
| Вертикальный пылесос Dyson V15 Detect Ab... | volume, power | volume: 38.5 дБ, power: 215 Вт | 0/2 | 8543.1 мс |
| Микроволновая печь Gorenje MO20E1W белый... | volume, power | volume: 20 л, power: 800 Вт | 2/2 | 8849.0 мс |
| Беспроводные наушники Sony WH-1000XM5 че... | working_time | working_time: 30 часов | 1/1 | 8240.5 мс |
