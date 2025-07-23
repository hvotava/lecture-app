import os
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import PlainTextResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from app.models import Attempt, Lesson, User, Answer
from fastapi import Query
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter, Form, status, Depends
from starlette.requests import Request
from typing import Optional
from fastapi import Path
import socket
import requests
from sqlalchemy import text
import os
from datetime import datetime
from app.database import SessionLocal
import base64
import json
import io
import openai
# Audio zpracování
import audioop
import wave
import asyncio

load_dotenv()

app = FastAPI()

# CORS (pro případné admin rozhraní)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Nastavení šablon
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'app', 'templates')
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Admin router
admin_router = APIRouter(prefix="/admin", tags=["admin"])

@admin_router.get("/", response_class=HTMLResponse)
def admin_root(request: Request):
    # Přesměrování na seznam uživatelů (jako ve Flasku)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.get("/users", response_class=HTMLResponse, name="admin_list_users")
def admin_list_users(request: Request):
    session = SessionLocal()
    users = session.query(User).all()
    session.close()
    return templates.TemplateResponse("users/list.html", {"request": request, "users": users})

@admin_router.get("/users/new", response_class=HTMLResponse, name="admin_new_user_get")
def admin_new_user_get(request: Request):
    # Prázdný formulář pro nového uživatele
    return templates.TemplateResponse("users/form.html", {"request": request, "user": None, "form": {"name": "", "phone": "", "language": "cs", "detail": "", "name.errors": [], "phone.errors": [], "language.errors": [], "detail.errors": []}})

@admin_router.post("/users/new", response_class=HTMLResponse)
def admin_new_user_post(request: Request, name: str = Form(...), phone: str = Form(...), language: str = Form(...), detail: str = Form("")):
    errors = {"name": [], "phone": [], "language": [], "detail": []}
    if not name:
        errors["name"].append("Jméno je povinné.")
    if not phone or not (phone.startswith("+420") or phone.startswith("0")) or len(phone.replace(" ", "")) < 9:
        errors["phone"].append("Telefon musí být ve formátu +420XXXXXXXXX nebo 0XXXXXXXXX")
    if language not in ["cs", "en"]:
        errors["language"].append("Neplatný jazyk.")
    if any(errors.values()):
        return templates.TemplateResponse("users/form.html", {"request": request, "user": None, "form": {"name": name, "phone": phone, "language": language, "detail": detail, "name.errors": errors["name"], "phone.errors": errors["phone"], "language.errors": errors["language"], "detail.errors": errors["detail"]}})
    user = User(name=name, phone=phone, language=language, detail=detail)
    session = SessionLocal()
    session.add(user)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        form = {"name": name, "phone": phone, "language": language, "detail": detail, "name.errors": [str(e)], "phone.errors": [], "language.errors": [], "detail.errors": []}
        session.close()
        return templates.TemplateResponse("users/form.html", {"request": request, "user": None, "form": form})
    session.close()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.get("/users/{id}/edit", response_class=HTMLResponse, name="admin_edit_user_get")
def admin_edit_user_get(request: Request, id: int = Path(...)):
    session = SessionLocal()
    user = session.query(User).get(id)
    if not user:
        session.close()
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)
    form = {"name": user.name, "phone": user.phone, "language": user.language, "detail": user.detail, "name.errors": [], "phone.errors": [], "language.errors": [], "detail.errors": []}
    session.close()
    return templates.TemplateResponse("users/form.html", {"request": request, "user": user, "form": form})

@admin_router.post("/users/{id}/edit", response_class=HTMLResponse)
def admin_edit_user_post(request: Request, id: int = Path(...), name: str = Form(...), phone: str = Form(...), language: str = Form(...), detail: str = Form("")):
    session = SessionLocal()
    user = session.query(User).get(id)
    if not user:
        session.close()
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)
    errors = {"name": [], "phone": [], "language": [], "detail": []}
    if not name:
        errors["name"].append("Jméno je povinné.")
    if not phone or not (phone.startswith("+420") or phone.startswith("0")) or len(phone.replace(" ", "")) < 9:
        errors["phone"].append("Telefon musí být ve formátu +420XXXXXXXXX nebo 0XXXXXXXXX")
    if language not in ["cs", "en"]:
        errors["language"].append("Neplatný jazyk.")
    if any(errors.values()):
        form = {"name": name, "phone": phone, "language": language, "detail": detail, "name.errors": errors["name"], "phone.errors": errors["phone"], "language.errors": errors["language"], "detail.errors": errors["detail"]}
        session.close()
        return templates.TemplateResponse("users/form.html", {"request": request, "user": user, "form": form})
    user.name = name
    user.phone = phone
    user.language = language
    user.detail = detail
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        form = {"name": name, "phone": phone, "language": language, "detail": detail, "name.errors": [str(e)], "phone.errors": [], "language.errors": [], "detail.errors": []}
        session.close()
        return templates.TemplateResponse("users/form.html", {"request": request, "user": user, "form": form})
    session.close()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.post("/users/{user_id}/delete", name="admin_delete_user")
