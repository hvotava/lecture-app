# Instrukce pro nasazení aplikace

## 1. Railway.app (WebSocket podporováno)

### Manuální nasazení:
1. Otevřete https://railway.app/dashboard
2. Vyberte projekt "lecture-app"
3. Klikněte "New Service" → "Empty Service"
4. Nahrajte kód nebo připojte GitHub repo
5. Nastavte environment variables z `railway-env-example.txt`

### Environment Variables pro Railway:
```
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your_secret_key_here
OPENAI_API_KEY=your_openai_api_key_here
TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
DATABASE_URL=postgresql://... (automaticky)
WEBHOOK_BASE_URL=https://your-app.up.railway.app
```

## 2. Render.com (doporučeno pro WebSocket)

### Nasazení:
1. Jděte na https://render.com
2. Připojte GitHub repo nebo nahrajte kód
3. Vyberte "Web Service"
4. Použijte tyto nastavení:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn --worker-class gevent --workers 1 --bind 0.0.0.0:$PORT wsgi:app`
   - Python Version: 3.11

### Environment Variables pro Render:
```
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your_secret_key_here
OPENAI_API_KEY=your_openai_api_key_here
TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
DATABASE_URL=postgresql://... (přidejte PostgreSQL addon)
WEBHOOK_BASE_URL=https://your-app.onrender.com
```

## 3. Heroku (alternativa)

### Nasazení:
1. Nainstalujte Heroku CLI
2. `heroku create lecture-app`
3. `git push heroku main`
4. Přidejte PostgreSQL addon: `heroku addons:create heroku-postgresql:hobby-dev`

## Soubory pro nasazení:
- `requirements.txt` - Python dependencies
- `Procfile` - Start command
- `wsgi.py` - WSGI entry point
- `railway.json` - Railway konfigurace
- `render.yaml` - Render konfigurace

## Po nasazení:
1. Nastavte webhook URL v Twilio konzoli
2. Otestujte health endpoint: `/health`
3. Otestujte voice endpoint: `/voice/` 