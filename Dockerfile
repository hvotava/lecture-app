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
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Exponujeme port (Railway automaticky nastaví PORT proměnnou)
EXPOSE 8000

# Shell form pro env variable expansion
CMD sh -c 'uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level warning'