def admin_delete_user(user_id: int = Path(...)):
    session = SessionLocal()
    user = session.query(User).get(user_id)
    if user:
        try:
            session.delete(user)
            session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()
    else:
        session.close()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.post("/users/{user_id}/call", name="admin_call_user")
def admin_call_user(user_id: int = Path(...)):
    session = SessionLocal()
    user = session.query(User).get(user_id)
    if not user:
        session.close()
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)
    lesson = session.query(Lesson).filter_by(language=user.language).order_by(Lesson.id.desc()).first()
    if not lesson:
        session.close()
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)
    
    # Vytvoření nového pokusu
    attempt = Attempt(
        user_id=user.id,
        lesson_id=lesson.id,
        next_due=datetime.now()
    )
    session.add(attempt)
    session.commit()
    
    try:
        from app.services.twilio_service import TwilioService
        twilio = TwilioService()
        base_url = os.getenv("WEBHOOK_BASE_URL", "https://lecture-app-production.up.railway.app")
        webhook_url = f"{base_url.rstrip('/')}/voice/?attempt_id={attempt.id}"  # ✅ Používám attempt.id
        logger.info(f"Volám uživatele {user.phone} s webhook URL: {webhook_url}")
        twilio.call(user.phone, webhook_url)
    except Exception as e:
        logger.error(f"Chyba při volání Twilio: {e}")
    finally:
        session.close()
    
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.get("/lessons", response_class=HTMLResponse, name="admin_list_lessons")
def admin_list_lessons(request: Request):
    session = SessionLocal()
    lessons = session.query(Lesson).order_by(Lesson.id.desc()).all()
    session.close()
    return templates.TemplateResponse("lessons/list.html", {"request": request, "lessons": lessons})

@admin_router.get("/lessons/new", response_class=HTMLResponse, name="admin_new_lesson_get")
def admin_new_lesson_get(request: Request):
    form = {"title": "", "language": "cs", "script": "", "questions": "", "title.errors": [], "language.errors": [], "script.errors": [], "questions.errors": []}
    return templates.TemplateResponse("lessons/form.html", {"request": request, "lesson": None, "form": form})

@admin_router.post("/lessons/new", response_class=HTMLResponse)
def admin_new_lesson_post(request: Request, title: str = Form(...), language: str = Form(...), script: str = Form(...), questions: str = Form("")):
    errors = {"title": [], "language": [], "script": [], "questions": []}
    if not title:
        errors["title"].append("Název je povinný.")
    if language not in ["cs", "en"]:
        errors["language"].append("Neplatný jazyk.")
    if not script:
        errors["script"].append("Skript je povinný.")
    if any(errors.values()):
        form = {"title": title, "language": language, "script": script, "questions": questions, "title.errors": errors["title"], "language.errors": errors["language"], "script.errors": errors["script"], "questions.errors": errors["questions"]}
        return templates.TemplateResponse("lessons/form.html", {"request": request, "lesson": None, "form": form})
    lesson = Lesson(title=title, language=language, script=script, questions=questions)
    session = SessionLocal()
    session.add(lesson)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        form = {"title": title, "language": language, "script": script, "questions": questions, "title.errors": [str(e)], "language.errors": [], "script.errors": [], "questions.errors": []}
        session.close()
        return templates.TemplateResponse("lessons/form.html", {"request": request, "lesson": None, "form": form})
    session.close()
    return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)

@admin_router.get("/lessons/{id}/edit", response_class=HTMLResponse, name="admin_edit_lesson_get")
def admin_edit_lesson_get(request: Request, id: int = Path(...)):
    session = SessionLocal()
    lesson = session.query(Lesson).get(id)
    if not lesson:
        session.close()
        return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)
    form = {"title": lesson.title, "language": lesson.language, "script": lesson.script, "questions": lesson.questions, "title.errors": [], "language.errors": [], "script.errors": [], "questions.errors": []}
    session.close()
    return templates.TemplateResponse("lessons/form.html", {"request": request, "lesson": lesson, "form": form})

@admin_router.post("/lessons/{id}/edit", response_class=HTMLResponse)
def admin_edit_lesson_post(request: Request, id: int = Path(...), title: str = Form(...), language: str = Form(...), script: str = Form(...), questions: str = Form("")):
    session = SessionLocal()
    lesson = session.query(Lesson).get(id)
    if not lesson:
        session.close()
        return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)
    errors = {"title": [], "language": [], "script": [], "questions": []}
    if not title:
        errors["title"].append("Název je povinný.")
    if language not in ["cs", "en"]:
        errors["language"].append("Neplatný jazyk.")
    if not script:
        errors["script"].append("Skript je povinný.")
    if any(errors.values()):
        form = {"title": title, "language": language, "script": script, "questions": questions, "title.errors": errors["title"], "language.errors": errors["language"], "script.errors": errors["script"], "questions.errors": errors["questions"]}
        session.close()
        return templates.TemplateResponse("lessons/form.html", {"request": request, "lesson": lesson, "form": form})
    lesson.title = title
    lesson.language = language
    lesson.script = script
    lesson.questions = questions
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        form = {"title": title, "language": language, "script": script, "questions": questions, "title.errors": [str(e)], "language.errors": [], "script.errors": [], "questions.errors": []}
        session.close()
        return templates.TemplateResponse("lessons/form.html", {"request": request, "lesson": lesson, "form": form})
    session.close()
    return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)

