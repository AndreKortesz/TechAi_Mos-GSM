FROM python:3.11-slim

# Установка системных зависимостей для WeasyPrint
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Порт по умолчанию
ENV PORT=8000
EXPOSE 8000

# Запуск - Python сам получит PORT из окружения
CMD ["python", "-c", "import os; import subprocess; port = os.environ.get('PORT', '8000'); subprocess.run(['uvicorn', 'server:app', '--host', '0.0.0.0', '--port', port])"]
