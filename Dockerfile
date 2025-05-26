# Použijeme Python 3.9
FROM python:3.9-slim

# Nastavíme pracovní adresář
WORKDIR /app

# Instalace systémových závislostí
RUN apt-get update && apt-get install -y \
    build-essential \
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

# Exponujeme port
ENV PORT=8080
EXPOSE 8080

# Spustíme aplikaci s gevent pro lepší DNS podporu
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 --worker-class gevent wsgi:app 