@admin_router.post("/lessons/{lesson_id}/delete", name="admin_delete_lesson")
def admin_delete_lesson(lesson_id: int = Path(...)):
    session = SessionLocal()
    lesson = session.query(Lesson).get(lesson_id)
    if lesson:
        try:
            session.delete(lesson)
            session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()
    else:
        session.close()
    return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)

@admin_router.post("/lessons/generate-questions", response_class=JSONResponse)
async def admin_generate_questions(request: Request):
    import json
    data = None
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Neplatný JSON"}, status_code=400)
    script = data.get("script")
    language = data.get("language", "cs")
    if not script:
        return JSONResponse({"error": "Chybí text skriptu"}, status_code=400)
    try:
        from app.services.openai_service import OpenAIService
        openai = OpenAIService()
        questions = openai.generate_questions(script, language)
        if not questions:
            return JSONResponse({"error": "Nepodařilo se vygenerovat otázky. Zkontrolujte OpenAI API klíč."}, status_code=500)
        return JSONResponse({"questions": questions})
    except Exception as e:
        # Simulace pro vývoj bez OpenAI
        print(f"Chyba při generování otázek: {e}")
        return JSONResponse({"questions": [{"question": "Ukázková otázka?", "answer": "Ukázková odpověď"}]})

@admin_router.get("/network-test", response_class=JSONResponse)
def admin_network_test():
    results = {}
    # Test DNS
    try:
        socket.gethostbyname('api.twilio.com')
        results['dns_twilio'] = 'OK'
    except Exception as e:
        results['dns_twilio'] = f'CHYBA: {str(e)}'
    try:
        socket.gethostbyname('api.openai.com')
        results['dns_openai'] = 'OK'
    except Exception as e:
        results['dns_openai'] = f'CHYBA: {str(e)}'
    # Test HTTP
    try:
        response = requests.get('https://httpbin.org/ip', timeout=10)
        results['http_test'] = f"OK - IP: {response.json().get('origin', 'unknown')}"
    except Exception as e:
        results['http_test'] = f'CHYBA: {str(e)}'
    return results

@admin_router.get("/db-test", response_class=JSONResponse)
def admin_db_test():
    session = SessionLocal()
    results = {}
    try:
        session.execute(text('SELECT 1'))
        results['db_connection'] = 'OK'
    except Exception as e:
        results['db_connection'] = f'CHYBA: {str(e)}'
    try:
        user_count = User.query.count()
        results['user_table'] = f'OK - {user_count} uživatelů'
    except Exception as e:
        results['user_table'] = f'CHYBA: {str(e)}'
    try:
        lesson_count = Lesson.query.count()
        results['lesson_table'] = f'OK - {lesson_count} lekcí'
    except Exception as e:
        results['lesson_table'] = f'CHYBA: {str(e)}'
    session.close()
    return results

@admin_router.get("/init-db", response_class=JSONResponse)
def admin_init_db():
    session = SessionLocal()
    results = {}
    try:
        session.create_all()
        results['create_tables'] = 'OK'
    except Exception as e:
        results['create_tables'] = f'CHYBA: {str(e)}'
    try:
        user_count = User.query.count()
        lesson_count = Lesson.query.count()
        results['tables_check'] = f'OK - {user_count} uživatelů, {lesson_count} lekcí'
    except Exception as e:
        results['tables_check'] = f'CHYBA: {str(e)}'
    session.close()
    return results

@admin_router.get("/debug/openai", response_class=JSONResponse)
def admin_debug_openai():
    try:
        from app.services.openai_service import OpenAIService
        api_key = os.getenv('OPENAI_API_KEY')
        api_key_exists = bool(api_key)
        api_key_length = len(api_key) if api_key else 0
        api_key_start = api_key[:7] + "..." if api_key and len(api_key) > 7 else "N/A"
        openai = OpenAIService()
        openai_enabled = getattr(openai, 'enabled', False)
        openai_client_exists = bool(getattr(openai, 'client', None))
        debug_info = {
            "environment_variables": {
                "OPENAI_API_KEY_exists": api_key_exists,
                "OPENAI_API_KEY_length": api_key_length,
                "OPENAI_API_KEY_start": api_key_start
            },
            "openai_service": {
                "service_exists": bool(openai),
                "enabled": openai_enabled,
                "client_exists": openai_client_exists
            },
            "timestamp": datetime.now().isoformat()
        }
        return debug_info
    except Exception as e:
        return {"error": str(e)}

