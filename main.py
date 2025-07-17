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
    # Validace (základní)
    if not name:
        errors["name"].append("Jméno je povinné.")
    if not phone or not (phone.startswith("+420") or phone.startswith("0")) or len(phone.replace(" ", "")) < 9:
        errors["phone"].append("Telefon musí být ve formátu +420XXXXXXXXX nebo 0XXXXXXXXX")
    if language not in ["cs", "en"]:
        errors["language"].append("Neplatný jazyk.")
    if any(errors.values()):
        # Zobrazit formulář s chybami
        return templates.TemplateResponse("users/form.html", {"request": request, "user": None, "form": {"name": name, "phone": phone, "language": language, "detail": detail, "name.errors": errors["name"], "phone.errors": errors["phone"], "language.errors": errors["language"], "detail.errors": errors["detail"]}})
    # Uložení do DB
    user = User(name=name, phone=phone, language=language, detail=detail)
    session = SessionLocal()
    session.add(user)
    session.commit()
    session.close()
    # Přesměrování na seznam uživatelů
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.get("/users/{id}/edit", response_class=HTMLResponse, name="admin_edit_user_get")
def admin_edit_user_get(request: Request, id: int = Path(...)):
    user = User.query.get(id) if hasattr(User, 'query') else None
    if not user:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)
    form = {"name": user.name, "phone": user.phone, "language": user.language, "detail": user.detail, "name.errors": [], "phone.errors": [], "language.errors": [], "detail.errors": []}
    return templates.TemplateResponse("users/form.html", {"request": request, "user": user, "form": form})

@admin_router.post("/users/{id}/edit", response_class=HTMLResponse)
def admin_edit_user_post(request: Request, id: int = Path(...), name: str = Form(...), phone: str = Form(...), language: str = Form(...), detail: str = Form("")):
    user = User.query.get(id) if hasattr(User, 'query') else None
    if not user:
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
        return templates.TemplateResponse("users/form.html", {"request": request, "user": user, "form": form})
    user.name = name
    user.phone = phone
    user.language = language
    user.detail = detail
    session = SessionLocal()
    session.commit()
    session.close()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.post("/users/{user_id}/delete", name="admin_delete_user")
def admin_delete_user(user_id: int = Path(...)):
    user = User.query.get(user_id) if hasattr(User, 'query') else None
    if user:
        session = SessionLocal()
        session.delete(user)
        session.commit()
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
    session.close()
    if not lesson:
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)
    try:
        from app.services.twilio_service import TwilioService
        twilio = TwilioService()
        base_url = os.getenv("WEBHOOK_BASE_URL", "https://lecture-app-production.up.railway.app")
        webhook_url = f"{base_url.rstrip('/')}/voice/?attempt_id={user.id}"
        twilio.call(user.phone, webhook_url)
    except Exception as e:
        print(f"Chyba při volání Twilio: {e}")
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
    session.commit()
    session.close()
    return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)

@admin_router.get("/lessons/{id}/edit", response_class=HTMLResponse, name="admin_edit_lesson_get")
def admin_edit_lesson_get(request: Request, id: int = Path(...)):
    lesson = Lesson.query.get(id) if hasattr(Lesson, 'query') else None
    if not lesson:
        return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)
    form = {"title": lesson.title, "language": lesson.language, "script": lesson.script, "questions": lesson.questions, "title.errors": [], "language.errors": [], "script.errors": [], "questions.errors": []}
    return templates.TemplateResponse("lessons/form.html", {"request": request, "lesson": lesson, "form": form})

@admin_router.post("/lessons/{id}/edit", response_class=HTMLResponse)
def admin_edit_lesson_post(request: Request, id: int = Path(...), title: str = Form(...), language: str = Form(...), script: str = Form(...), questions: str = Form("")):
    lesson = Lesson.query.get(id) if hasattr(Lesson, 'query') else None
    if not lesson:
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
        return templates.TemplateResponse("lessons/form.html", {"request": request, "lesson": lesson, "form": form})
    lesson.title = title
    lesson.language = language
    lesson.script = script
    lesson.questions = questions
    session = SessionLocal()
    session.commit()
    session.close()
    return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)

