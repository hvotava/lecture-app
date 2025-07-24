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
import time
import tempfile

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
    """Twilio Stream statusCallback endpoint"""
    logger.info("Přijat Twilio Stream statusCallback")
    
    # Přečteme data z requestu
    form_data = await request.form()
    callback_data = dict(form_data)
    
    logger.info(f"Stream callback data: {callback_data}")
    
    # Zpracujeme různé typy stream eventů
    stream_event = callback_data.get('StreamEvent')
    stream_sid = callback_data.get('StreamSid')
    
    if stream_event == 'stream-started':
        logger.info(f"🟢 Stream {stream_sid} spuštěn")
    elif stream_event == 'stream-stopped':
        logger.info(f"🔴 Stream {stream_sid} ukončen - WebSocket by měl být uzavřen")
        # Zde by mohlo být dodatečné cleanup pokud potřebujeme
    elif stream_event == 'stream-error':
        error_code = callback_data.get('StreamErrorCode')
        error_msg = callback_data.get('StreamError')
        logger.error(f"❌ Stream {stream_sid} chyba {error_code}: {error_msg}")
    
    return {"status": "ok"}

@app.post("/voice/call")
async def voice_call_handler(request: Request):
    """Handler pro Twilio Voice webhook na /voice/call endpoint"""
    logger.info("Přijat Twilio webhook na /voice/call")
    
    # Získáme form data z Twilio
    form_data = await request.form()
    
    # Logování důležitých informací
    from_number = form_data.get('From', 'Unknown')
    to_number = form_data.get('To', 'Unknown') 
    call_sid = form_data.get('CallSid', 'Unknown')
    
    logger.info(f"Call SID: {call_sid}")
    logger.info(f"From: {from_number} -> To: {to_number}")
    
    # Zkusíme získat attempt_id z query parametrů
    attempt_id = request.query_params.get('attempt_id')
    logger.info(f"Attempt ID: {attempt_id}")
    
    # Vytvoříme TwiML odpověď
    twiml_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="cs-CZ" rate="0.9" voice="Google.cs-CZ-Standard-A">Vítejte u AI asistenta pro výuku jazyků.</Say>
    <Say language="cs-CZ" rate="0.9" voice="Google.cs-CZ-Standard-A">Nyní vás připojuji k AI asistentovi.</Say>
    <Start>
        <Stream 
            name="ai_assistant_stream"
            url="wss://lecture-app-production.up.railway.app/audio" 
            track="both_tracks" 
            statusCallback="https://lecture-app-production.up.railway.app/stream-callback"
            statusCallbackMethod="POST"
        />
    </Start>
    <Pause length="3600"/>
