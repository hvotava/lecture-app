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
SECRET_KEY=your-secret-key-here
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
DATABASE_URL=sqlite:///voice_learning.db
LOG_LEVEL=INFO
```

## Automatické nastavení

Railway automaticky:
- ✅ Detekuje `requirements.txt`
- ✅ Nainstaluje Python dependencies
- ✅ Použije `Procfile` pro start command
- ✅ Přiřadí doménu (např. `your-app.up.railway.app`)

## Po deploymenu

1. **Zkopírujte URL vaší aplikace**
2. **Aktualizujte `WEBHOOK_BASE_URL`** na skutečnou URL
3. **Nastavte Twilio webhook** na `https://your-app.up.railway.app/webhook/voice`
4. **Testujte aplikaci** zavoláním na Twilio číslo

## Monitoring

- Railway poskytuje automatické logy
- Můžete sledovat metriky v dashboardu
- Aplikace se automaticky restartuje při chybách

## Troubleshooting

Pokud deployment selže:
1. Zkontrolujte logy v Railway dashboardu
2. Ověřte všechny environment variables
3. Ujistěte se, že `requirements.txt` obsahuje všechny dependencies

## Scaling

Railway automaticky škáluje podle potřeby:
- Minimum: 0 instancí (sleep mode)
- Maximum: podle vašeho plánu
- Auto-wake při příchozím requestu 