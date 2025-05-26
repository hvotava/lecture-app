# Voice Learning

Aplikace pro hlasové školení prodejců s využitím Twilio Voice a OpenAI.

## Funkce

* Přidávání a správa lekcí přes webové rozhraní
* Automatické hovory prodejcům přes Twilio Voice
* Vyhodnocování odpovědí pomocí OpenAI GPT-4
* Plánování opakování na základě výkonu (spaced repetition)
* Možnost přerušení hovoru slovem "stop" nebo DTMF
* Responzivní admin rozhraní s Bootstrap 5 a HTMX

## Požadavky

* Python 3.12
* Účet na PythonAnywhere (placený pro outbound hovory)
* Účet na Twilio s českým číslem
* API klíč pro OpenAI

## Instalace na PythonAnywhere

1. Vytvořte novou webovou aplikaci na PythonAnywhere:
   * Python 3.12
   * Flask
   * Virtualenv

2. Naklonujte repozitář:
   ```bash
   git clone https://github.com/your-repo/voice-learning.git
   cd voice-learning
   ```

3. Nainstalujte závislosti:
   ```bash
   pip install -r requirements.txt
   ```

4. Nastavte proměnné prostředí v PythonAnywhere:
   * Web → WSGI file → envvars
   ```
   SECRET_KEY=your-secret-key
   TWILIO_ACCOUNT_SID=your-twilio-sid
   TWILIO_AUTH_TOKEN=your-twilio-token
   TWILIO_PHONE_NUMBER=your-twilio-number
   OPENAI_API_KEY=your-openai-key
   ```

5. Nastavte WSGI soubor:
   ```python
   import sys
   path = '/home/yourusername/voice-learning'
   if path not in sys.path:
       sys.path.append(path)
   
   from app.app import create_app
   application = create_app()
   ```

6. Nastavte plánovač úloh:
   * Tasks → Add a new scheduled task
   * Command: `cd /home/yourusername/voice-learning && python -c "from app.services.scheduler import SchedulerService; SchedulerService()._check_due_attempts()"`
   * Interval: Every 5 minutes

## Konfigurace Twilio

1. Získejte české telefonní číslo na Twilio
2. Nastavte webhooky pro hlas:
   * Primary handler: `https://your-app.pythonanywhere.com/voice`
   * Fallback handler: `https://your-app.pythonanywhere.com/voice/stop`
3. Povolte outbound hovory pro česká čísla v GeoPermissions

## Přidání lekce

1. Přihlaste se do admin rozhraní
2. Klikněte na "Nová lekce"
3. Vyplňte formulář:
   * Název lekce
   * Jazyk (cs/en)
   * Skript (text, který se přehraje)
   * Otázky ve formátu JSON:
     ```json
     {
       "current": "Otázka pro prodejce?",
       "answer": "Správná odpověď"
     }
     ```

## Spuštění testů

```bash
pytest tests/
```

## Spuštění manuálního hovoru

```bash
curl -X POST https://your-app.pythonanywhere.com/voice \
  -d "attempt_id=1" \
  -H "Content-Type: application/x-www-form-urlencoded"
```

## Architektura

* Flask pro webové rozhraní a Twilio webhooky
* SQLAlchemy pro práci s databází
* Twilio pro hlasové hovory a STT/TTS
* OpenAI pro vyhodnocování odpovědí
* APScheduler pro plánování opakování
* Bootstrap 5 + HTMX pro admin rozhraní

## Licence

MIT 