</Response>'''
    
    logger.info(f"TwiML odpověď z /voice/call: {twiml_response}")
    
    return Response(
        content=twiml_response,
        media_type="application/xml"
    )

@app.post("/voice/")
async def voice_handler(request: Request):
    logger.info("Přijat Twilio webhook na /voice/")
    logger.info(f"Attempt ID: {request.query_params.get('attempt_id')}")
    
    # Získání parametrů hovoru
    form = await request.form()
    caller_country = form.get("CallerCountry", "")
    to_country = form.get("ToCountry", "")
    logger.info(f"Volající: {caller_country} -> {to_country}")
    
    response = VoiceResponse()
    
    # Úvodní hlášení
    response.say(
        "Vítejte u AI asistenta pro výuku jazyků.",
        language="cs-CZ",
        rate="0.9",
        voice="Google.cs-CZ-Standard-A"
    )
    response.say(
        "Nyní vás připojuji k AI asistentovi.",
        language="cs-CZ",
        rate="0.9",
        voice="Google.cs-CZ-Standard-A"
    )
    
    # Konfigurace Media Streamu - použití Start místo Connect pro obousměrný stream
    start = response.start()
    start.stream(
        url="wss://lecture-app-production.up.railway.app/audio",
        track="both_tracks",  # Explicitně nastavíme obousměrný stream
        status_callback="https://lecture-app-production.up.railway.app/stream-callback",
        status_callback_method="POST",
        name="ai_assistant_stream"
    )
    
    # Dlouhá pauza pro udržení hovoru
    response.pause(length=3600)
    
    logger.info(f"TwiML odpověď: {response}")
    return Response(content=str(response), media_type="text/xml")

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

# Pomocná funkce pro práci s OpenAI Assistant
async def get_assistant_info(client, assistant_id: str):
    """Získá informace o OpenAI asistentovi"""
    try:
        assistant = await client.beta.assistants.retrieve(assistant_id)
        logger.info(f"Assistant info - ID: {assistant.id}, Name: {assistant.name}, Model: {assistant.model}")
        return assistant
    except Exception as e:
        logger.error(f"Chyba při získávání informací o asistentovi {assistant_id}: {e}")
        return None

async def wav_to_mulaw(audio_data: bytes) -> bytes:
    """Převede WAV audio na μ-law formát pro Twilio"""
    try:
        from pydub import AudioSegment
        
        # Načteme WAV audio
        audio_segment = AudioSegment.from_wav(io.BytesIO(audio_data))
        
        # Převedeme na 8kHz mono
        audio_segment = audio_segment.set_frame_rate(8000).set_channels(1)
        
        # Převedeme na μ-law
        raw_audio = audio_segment.raw_data
        mulaw_audio = audioop.lin2ulaw(raw_audio, 2)  # 2 bytes per sample
        
        return mulaw_audio
    except Exception as e:
        logger.error(f"Chyba při převodu WAV na μ-law: {e}")
        return b""

async def send_tts_to_twilio(websocket: WebSocket, text: str, stream_sid: str, client):
    """Odešle TTS audio do Twilio WebSocket streamu"""
    try:
        # Kontrola jestli je WebSocket stále připojen
        try:
            # Ping test pro ověření připojení
            await websocket.ping()
            logger.debug("TTS: WebSocket ping OK")
        except Exception as ping_error:
            logger.warning(f"TTS: WebSocket ping failed: {ping_error}")
            logger.warning("WebSocket není připojen, přeskakujem TTS")
            return
            
        logger.info(f"🔊 Generuji TTS pro text: '{text[:50]}...'")
        
        # Generace TTS pomocí OpenAI
        response = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
            response_format="wav"
        )
        
        # Převod na G.711 μ-law pro Twilio
        audio_data = response.content
        
        # Zde by měla být konverze na G.711, ale pro jednoduchost použijeme base64
        import base64
        audio_b64 = base64.b64encode(audio_data).decode()
        
        # Rozdělíme na chunky a pošleme
        chunk_size = 1000  # Base64 chunky
        for i in range(0, len(audio_b64), chunk_size):
            chunk = audio_b64[i:i+chunk_size]
            
            media_message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": chunk
                }
            }
            
            if stream_sid:  # Pouze pokud máme stream_sid
                await websocket.send_text(json.dumps(media_message))
                await asyncio.sleep(0.05)  # 50ms mezi chunky
        
        logger.info("✅ TTS audio odesláno")
        
    except Exception as e:
        logger.error(f"Chyba při TTS: {e}")

async def process_audio_chunk(websocket: WebSocket, audio_data: bytes, 
                             stream_sid: str, client, assistant_id: str, thread_id: str):
    """Zpracuje audio chunk pomocí OpenAI Assistant API v real-time"""
    try:
        if len(audio_data) < 1000:  # Příliš malý chunk, ignorujeme
            return
            
        logger.info(f"🎧 Zpracovávám audio chunk ({len(audio_data)} bajtů)")
        
        # Uložíme audio do dočasného souboru
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            # Vytvoříme jednoduchý WAV header pro μ-law audio
            import struct
            
            # WAV header pro μ-law, 8kHz, mono
            wav_header = struct.pack('<4sI4s4sIHHIIHH4sI',
                b'RIFF', len(audio_data) + 44 - 8,  # File size
                b'WAVE',
                b'fmt ', 16,  # Format chunk size
                7,  # μ-law format
                1,  # Mono
                8000,  # Sample rate
                8000,  # Byte rate
                1,  # Block align
                8,  # Bits per sample
                b'data', len(audio_data)
            )
            
            tmp_file.write(wav_header)
            tmp_file.write(audio_data)
            tmp_file_path = tmp_file.name
        
        try:
            # OpenAI Whisper pro STT
            with open(tmp_file_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="cs"
                )
            
            user_text = transcript.text.strip()
            logger.info(f"📝 Transkripce: '{user_text}'")
            
            if not user_text or len(user_text) < 3:
                logger.info("Příliš krátká transkripce, ignoruji")
                return
            
            # Přidáme zprávu do threadu
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_text
            )
            
            # Spustíme asistenta
            run = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )
            
            # Čekáme na dokončení (s timeout)
            import time
            max_wait = 15  # 15 sekund timeout pro rychlejší odpověď
            start_time = time.time()
            
            while run.status in ["queued", "in_progress"] and (time.time() - start_time) < max_wait:
                await asyncio.sleep(0.5)  # Kratší interval pro rychlejší odpověď
                run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            
            if run.status == "completed":
                # Získáme nejnovější odpověď
                messages = client.beta.threads.messages.list(thread_id=thread_id, limit=1)
                
                for message in messages.data:
                    if message.role == "assistant":
                        for content in message.content:
                            if content.type == "text":
                                assistant_response = content.text.value
                                logger.info(f"🤖 Assistant odpověď: '{assistant_response}'")
                                
                                # Pošleme jako TTS
                                await send_tts_to_twilio(websocket, assistant_response, stream_sid, client)
                                return
                
                logger.warning("Žádná assistant odpověď nenalezena")
            else:
                logger.warning(f"Assistant run neúspěšný: {run.status}")
                
        finally:
            # Vyčistíme dočasný soubor
            import os
            try:
                os.unlink(tmp_file_path)
            except:
                pass
                
    except Exception as e:
        logger.error(f"Chyba při zpracování audio: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

@app.websocket("/audio-test")
async def audio_stream_test(websocket: WebSocket):
    """Jednoduchý test WebSocket handler bez OpenAI připojení"""
    await websocket.accept()
    logger.info("=== AUDIO TEST WEBSOCKET HANDLER SPUŠTĚN ===")
    
    try:
        while True:
            # Čekáme na zprávu od klienta
            data = await websocket.receive_text()
            logger.info(f"Přijata zpráva: {data[:100]}...")
            
            # Parsujeme JSON
            try:
                message = json.loads(data)
                event_type = message.get("event", "unknown")
                logger.info(f"Event type: {event_type}")
                
                if event_type == "start":
                    logger.info("Start event - odesílám odpověď")
                    response = {
                        "event": "test_response",
                        "message": "Test WebSocket funguje!"
                    }
                    await websocket.send_text(json.dumps(response))
                    
                elif event_type == "media":
                    logger.info("Media event - ignoruji")
                    
                elif event_type == "stop":
                    logger.info("Stop event - ukončuji")
                    break
                    
            except json.JSONDecodeError as e:
                logger.error(f"Chyba při parsování JSON: {e}")
                
    except WebSocketDisconnect:
        logger.info("WebSocket odpojení")
    except Exception as e:
        logger.error(f"Chyba v test handleru: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    finally:
        logger.info("=== AUDIO TEST WEBSOCKET HANDLER UKONČEN ===")

@app.websocket("/audio")
async def audio_stream(websocket: WebSocket):
    """WebSocket endpoint pro Twilio Media Stream s robustním connection managementem"""
    
    # KRITICKÉ: Musíme nejprve přijmout WebSocket připojení
    await websocket.accept()
    logger.info("DEBUG: WebSocket connection accepted.")
    
    # Inicializace OpenAI klienta
    openai_api_key = os.getenv('OPENAI_API_KEY')
    if not openai_api_key:
        logger.error("OPENAI_API_KEY není nastaven")
        await websocket.close()
        return
        
    import openai
    client = openai.OpenAI(api_key=openai_api_key)
    
    # Vytvoříme nového assistanta s českými instrukcemi pro výuku jazyků
    try:
        assistant = client.beta.assistants.create(
            name="AI Asistent pro výuku jazyků",
            instructions="""Jsi AI asistent pro výuku jazyků. Komunikuješ POUZE v češtině.

TVOJE ROLE:
- Pomáháš studentům s výukou jazyků
- Mluvíš pouze česky, přirozeně a srozumitelně
- Jsi trpělivý, povzbuzující a přátelský
- Odpovídáš stručně a jasně

TVOJE ÚKOLY:
- Odpovídej na otázky studentů
- Vysvětluj jazykové koncepty
- Poskytuj zpětnou vazbu na odpovědi
- Kladeš jednoduché otázky pro ověření porozumění
- Buď konstruktivní a motivující

STYL KOMUNIKACE:
- Používej přirozený konverzační styl
- Krátké, srozumitelné věty
- Pozitivní přístup
- Pokud student něco neví, vysvětli to jednoduše

Vždy zůstávej v roli učitele jazyků a komunikuj pouze v češtině.""",
            model="gpt-4-1106-preview",
            tools=[]
        )
        assistant_id = assistant.id
        logger.info(f"✅ Vytvořen nový Assistant: {assistant_id}")
    except Exception as e:
        logger.error(f"Chyba při vytváření Assistanta: {e}")
        # Fallback na existující Assistant
        assistant_id = "asst_W6120kPP1lLBzU5OQLYvH6W1"
        logger.info(f"🔄 Používám existující Assistant: {assistant_id}")
    
    thread = None
    
    try:
        logger.info("=== AUDIO WEBSOCKET HANDLER SPUŠTĚN ===")
        
        # Vytvoříme nový thread pro konverzaci
        thread = client.beta.threads.create()
        logger.info(f"✅ Thread vytvořen: {thread.id}")
        
        # Inicializace proměnných
        stream_sid = None
        audio_buffer = bytearray()
        
        # Úvodní zpráva - počkáme na stream_sid
        initial_message = "Ahoj! Jsem AI asistent pro výuku jazyků. Jak vám mohu pomoci?"
        initial_message_sent = False
        
        # Keepalive task pro udržení WebSocket připojení
        keepalive_task = None
        websocket_active = True  # Flag pro sledování stavu připojení
        
        async def keepalive_sender():
            """Periodicky odesílá keepalive zprávy"""
            nonlocal websocket_active
            try:
                while websocket_active:
                    await asyncio.sleep(10)  # Každých 10 sekund
                    
                    if not websocket_active:
                        logger.info("💓 WebSocket neaktivní, ukončujem keepalive")
                        break
                        
                    if stream_sid:
                        try:
                            # Pošleme prázdný media chunk jako keepalive
                            keepalive_msg = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": ""  # Prázdný payload
                                }
                            }
                            await websocket.send_text(json.dumps(keepalive_msg))
                            logger.info("💓 Keepalive odesláno")
                        except Exception as send_error:
                            logger.error(f"💓 Keepalive send error: {send_error}")
                            websocket_active = False
                            break
            except Exception as e:
                logger.error(f"Keepalive chyba: {e}")
        
        # Hlavní smyčka pro zpracování WebSocket zpráv
        while websocket_active:
            try:
                logger.info("DEBUG: Čekám na WebSocket data...")
                
                # Kontrola stavu WebSocket před čtením
                try:
                    # Pokusíme se o rychlý ping test
                    await websocket.ping()
                    logger.debug("DEBUG: WebSocket ping OK")
                except Exception as ping_error:
                    logger.info(f"DEBUG: WebSocket ping failed: {ping_error}")
                    logger.info("DEBUG: WebSocket je pravděpodobně zavřen, ukončujem smyčku")
                    websocket_active = False
                    break
                
                data = await websocket.receive_text()
                logger.info(f"DEBUG: Přijata data: {data[:100]}...")
                
                msg = json.loads(data)
                event = msg.get("event")
                logger.info(f"DEBUG: Event typ: {event}")
                
                if event == "start":
                    logger.info("=== MEDIA STREAM START EVENT PŘIJAT! ===")
                    stream_sid = msg.get("streamSid")
                    logger.info(f"Stream SID: {stream_sid}")
                    
                    # Spustíme keepalive task
                    if not keepalive_task:
                        keepalive_task = asyncio.create_task(keepalive_sender())
                        logger.info("💓 Keepalive task spuštěn")
                    
                    # Pošleme úvodní zprávu nyní když máme stream_sid
                    if not initial_message_sent:
                        await asyncio.sleep(2)  # Krátká pauza po uvítání
                        await send_tts_to_twilio(websocket, initial_message, stream_sid, client)
                        initial_message_sent = True
                    
                elif event == "media":
                    payload = msg["media"]["payload"]
                    track = msg["media"]["track"]
                    
                    if track == "inbound":
                        # Real-time zpracování - zpracujeme audio ihned
                        audio_data = base64.b64decode(payload)
                        audio_buffer.extend(audio_data)
                        
                        # Zpracujeme audio každých 2 sekundy (cca 160 chunků)
                        if len(audio_buffer) >= 3200:  # ~2 sekundy audio při 8kHz
                            logger.info(f"🎧 Zpracovávám audio chunk ({len(audio_buffer)} bajtů)")
                            
                            # Zpracujeme audio v background tasku
                            asyncio.create_task(
                                process_audio_chunk(
                                    websocket, bytes(audio_buffer), stream_sid, 
                                    client, assistant_id, thread.id
                                )
                            )
                            
                            # Vymažeme buffer
                            audio_buffer.clear()
                        
                elif event == "stop":
                    logger.info("Media Stream ukončen")
                    websocket_active = False
                    
                    # Zpracujeme zbývající audio
                    if audio_buffer:
                        await process_audio_chunk(
                            websocket, bytes(audio_buffer), stream_sid, 
                            client, assistant_id, thread.id
                        )
                    break
                    
            except json.JSONDecodeError as e:
                logger.error(f"DEBUG: Neplatný JSON z Twilia: {e}")
            except RuntimeError as e:
                if "Need to call \"accept\" first" in str(e):
                    logger.error(f"DEBUG: WebSocket nebyl přijat nebo byl zavřen: {e}")
                else:
                    logger.error(f"DEBUG: WebSocket runtime error: {e}")
                websocket_active = False
                break
            except Exception as e:
                error_msg = str(e)
                logger.error(f"DEBUG: Chyba při zpracování zprávy: {error_msg}")
                
                # Zkontrolujeme různé typy WebSocket chyb
                if any(keyword in error_msg.lower() for keyword in [
                    "websocket", "disconnect", "connection", "closed", "broken pipe"
                ]):
                    logger.info("DEBUG: Detekováno WebSocket odpojení")
                    websocket_active = False
                    break
                    
                # Pro ostatní chyby pokračujeme
                continue
                    
    except Exception as e:
        logger.error(f"Chyba v Assistant API handleru: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    finally:
        # Označíme WebSocket jako neaktivní
        if 'websocket_active' in locals():
            websocket_active = False
        
        # Vyčistíme keepalive task
        if 'keepalive_task' in locals() and keepalive_task and not keepalive_task.done():
            keepalive_task.cancel()
            logger.info("💓 Keepalive task ukončen")
        
        # Vyčistíme thread
        if thread:
            try:
                client.beta.threads.delete(thread.id)
                logger.info(f"Thread {thread.id} smazán")
            except:
                pass
        
        logger.info("=== AUDIO WEBSOCKET HANDLER UKONČEN ===")

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
    
    async def safe_send_text(msg):
        try:
            await websocket.send_text(msg)
        except Exception as e:
            logger.error(f"[safe_send_text] WebSocket není připojen: {e}")

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

# Konfigurace pro produkci s delšími WebSocket timeouty
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        ws_ping_interval=30,  # Ping každých 30 sekund
        ws_ping_timeout=10,   # Timeout pro ping odpověď 10 sekund
        timeout_keep_alive=65  # Keep-alive timeout 65 sekund
    ) 