@admin_router.get("/debug/database", response_class=JSONResponse)
def admin_debug_database():
    session = SessionLocal()
    database_url = os.getenv('DATABASE_URL')
    database_url_exists = bool(database_url)
    database_url_start = database_url[:20] + "..." if database_url and len(database_url) > 20 else "N/A"
    app_database_uri = session.engine.url if hasattr(session, 'engine') else 'N/A'
    app_database_uri_start = str(app_database_uri)[:20] + "..." if app_database_uri and len(str(app_database_uri)) > 20 else "N/A"
    try:
        session.execute(text('SELECT 1'))
        database_connection = "OK"
    except Exception as db_error:
        database_connection = f"ERROR: {str(db_error)}"
    session.close()
    debug_info = {
        "environment_variables": {
            "DATABASE_URL_exists": database_url_exists,
            "DATABASE_URL_start": database_url_start,
            "DATABASE_URL_full": database_url if database_url else "N/A"
        },
        "app_configuration": {
            "SQLALCHEMY_DATABASE_URI_start": app_database_uri_start,
            "SQLALCHEMY_DATABASE_URI_full": str(app_database_uri)
        },
        "database_connection": database_connection,
        "timestamp": datetime.now().isoformat()
    }
    return debug_info

@admin_router.get("/debug/env", response_class=JSONResponse)
def admin_debug_env():
    env_vars = [
        'DATABASE_URL',
        'OPENAI_API_KEY',
        'TWILIO_ACCOUNT_SID',
        'TWILIO_AUTH_TOKEN',
        'TWILIO_PHONE_NUMBER',
        'WEBHOOK_BASE_URL',
        'SECRET_KEY',
        'PORT',
        'FLASK_ENV',
        'FLASK_DEBUG'
    ]
    env_info = {}
    for var in env_vars:
        value = os.getenv(var)
        if value:
            if 'KEY' in var or 'TOKEN' in var or 'SID' in var:
                env_info[var] = f"{value[:10]}..." if len(value) > 10 else "***"
            elif 'URL' in var:
                env_info[var] = value
            else:
                env_info[var] = value
        else:
            env_info[var] = "NENASTAVENO"
    debug_info = {
        "environment_variables": env_info,
        "timestamp": datetime.now().isoformat()
    }
    return debug_info

# Připojení admin routeru
app.include_router(admin_router)

logger = logging.getLogger("uvicorn")

@app.get("/")
def root():
    return {"message": "Lecture App FastAPI běží!", "endpoints": ["/health", "/voice/", "/voice/media-stream"]}

@app.post("/")
async def root_post(request: Request, attempt_id: str = Query(None)):
    """Twilio někdy volá root endpoint místo /voice/ - přesměrujeme na stejnou logiku"""
    logger.info("Přijat Twilio webhook na ROOT / endpoint")
    logger.info(f"Attempt ID: {attempt_id}")
    
    # Stejná TwiML odpověď jako v /voice/
    response = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="cs-CZ" rate="0.9" voice="Google.cs-CZ-Standard-A">Vítejte u AI asistenta pro výuku jazyků.</Say>
    <Say language="cs-CZ" rate="0.9" voice="Google.cs-CZ-Standard-A">Nyní vás připojuji k AI asistentovi.</Say>
    <Start>
        <Stream url="wss://lecture-app-production.up.railway.app/audio" track="both_tracks" statusCallback="https://lecture-app-production.up.railway.app/stream-callback" />
    </Start>
    <Pause length="3600"/>
</Response>"""
    logger.info(f"TwiML odpověď z ROOT: {response}")
    return Response(content=response, media_type="text/xml")

@app.get("/health")
def health():
    return {"status": "healthy", "service": "lecture-app"}

@app.post("/stream-callback")
async def stream_callback(request: Request):
    """Twilio Stream statusCallback endpoint - pouze potvrzení HTTP 200"""
    logger.info("Přijat Twilio Stream statusCallback")
    
    # Logování pro debugging
    try:
        form_data = await request.form()
        logger.info(f"Stream callback data: {dict(form_data)}")
    except:
        pass
    
    # Pouze HTTP 200 odpověď, žádné TwiML
    return {"status": "ok"}

@app.post("/voice/")
async def voice(request: Request, attempt_id: str = Query(None)):
    logger.info("Přijat Twilio webhook na /voice/")
    logger.info(f"Attempt ID: {attempt_id}")
    response = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="cs-CZ" rate="0.9" voice="Google.cs-CZ-Standard-A">Vítejte u AI asistenta pro výuku jazyků.</Say>
    <Say language="cs-CZ" rate="0.9" voice="Google.cs-CZ-Standard-A">Nyní vás připojuji k AI asistentovi.</Say>
    <Start>
        <Stream url="wss://lecture-app-production.up.railway.app/audio" track="both_tracks" statusCallback="https://lecture-app-production.up.railway.app/stream-callback" />
    </Start>
    <Pause length="3600"/>
</Response>"""
    logger.info(f"TwiML odpověď: {response}")
    return Response(content=response, media_type="text/xml")

@app.post("/voice/start-stream/")
async def voice_start_stream(request: Request):
    """TwiML odpověď s <Start><Stream> pro Media Streams (obousměrně)."""
    response = """
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="cs-CZ" rate="0.9" voice="Google.cs-CZ-Standard-A">
        Vítejte u AI asistenta pro výuku jazyků.
    </Say>
    <Start>
        <Stream url="wss://lecture-app-production.up.railway.app/audio" track="both" />
    </Start>
</Response>
"""
    return Response(content=response, media_type="text/xml")