@admin_router.post("/lessons/{lesson_id}/delete", name="admin_delete_lesson")
def admin_delete_lesson(lesson_id: int = Path(...)):
    lesson = Lesson.query.get(lesson_id) if hasattr(Lesson, 'query') else None
    if lesson:
        session = SessionLocal()
        session.delete(lesson)
        session.commit()
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

@app.get("/health")
def health():
    return {"status": "healthy", "service": "lecture-app"}

@app.post("/voice/")
async def voice(request: Request, attempt_id: str = Query(None)):
    logger.info("Přijat Twilio webhook na /voice/")
    logger.info(f"Attempt ID: {attempt_id}")
    response = VoiceResponse()
    response.say(
        "Vítejte u AI asistenta pro výuku jazyků.",
        language="cs-CZ",
        voice="Google.cs-CZ-Standard-A",
        rate="0.9"
    )
    if attempt_id:
        # Zde by mělo být načtení lekce z DB, pro demo použijeme placeholder
        try:
            # attempt = Attempt.query.get(attempt_id)  # TODO: async DB
            # if attempt and attempt.lesson:
            #     lesson = attempt.lesson
            lesson = None  # TODO: nahradit skutečnou lekcí
            if lesson:
                response.say(
                    f"Začínáme s lekcí: {lesson.title}",
                    language="cs-CZ",
                    voice="Google.cs-CZ-Standard-A",
                    rate="0.9"
                )
                response.pause(length=1)
                response.say(
                    f"Téma lekce: {lesson.script[:200]}...",
                    language="cs-CZ",
                    voice="Google.cs-CZ-Standard-A",
                    rate="0.8"
                )
                response.pause(length=1)
            response.say(
                "Nyní vás připojuji k AI asistentovi, se kterým si můžete povídat o lekci.",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A",
                rate="0.9"
            )
            connect = Connect()
            stream = Stream(
                url=f"wss://lecture-app-production.up.railway.app/voice/media-stream?attempt_id={attempt_id}",
                track="both_tracks"
            )
            connect.append(stream)
            response.append(connect)
        except Exception as e:
            logger.error(f"Chyba při načítání lekce: {str(e)}")
            response.say(
                "Došlo k chybě při načítání lekce. Zkuste to prosím znovu.",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A"
            )
            response.hangup()
    else:
        response.say(
            "Připojuji vás k AI asistentovi pro obecnou konverzaci.",
            language="cs-CZ",
            voice="Google.cs-CZ-Standard-A",
            rate="0.9"
        )
        connect = Connect()
        stream = Stream(
            url=f"wss://lecture-app-production.up.railway.app/voice/media-stream",
            track="both_tracks"
        )
        connect.append(stream)
        response.append(connect)
    logger.info("TwiML odpověď:")
    logger.info(str(response))
    return Response(content=str(response), media_type="text/xml")

@app.websocket("/voice/media-stream")
async def media_stream(websocket: WebSocket):
    logger.info("Přijat WebSocket na /voice/media-stream")
    await websocket.accept()
    logger.info("WebSocket accepted, čekám na data z Twilia...")
    
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
        
    try:
        session = SessionLocal()
        attempt = session.query(Attempt).get(conversation_state["attempt_id"])
        
        if attempt and conversation_state["user_answers"]:
            # Výpočet celkového skóre
            total_score = sum(answer["score"] for answer in conversation_state["user_answers"])
            average_score = total_score / len(conversation_state["user_answers"])
            
            # Aktualizace pokusu
            attempt.score = average_score
            attempt.status = "completed"
            attempt.completed_at = datetime.now()
            attempt.calculate_next_due()
            
            # Uložení odpovědí
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
            
        session.close()
    except Exception as e:
        logger.error(f"Chyba při ukládání výsledků: {e}") 