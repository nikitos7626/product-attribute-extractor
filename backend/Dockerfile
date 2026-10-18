FROM python:3.12-slim

# Оптимизация окружения Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

WORKDIR /app

# Системные зависимости для сборки C-расширений и утилит
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем манифест зависимостей
COPY backend/requirements.txt /app/requirements.txt

# Устанавливаем легковесную CPU-версию PyTorch и все зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Впекаем веса модели GLiNER в образ на этапе сборки (чтобы контейнер работал автономно без интернета)
RUN python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_multi-v2.1')"

# Копируем исходный код бэкенда и артефакты
COPY backend /app
COPY output /output
COPY output /app/output
COPY extract.py /app/extract.py

EXPOSE 8000

# Healthcheck для автоматического контроля состояния сервиса
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Запуск приложения через Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
