# Použijeme Python 3.11 pro lepší kompatibilitu
FROM python:3.11-slim

# Nastavíme pracovní adresář
WORKDIR /app

# Instalace systémových závislostí
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Zkopírujeme requirements.txt
COPY requirements.txt .

# Nainstalujeme závislosti
RUN pip install --no-cache-dir -r requirements.txt

# Zkopírujeme zbytek aplikace
COPY . .

# Nastavíme proměnné prostředí
ENV FLASK_APP=wsgi:app
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Exponujeme port (Railway automaticky nastaví PORT proměnnou)
EXPOSE 8080

# Spustíme aplikaci s více logováním
CMD sh -c 'echo "=== STARTING APPLICATION ===" && \
    echo "PORT: ${PORT:-8080}" && \
    echo "PWD: $(pwd)" && \
    echo "Files in current directory:" && \
    ls -la && \
    echo "=== STARTING UVICORN ===" && \
    uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --log-level debug'