@app.websocket("/audio")
async def audio_stream(websocket: WebSocket):
    logger.info("=== AUDIO WEBSOCKET HANDLER SPUŠTĚN ===")
    logger.info(f"WebSocket client: {websocket.client}")
    logger.info(f"WebSocket headers: {websocket.headers}")
    logger.info(f"WebSocket query params: {websocket.query_params}")
    
    await websocket.accept()
    logger.info("=== WEBSOCKET /AUDIO ACCEPTED - ČEKÁM NA TWILIO DATA ===")
    
    # Inicializace AI služeb
    try:
        from app.services.openai_service import OpenAIService
        openai_service = OpenAIService()
        logger.info("OpenAI služba inicializována")
    except Exception as e:
        logger.error(f"Chyba při inicializaci OpenAI: {e}")
        openai_service = None
    
    # Stav konverzace
    stream_sid = None
    audio_buffer = bytearray()
    last_audio_time = None
    conversation_context = []
    attempt_id = websocket.query_params.get("attempt_id")
    lesson_context = ""
    
    # Načtení lekce pro kontext
    if attempt_id:
        try:
            session = SessionLocal()
            attempt = session.query(Attempt).get(int(attempt_id))
            if attempt and attempt.lesson:
                lesson_context = f"Lekce: {attempt.lesson.title}\nObsah: {attempt.lesson.script}"
                logger.info(f"Načten kontext lekce: {attempt.lesson.title}")
            session.close()
        except Exception as e:
            logger.error(f"Chyba při načítání lekce: {e}")
    
    async def send_audio_to_twilio(audio_data: bytes):
        """Pošle audio data zpět do Twilio"""
        if not stream_sid:
            logger.warning("Nelze poslat audio - stream_sid není nastaven")
            return
            
        try:
            # Konverze na μ-law a base64
            import audioop
            mulaw_data = audioop.lin2ulaw(audio_data, 2)  # 16-bit linear to μ-law
            audio_base64 = base64.b64encode(mulaw_data).decode('utf-8')
            
            media_message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": audio_base64
                }
            }
            
            await websocket.send_text(json.dumps(media_message))
            logger.info("Audio odesláno do Twilio")
        except Exception as e:
            logger.error(f"Chyba při odesílání audio: {e}")
    
    def wav_to_mulaw(wav_bytes):
        import wave
        import audioop
        import io
        with io.BytesIO(wav_bytes) as wav_io:
            with wave.open(wav_io, 'rb') as wav_file:
                n_channels = wav_file.getnchannels()
                sampwidth = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                pcm_data = wav_file.readframes(wav_file.getnframes())
                logger.info(f"[TTS] WAV parametry: {n_channels}ch, {sampwidth*8}bit, {framerate}Hz, {len(pcm_data)} bytes")
                if n_channels != 1 or sampwidth != 2 or framerate != 8000:
                    logger.error("TTS WAV není mono/16bit/8kHz! Twilio přehraje pouze 8kHz mono μ-law.")
                    # (volitelně: zde by šel přidat resampling, ale pro OpenAI TTS by mělo být správně)
                    raise ValueError("TTS WAV není mono/16bit/8kHz!")
                mulaw_data = audioop.lin2ulaw(pcm_data, 2)
                return mulaw_data

    async def process_speech_and_respond(audio_bytes: bytes):
        """Zpracuje řeč a vygeneruje odpověď"""
        if not openai_service:
            logger.error("OpenAI služba není dostupná")
            return
        try:
            logger.info(f"Zpracovávám audio buffer ({len(audio_bytes)} bytes)")
            # 1. Speech-to-Text pomocí Whisper
            import io
            audio_file = io.BytesIO()
            import audioop
            import wave
            linear_data = audioop.ulaw2lin(audio_bytes, 1)
            with wave.open(audio_file, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(8000)
                wav_file.writeframes(linear_data)
            audio_file.seek(0)
            audio_file.name = "audio.wav"
            transcript = openai_service.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="cs"
            )
            user_text = transcript.text.strip()
            if not user_text:
                logger.info("Prázdná transkripce - ignoruji")
                return
            logger.info(f"Transkripce: {user_text}")
            conversation_context.append({"role": "user", "content": user_text})
            # 2. Generování odpovědi pomocí GPT
            system_prompt = f"""Jsi AI asistent pro výuku jazyků. {lesson_context}\n\nTvoje úkoly:\n- Pomáhej studentovi s lekcí\n- Odpovídej na otázky týkající se obsahu\n- Buď trpělivý a povzbuzující\n- Odpovídej stručně (max 2-3 věty)\n- Mluv česky"""
            messages = [{"role": "system", "content": system_prompt}] + conversation_context[-10:]
            response = openai_service.client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                max_tokens=150,
                temperature=0.7
            )
            ai_response = response.choices[0].message.content
            logger.info(f"GPT odpověď: {ai_response}")
            conversation_context.append({"role": "assistant", "content": ai_response})
            # 3. Text-to-Speech
            logger.info(f"Posílám do TTS: {ai_response}")
            tts_response = openai_service.client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=ai_response,
                response_format="wav"
            )
            logger.info(f"TTS odpověď: {type(tts_response.content)}, velikost: {len(tts_response.content)} bytes")
            if not tts_response.content or len(tts_response.content) < 100:
                logger.error("TTS vrátil prázdný nebo příliš krátký audio výstup!")
                return
            # Konverze TTS WAV na μ-law
            try:
                mulaw_data = wav_to_mulaw(tts_response.content)
            except Exception as e:
                logger.error(f"Chyba při převodu TTS WAV na μ-law: {e}")
                return
            # Odeslání do Twilia
            audio_base64 = base64.b64encode(mulaw_data).decode('utf-8')
            media_message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": audio_base64
                }
            }
            try:
                await websocket.send_text(json.dumps(media_message))
                logger.info("Audio odesláno do Twilia (po TTS)")
            except Exception as e:
                logger.error(f"Chyba při odesílání audio: {e}")
        except Exception as e:
            logger.error(f"Chyba při zpracování řeči: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    try:
        # Pošleme potvrzení připojení
        await websocket.send_text('{"event":"connected","protocol":"websocket","version":"1.0.0"}')
        logger.info("Odesláno potvrzení připojení")
        
        # Periodické zpracování bufferu při tichu
        async def silence_processor():
            while True:
                await asyncio.sleep(0.5)  # Kontrola každou půlsekundu
                if last_audio_time and audio_buffer:
                    time_since_last = (datetime.now() - last_audio_time).total_seconds()
                    logger.info(f"[Ticho-check] Čas od posledního audia: {time_since_last:.2f}s, buffer: {len(audio_buffer)} bytes")
                    # Pokud je v bufferu aspoň 0.5 sekundy audia nebo 0.5s ticha
                    if len(audio_buffer) > 4000 or time_since_last > 0.5:
                        buffer_copy = bytes(audio_buffer)
                        audio_buffer.clear()
                        logger.info(f"[Ticho-check] Zpracovávám buffer ({len(buffer_copy)} bytes) po {time_since_last:.2f}s ticha")
                        await process_speech_and_respond(buffer_copy)

        # Logování při každém přírůstku do bufferu
        def log_audio_chunk(seq, track, buf_len):
            logger.info(f"[AUDIO-CHUNK] Přidán chunk #{seq} ({track}), buffer: {buf_len} bytes")
        
        # Spustíme background task
        silence_task = asyncio.create_task(silence_processor())
        
        try:
            while True:
                data = await websocket.receive_text()
                
                try:
                    msg = json.loads(data)
                    event = msg.get("event")
                    
                    if event == "start":
                        logger.info("=== MEDIA STREAM START EVENT PŘIJAT! ===")
                        stream_sid = msg.get("streamSid")
                        logger.info(f"Stream SID: {stream_sid}")
                        
                        # Úvodní zpráva
                        welcome_text = f"Vítejte u AI asistenta pro výuku jazyků!"
                        if lesson_context:
                            welcome_text += f" Dnes se budeme učit o tématu z vaší lekce. Můžete se mě ptát na cokoliv!"
                        
                        try:
                            tts_response = openai_service.client.audio.speech.create(
                                model="tts-1",
                                voice="alloy",
                                input=welcome_text,
                                response_format="wav"
                            )
                            await send_audio_to_twilio(tts_response.content)
                            logger.info("Úvodní zpráva odeslána")
                        except Exception as e:
                            logger.error(f"Chyba při generování úvodní zprávy: {e}")
                        
                    elif event == "connected":
                        logger.info("=== WEBSOCKET CONNECTED EVENT ===")
                        
                    elif event == "media":
                        payload = msg["media"]["payload"]
                        track = msg["media"]["track"]
                        seq = msg.get("sequenceNumber", "?")
                        # Logování každého chunku
                        log_audio_chunk(seq, track, len(audio_buffer))
                        # Zpracováváme pouze inbound (příchozí) audio
                        if track == "inbound":
                            audio_bytes = base64.b64decode(payload)
                            audio_buffer.extend(audio_bytes)
                            last_audio_time = datetime.now()
                            # Zpracování po 0.5s audia (4000 bytes)
                            if len(audio_buffer) > 4000:
                                buffer_copy = bytes(audio_buffer)
                                audio_buffer.clear()
                                logger.info(f"[MEDIA] Zpracovávám buffer ({len(buffer_copy)} bytes) po {seq} chunku")
                                await process_speech_and_respond(buffer_copy)
                    
                    elif event == "stop":
                        logger.info("Media Stream ukončen")
                        # Zpracování posledního bufferu
                        if audio_buffer:
                            buffer_copy = bytes(audio_buffer)
                            await process_speech_and_respond(buffer_copy)
                        break
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Neplatný JSON z Twilia: {e}")
                except Exception as e:
                    logger.error(f"Chyba při zpracování zprávy: {e}")
                    
        finally:
            # Zrušíme background task
            silence_task.cancel()
            try:
                await silence_task
            except asyncio.CancelledError:
                pass
        
    except WebSocketDisconnect:
        logger.info("WebSocket /audio odpojen Twiliem (WebSocketDisconnect)")
    except Exception as e:
        logger.error(f"Chyba ve WebSocket /audio: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        try:
            await websocket.close()
        except:
            pass

@app.websocket("/voice/media-stream")
async def media_stream(websocket: WebSocket):
    logger.info("=== MEDIA STREAM WEBSOCKET HANDLER SPUŠTĚN ===")
    logger.info(f"WebSocket client: {websocket.client}")
    logger.info(f"WebSocket headers: {websocket.headers}")
    logger.info(f"WebSocket query params: {websocket.query_params}")
    
    await websocket.accept()
    logger.info("=== WEBSOCKET ACCEPTED - ČEKÁM NA TWILIO DATA ===")
    
    # Inicializace služeb
    from app.services.openai_service import OpenAIService
    from app.services.twilio_service import TwilioService
    openai_service = OpenAIService()
    twilio_service = TwilioService()
    
    # Stav konverzace
    conversation_state = {
        "phase": "introduction",  # introduction, teaching, questioning, evaluation
        "current_question_index": 0,
        "questions": [],
        "user_answers": [],
        "attempt_id": None,
        "user_id": None,
        "lesson_id": None,
        "lesson": None,
        "audio_buffer": b"",
        "last_audio_time": None
    }
    
    try:
        # Načtení parametrů z URL
        query_params = websocket.query_params
        attempt_id = query_params.get("attempt_id")
        logger.info(f"WebSocket query params: {query_params}")
        
        if attempt_id:
            logger.info(f"Načítám attempt_id: {attempt_id}")
            # Načtení pokusu z databáze
            session = SessionLocal()
            attempt = session.query(Attempt).get(int(attempt_id))
            if attempt:
                conversation_state["attempt_id"] = attempt.id
                conversation_state["user_id"] = attempt.user_id
                conversation_state["lesson_id"] = attempt.lesson_id
                conversation_state["lesson"] = attempt.lesson
                
                # Generování otázek z lekce
                if attempt.lesson:
                    questions = openai_service.generate_questions_from_lesson(
                        attempt.lesson.script, 
                        attempt.lesson.language, 
                        num_questions=5
                    )
                    conversation_state["questions"] = questions
                    logger.info(f"Vygenerováno {len(questions)} otázek pro lekci")
            
            session.close()
        
        # Úvodní hláška
        logger.info("Odesílám úvodní TwiML odpověď Twiliu")
        await send_twiml_response(websocket, twilio_service.create_introduction_response(
            conversation_state["lesson"] if conversation_state["lesson"] else None
        ))
        
        while True:
            logger.info("Čekám na zprávu z Twilia...")
            # Přijetí dat z Twilio
            data = await websocket.receive_text()
            logger.info(f"Přijato z Twilia: {data}")
            
            # Parsování JSON z Twilio Media Streams
            try:
                import json
                media_data = json.loads(data)
                
                if "event" in media_data:
                    event = media_data["event"]
                    
                    if event == "media":
                        # Audio data
                        audio_data = media_data.get("media", {}).get("payload", "")
                        if audio_data:
                            # Přidání do bufferu
                            import base64
                            try:
                                audio_bytes = base64.b64decode(audio_data)
                                conversation_state["audio_buffer"] += audio_bytes
                                conversation_state["last_audio_time"] = datetime.now()
                            except Exception as e:
                                logger.error(f"Chyba při dekódování audia: {e}")
                    
                    elif event == "stop":
                        # Konec audia - zpracování
                        if conversation_state["audio_buffer"]:
                            await process_audio_and_respond(
                                websocket, 
                                conversation_state, 
                                openai_service, 
                                twilio_service
                            )
                    
                    elif event == "mark":
                        # Mark event - možnost pro synchronizaci
                        mark_name = media_data.get("mark", {}).get("name", "")
                        logger.info(f"Mark event: {mark_name}")
                        
                        if mark_name == "question_start":
                            conversation_state["phase"] = "questioning"
                        elif mark_name == "teaching_start":
                            conversation_state["phase"] = "teaching"
                            
            except json.JSONDecodeError:
                logger.warning("Neplatný JSON z Twilio")
            except Exception as e:
                logger.error(f"Chyba při zpracování dat: {e}")
                
    except WebSocketDisconnect:
        logger.info("WebSocket odpojen Twiliem (WebSocketDisconnect)")
        # Uložení výsledků
        await save_conversation_results(conversation_state)
    except Exception as e:
        logger.error(f"Chyba ve WebSocket handleru: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await websocket.close()

async def process_audio_and_respond(websocket, conversation_state, openai_service, twilio_service):
    """Zpracuje audio buffer a odpoví podle fáze konverzace."""
    try:
        # Převod audia na text
        audio_text = openai_service.speech_to_text(
            conversation_state["audio_buffer"], 
            language=conversation_state["lesson"].language if conversation_state["lesson"] else "cs"
        )
        
        if not audio_text.strip():
            logger.info("Prázdný audio - ignoruji")
            conversation_state["audio_buffer"] = b""
            return
        
        logger.info(f"Přepsaný text: {audio_text}")
        
        # Zpracování podle fáze konverzace
        if conversation_state["phase"] == "introduction":
            # Přechod do fáze výuky
            conversation_state["phase"] = "teaching"
            await send_twiml_response(websocket, twilio_service.create_teaching_response(
                conversation_state["lesson"]
            ))
            
        elif conversation_state["phase"] == "teaching":
            # Kontrola, zda uživatel chce přejít k otázkám
            if any(keyword in audio_text.lower() for keyword in ["otázky", "zkoušení", "test", "hotovo", "konec"]):
                conversation_state["phase"] = "questioning"
                await send_twiml_response(websocket, twilio_service.create_questioning_start_response())
            else:
                # Odpověď na otázku o lekci
                response = openai_service.answer_user_question(
                    audio_text,
                    current_lesson=conversation_state["lesson"].__dict__ if conversation_state["lesson"] else None,
                    language=conversation_state["lesson"].language if conversation_state["lesson"] else "cs"
                )
                await send_twiml_response(websocket, twilio_service.create_chat_response(
                    response["answer"],
                    conversation_state["lesson"].language if conversation_state["lesson"] else "cs"
                ))
                
        elif conversation_state["phase"] == "questioning":
            # Zpracování odpovědi na otázku
            if conversation_state["current_question_index"] < len(conversation_state["questions"]):
                current_question = conversation_state["questions"][conversation_state["current_question_index"]]
                
                # Vyhodnocení odpovědi
                evaluation = openai_service.evaluate_voice_answer(
                    current_question["question"],
                    current_question["correct_answer"],
                    audio_text,
                    conversation_state["lesson"].language if conversation_state["lesson"] else "cs"
                )
                
                # Uložení odpovědi
                conversation_state["user_answers"].append({
                    "question": current_question["question"],
                    "correct_answer": current_question["correct_answer"],
                    "user_answer": audio_text,
                    "score": evaluation["score"],
                    "feedback": evaluation["feedback"],
                    "is_correct": evaluation["is_correct"]
                })
                
                # Odpověď s feedbackem
                feedback_text = f"Vaše odpověď: {evaluation['feedback']}. Skóre: {evaluation['score']}%."
                await send_twiml_response(websocket, twilio_service.create_feedback_response(
                    feedback_text,
                    conversation_state["lesson"].language if conversation_state["lesson"] else "cs"
                ))
                
                conversation_state["current_question_index"] += 1
                
                # Další otázka nebo konec
                if conversation_state["current_question_index"] < len(conversation_state["questions"]):
                    next_question = conversation_state["questions"][conversation_state["current_question_index"]]
                    await send_twiml_response(websocket, twilio_service.create_question_response(
                        next_question["question"],
                        conversation_state["lesson"].language if conversation_state["lesson"] else "cs"
                    ))
                else:
                    # Konec zkoušení
                    conversation_state["phase"] = "evaluation"
                    await send_twiml_response(websocket, twilio_service.create_evaluation_response(
                        conversation_state["user_answers"],
                        conversation_state["lesson"].language if conversation_state["lesson"] else "cs"
                    ))
        
        # Vyčištění bufferu
        conversation_state["audio_buffer"] = b""
        
    except Exception as e:
        logger.error(f"Chyba při zpracování audia: {e}")
        conversation_state["audio_buffer"] = b""

async def send_twiml_response(websocket, twiml_content):
    """Pošle TwiML odpověď zpět do Twilio."""
    try:
        await websocket.send_text(json.dumps({
            "event": "media",
            "streamSid": "placeholder",
            "media": {
                "payload": twiml_content
            }
        }))
    except Exception as e:
        logger.error(f"Chyba při odesílání TwiML: {e}")

async def save_conversation_results(conversation_state):
    """Uloží výsledky konverzace do databáze."""
    if not conversation_state["attempt_id"]:
        return
    
    session = SessionLocal()
    try:
        attempt = session.query(Attempt).get(conversation_state["attempt_id"])
        if attempt and conversation_state["user_answers"]:
            total_score = sum(answer["score"] for answer in conversation_state["user_answers"])
            average_score = total_score / len(conversation_state["user_answers"])
            attempt.score = average_score
            attempt.status = "completed"
            attempt.completed_at = datetime.now()
            attempt.calculate_next_due()
            for i, answer_data in enumerate(conversation_state["user_answers"]):
                answer = Answer(
                    attempt_id=attempt.id,
                    question_index=i,
                    question_text=answer_data["question"],
                    correct_answer=answer_data["correct_answer"],
                    user_answer=answer_data["user_answer"],
                    score=answer_data["score"],
                    is_correct=answer_data["is_correct"],
                    feedback=answer_data["feedback"]
                )
                session.add(answer)
            session.commit()
            logger.info(f"Uloženy výsledky pro pokus {attempt.id}, průměrné skóre: {average_score:.1f}%")
    except Exception as e:
        session.rollback()
        logger.error(f"Chyba při ukládání výsledků: {e}")
    finally:
        session.close() 