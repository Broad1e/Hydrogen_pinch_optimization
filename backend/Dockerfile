# Сборка: Установка зависимостей
FROM python:3.11-slim as builder

# Установка системных зависимостей для сборки psycopg2
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Установка Poetry
RUN pip install --no-cache-dir poetry==1.8.3

WORKDIR /app

# Копируем только файлы управления зависимостями
COPY pyproject.toml poetry.lock* ./

# Отключаем виртуальные окружения и устанавливаем зависимости
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

# Финальный образ: Легкий и безопасный (без gcc)
FROM python:3.11-slim

# Нужен libpq для psycopg2 (runtime)
RUN apt-get update && apt-get install -y libpq-dev curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем установленные пакеты из builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Копируем исходный код
COPY . .

# Открываем порт
EXPOSE 8000

# Запуск Uvicorn (FastAPI)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]