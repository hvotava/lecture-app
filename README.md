# Voice Learning

Aplikace pro hlasové školení prodejců s využitím Twilio Voice a OpenAI Realtime API.

## Funkce

* Přidávání a správa lekcí přes webové rozhraní
* Automatické hovory prodejcům přes Twilio Voice
* **OpenAI Realtime API**: Real-time speech-to-speech komunikace s modelem `gpt-4o-realtime-preview-2024-10-01`
* **Model**: `gpt-4.1-mini` pro standardní AI operace, `gpt-4o-realtime-preview` pro real-time komunikaci
* Vyhodnocování odpovědí pomocí AI v reálném čase
* Plánování opakování na základě výkonu (spaced repetition)
* Možnost přerušení hovoru slovem "stop" nebo DTMF
* Responzivní admin rozhraní s Bootstrap 5 a HTMX
* Real-time audio konverzace pomocí Twilio Media Streams

## Požadavky

* Python 3.12
* Účet na Railway.com (pro deployment)
* Účet na Twilio s UK/US číslem
* API klíč pro OpenAI s přístupem k Realtime API
* **OpenAI Realtime API**: Model `gpt-4o-realtime-preview-2024-10-01` musí být dostupný

## Instalace na Railway.com

1. Naklonujte repozitář:
   ```bash
   git clone https://github.com/your-repo/voice-learning.git
   cd voice-learning
   ```

2. Nainstalujte závislosti:
   ```bash
   pip install -r requirements.txt
   ```

3. Nastavte proměnné prostředí v Railway Dashboard:
   ```
   SECRET_KEY=your-secret-key
   TWILIO_ACCOUNT_SID=your-twilio-sid
   TWILIO_AUTH_TOKEN=your-twilio-token
   TWILIO_PHONE_NUMBER=your-twilio-number
   OPENAI_API_KEY=your-openai-key
   DATABASE_URL=postgresql://...
   WEBHOOK_BASE_URL=https://your-app.up.railway.app
   ```

4. Nasaďte na Railway:
   ```bash
   railway deploy
   ```

## Konfigurace OpenAI Realtime API

Aplikace používá OpenAI Realtime API s těmito parametry:
- **Model**: `gpt-4o-realtime-preview-2024-10-01`
- **Účel**: Real-time speech-to-speech AI asistent pro výuku jazyků
- **Formát**: G.711 μ-law (8kHz, mono) - kompatibilní s Twilio
- **Voice Activity Detection**: Server VAD s threshold 0.5
- **Silence Detection**: 800ms ticha pro automatické ukončení

AI asistent má nastavené instrukce pro:
- Komunikaci v češtině
- Pomoc s výukou jazyků
- Trpělivé a povzbuzující chování
- Vyhodnocování odpovědí studentů v reálném čase
- Kladení otázek pro ověření porozumění

## Konfigurace Twilio

1. Získejte UK/US telefonní číslo na Twilio
2. Nastavte webhooky pro hlas:
   * Primary handler: `https://your-app.up.railway.app/voice/`
   * Fallback handler: `https://your-app.up.railway.app/`
3. Povolte outbound hovory pro UK/US čísla v GeoPermissions
4. **Media Streams**: Automaticky konfigurováno pro WebSocket připojení na `/audio`

## Přidání lekce

1. Přihlaste se do admin rozhraní na `/admin`
2. Klikněte na "Nová lekce"
3. Vyplňte formulář:
   * Název lekce
   * Jazyk (cs/en)
   * Skript (text, který se přehraje)
   * Otázky ve formátu JSON (volitelné - AI může generovat vlastní)

## Spuštění testů

```bash
pytest tests/
```

## Spuštění manuálního hovoru

Přes admin rozhraní:
1. Jděte na `/admin/users`
2. Klikněte "Zavolat" u konkrétního uživatele

## Architektura

* **FastAPI** pro webové rozhraní a Twilio webhooky
* **SQLAlchemy** pro práci s databází (PostgreSQL)
* **Twilio Media Streams** pro real-time audio komunikaci
* **OpenAI Realtime API** s modelem `gpt-4o-realtime-preview-2024-10-01` pro speech-to-speech
* **WebSocket** komunikace pro real-time audio streaming mezi Twilio a OpenAI

## Technické detaily

### Real-time Audio Pipeline
```
Twilio Media Stream → WebSocket (/audio) → OpenAI Realtime API → WebSocket → Twilio
```

### Audio zpracování
- **Vstup**: Twilio Media Stream (G.711 μ-law, 8kHz, mono)
- **Zpracování**: Přímé předání do OpenAI Realtime API (bez konverze)
- **Výstup**: OpenAI Realtime API → G.711 μ-law → Twilio Media Stream
- **Chunking**: Audio chunky předávány v real-time bez buffering

### AI Pipeline (Real-time)
1. **Příjem audio** z Twilio Media Stream
2. **Přímé předání** do OpenAI Realtime API (`input_audio_buffer.append`)
3. **Real-time zpracování** pomocí `gpt-4o-realtime-preview-2024-10-01`
4. **Automatická detekce řeči** (Server VAD)
5. **Streaming audio odpověď** (`response.audio.delta`)
6. **Přímé předání** zpět do Twilio Media Stream

### WebSocket zprávy

#### Twilio → OpenAI:
```json
{
  "type": "input_audio_buffer.append",
  "audio": "base64_encoded_mulaw_audio"
}
```

#### OpenAI → Twilio:
```json
{
  "event": "media",
  "streamSid": "stream_id",
  "media": {
    "payload": "base64_encoded_mulaw_audio"
  }
}
```

### Klíčové OpenAI Realtime API zprávy:
- `session.update` - Konfigurace session
- `input_audio_buffer.append` - Audio data od uživatele
- `response.create` - Požadavek na odpověď
- `response.audio.delta` - Streaming audio odpověď
- `input_audio_buffer.speech_stopped` - Detekce konce řeči

## Licence

MIT 