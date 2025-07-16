# 🚂 Railway Deployment Guide

## Rychlý start

1. **Jděte na [railway.app](https://railway.app)**
2. **Klikněte "Start a New Project"**
3. **Vyberte "Deploy from GitHub repo"**
4. **Připojte repository: `hvotava/lecture-app`**

## Environment Variables

V Railway dashboardu přidejte tyto proměnné:

### Základní konfigurace
```
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your-very-secure-secret-key-minimum-32-chars
PORT=8080
```

### Twilio konfigurace
```
TWILIO_ACCOUNT_SID=your-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_PHONE_NUMBER=your-twilio-phone-number
TWILIO_ASSISTANT_ID=your-twilio-assistant-id
```

### OpenAI konfigurace
```
OPENAI_API_KEY=your-openai-api-key
```

### Aplikační konfigurace
```
WEBSOCKET_ENABLED=true
WEBHOOK_BASE_URL=https://your-app-name.up.railway.app
DATABASE_URL=postgresql://user:password@host:port/database
LOG_LEVEL=INFO
RAILWAY_ENVIRONMENT=production
```

## Automatické nastavení

Railway automaticky:
- ✅ Detekuje `requirements.txt`
- ✅ Nainstaluje Python dependencies
- ✅ Použije `railway.json` pro konfiguraci
- ✅ Přiřadí doménu (např. `your-app.up.railway.app`)

## Po deploymenu

1. **Zkopírujte URL vaší aplikace**
2. **Aktualizujte `WEBHOOK_BASE_URL`** na skutečnou URL
3. **Nastavte Twilio webhook** na `https://your-app.up.railway.app/voice`
4. **Testujte health check** na `https://your-app.up.railway.app/health`
5. **Testujte aplikaci** zavoláním na Twilio číslo

## Monitoring

- Railway poskytuje automatické logy
- Můžete sledovat metriky v dashboardu
- Aplikace se automaticky restartuje při chybách
- Health check endpoint: `/health`

## Troubleshooting

Pokud deployment selže:

### 1. Zkontrolujte logy v Railway dashboardu
- Jděte do vašeho projektu
- Klikněte na "Deployments"
- Vyberte nejnovější deployment
- Zkontrolujte "Build Logs" a "Deploy Logs"

### 2. Ověřte environment variables
- Všechny povinné proměnné musí být nastavené
- SECRET_KEY musí mít alespoň 32 znaků
- DATABASE_URL musí být platná PostgreSQL URL

### 3. Zkontrolujte dependencies
- Všechny balíčky v `requirements.txt` musí být kompatibilní
- Gevent a gunicorn jsou správně nakonfigurovány

### 4. Časté problémy
- **Port binding error**: Zkontrolujte, že používáte `$PORT` proměnnou
- **Import error**: Zkontrolujte, že všechny moduly existují
- **Database connection**: Ověřte DATABASE_URL
- **WebSocket error**: Gevent worker je správně nakonfigurován

## Scaling

Railway automaticky škáluje podle potřeby:
- Minimum: 0 instancí (sleep mode)
- Maximum: podle vašeho plánu
- Auto-wake při příchozím requestu

## Testování

Po úspěšném deploymentu testujte:

1. **Health check**: `GET /health`
2. **Twilio webhook**: `POST /voice`
3. **WebSocket connection**: Pro real-time komunikaci
4. **Database operations**: Vytvoření a čtení dat 