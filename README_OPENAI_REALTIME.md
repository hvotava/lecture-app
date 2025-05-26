# OpenAI Realtime API - Hlasový asistent pro výuku jazyků

## Přehled

Aplikace byla aktualizována, aby používala **OpenAI Realtime API** místo starého systému otázek a odpovědí. Nová implementace poskytuje:

- **Reálný čas konverzace** s AI asistentem
- **Přirozený dialog** místo strukturovaných otázek
- **Lepší rozpoznávání řeči** pomocí OpenAI Whisper
- **Kvalitní syntéza řeči** s hlasem "alloy"
- **Kontextové porozumění** lekce

## Architektura

### Komponenty

1. **Flask aplikace** (`app/app.py`)
   - Hlavní aplikace s Flask-SocketIO podporou
   - CORS konfigurace pro WebSocket připojení

2. **Voice routes** (`app/routes/voice.py`)
   - `/voice/` - Hlavní endpoint pro příchozí hovory
   - `/voice/openai-realtime` - Endpoint pro připojení k OpenAI Realtime API
   - `/voice/media-stream` - WebSocket endpoint pro Media Stream

3. **Realtime service** (`app/services/realtime_service.py`)
   - `OpenAIRealtimeService` - Správa připojení k OpenAI
   - `TwilioMediaStreamHandler` - Zpracování Twilio Media Stream
   - `handle_media_stream_websocket` - Hlavní WebSocket handler

### Tok dat

```
Twilio Call → Voice Endpoint → OpenAI Realtime Endpoint → Media Stream WebSocket
                                                                    ↓
OpenAI Realtime API ←→ WebSocket Handler ←→ Twilio Media Stream
```

## Konfigurace

### Požadované proměnné prostředí

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+420...

# Flask
SECRET_KEY=...
WEBHOOK_BASE_URL=https://your-domain.com
```

### Nové závislosti

```
Flask-SocketIO==5.3.6
websocket-client==1.7.0
```

## Funkce

### 1. Kontextové porozumění

AI asistent má přístup k obsahu lekce a může:
- Odpovídat na otázky o lekci
- Klást otázky pro ověření porozumění
- Poskytovat zpětnou vazbu
- Vysvětlovat obtížné části

### 2. Přirozená konverzace

- **Server VAD** (Voice Activity Detection) pro detekci řeči
- **Automatické ukončování** po tichu (800ms)
- **Přerušování** - AI může být přerušeno během mluvení
- **Transkripce** všech promluv pomocí Whisper

### 3. Audio kvalita

- **Formát**: G.711 μ-law (8kHz, mono)
- **Kompatibilita** s Twilio Media Stream
- **Nízká latence** díky streaming audio

## Implementace

### OpenAI Realtime API konfigurace

```json
{
  "type": "session.update",
  "session": {
    "modalities": ["text", "audio"],
    "instructions": "Jsi užitečný AI asistent pro výuku jazyků...",
    "voice": "alloy",
    "input_audio_format": "g711_ulaw",
    "output_audio_format": "g711_ulaw",
    "turn_detection": {
      "type": "server_vad",
      "threshold": 0.5,
      "silence_duration_ms": 800
    }
  }
}
```

### WebSocket zprávy

#### Z Twilio do OpenAI:
```json
{
  "type": "input_audio_buffer.append",
  "audio": "base64_encoded_audio"
}
```

#### Z OpenAI do Twilio:
```json
{
  "event": "media",
  "media": {
    "payload": "base64_encoded_audio"
  }
}
```

## Testování

### Lokální spuštění

```bash
# Instalace závislostí
pip install -r requirements.txt

# Spuštění aplikace
python3 -c "from app.app import create_app; app = create_app(); app.run(debug=True)"
```

### Test WebSocket připojení

```bash
# Test základní funkčnosti
python3 -c "from app.app import create_app; app = create_app(); print('OK')"
```

## Logování

Aplikace loguje následující události:

- **Připojení** k OpenAI Realtime API
- **Audio zprávy** (delta, done)
- **Transkripce** uživatelských promluv
- **Detekce řeči** (start/stop)
- **Chyby** WebSocket připojení

### Příklad logů

```
INFO:app.services.realtime_service:OpenAI session vytvořena: sess_...
INFO:app.services.realtime_service:OpenAI detekoval začátek řeči
INFO:app.services.realtime_service:Transkripce uživatele: Ahoj, jak se máš?
INFO:app.services.realtime_service:OpenAI dokončilo audio odpověď
```

## Řešení problémů

### Časté problémy

1. **WebSocket chyby**
   - Zkontrolujte OPENAI_API_KEY
   - Ověřte síťové připojení

2. **Audio problémy**
   - Zkontrolujte formát G.711 μ-law
   - Ověřte Twilio Media Stream konfiguraci

3. **Latence**
   - Optimalizujte síťové připojení
   - Zkontrolujte server výkon

### Debug režim

```python
import logging
logging.getLogger('app.services.realtime_service').setLevel(logging.DEBUG)
```

## Budoucí vylepšení

- [ ] Podpora více jazyků
- [ ] Pokročilé analýzy konverzace
- [ ] Integrace s dalšími AI modely
- [ ] Offline režim pro základní funkce
- [ ] Pokročilé metriky výkonu

## Kontakt

Pro technické dotazy nebo problémy vytvořte issue v repozitáři. 