import os
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import PlainTextResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from app.models import Attempt, Lesson, User, Answer, Base, TestSession
from sqlalchemy.orm import mapped_column
from fastapi import Query
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter, Form, status, Depends
from starlette.requests import Request
from typing import Optional
from fastapi import Path
import socket
import requests
from sqlalchemy import text
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
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Boolean, Float, ForeignKey, text
from sqlalchemy.orm import relationship
from sqlalchemy.orm.attributes import flag_modified
from fastapi.staticfiles import StaticFiles
from admin_dashboard import DashboardStats

load_dotenv()

# Základní konfigurace check - neblokuje startup
try:
    print("=== CONFIGURATION CHECK ===")
    missing_vars = []
    required_vars = ['DATABASE_URL', 'OPENAI_API_KEY']
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
            print(f"⚠️  Missing: {var}")
        else:
            print(f"✅ Found: {var}")
    
    if missing_vars:
        print(f"⚠️  WARNING: {len(missing_vars)} environment variables missing")
    else:
        print("✅ All critical env vars present")
    print("=== CONFIG CHECK COMPLETE ===")
except Exception as e:
    print(f"❌ Config check failed: {e}")

app = FastAPI(title="Lecture App", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Startup event handler pro diagnostiku - musí být rychlý pro health check
@app.on_event("startup")
async def startup_event():
    import sys
    print("=== LECTURE APP STARTUP ===")
    print(f"Python version: {sys.version}")
    print(f"PORT env var: {os.getenv('PORT', 'NOT SET')}")
    print(f"DATABASE_URL: {'SET' if os.getenv('DATABASE_URL') else 'NOT SET'}")
    print(f"OPENAI_API_KEY: {'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
    print(f"TWILIO_ACCOUNT_SID: {'SET' if os.getenv('TWILIO_ACCOUNT_SID') else 'NOT SET'}")
    
    # Otestuj základní importy asynchronně (neblokuj startup)
    try:
        import asyncio
        asyncio.create_task(test_connections_async())
    except Exception as e:
        print(f"⚠️  Async connection test failed: {e}")
    
    print("=== STARTUP COMPLETE ===")

async def test_connections_async():
    """Asynchronní test připojení - nesmí blokovat startup"""
    await asyncio.sleep(1)  # Dej čas na startup
    try:
        print("🔍 Testing DB connection...")
        from app.database import SessionLocal
        session = SessionLocal()
        session.close()
        print("✅ DB connection OK")
    except Exception as e:
        print(f"❌ DB connection failed: {e}")
    
    try:
        print("🔍 Testing OpenAI...")
        import openai
        print("✅ OpenAI import OK")
    except Exception as e:
        print(f"❌ OpenAI import failed: {e}")

# CORS (pro případné admin rozhraní)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DEBUG middleware pro WebSocket
@app.middleware("http")
async def debug_middleware(request: Request, call_next):
    print(f"🔍 MIDDLEWARE: {request.method} {request.url}")
    if request.url.path == "/audio":
        print("🎯 MIDDLEWARE: Detekován /audio request!")
    response = await call_next(request)
    return response

# Nastavení šablon
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'app', 'templates')
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Admin router
admin_router = APIRouter(prefix="/admin", tags=["admin"])
system_router = APIRouter(prefix="/admin/system", tags=["system"]) # Nový router

@admin_router.get("/", response_class=HTMLResponse)
def admin_root(request: Request):
    # Přesměrování na dashboard
    return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)

@admin_router.get("/dashboard", response_class=HTMLResponse, name="admin_dashboard")
def admin_dashboard(request: Request):
    stats_generator = DashboardStats()
    overview_stats = stats_generator.get_overview_stats()
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "stats": overview_stats
    })

@admin_router.get("/users", response_class=HTMLResponse, name="admin_list_users")
def admin_list_users(request: Request):
    session = SessionLocal()
    try:
        users = session.query(User).all()
        
        # Zajisti, že všichni uživatelé mají current_lesson_level
        for user in users:
            if not hasattr(user, 'current_lesson_level') or user.current_lesson_level is None:
                user.current_lesson_level = 0
        
        return templates.TemplateResponse("admin/users_list.html", {"request": request, "users": users})
    except Exception as e:
        logger.error(f"❌ Kritická chyba v admin_list_users: {e}")
        session.rollback() # Důležitý rollback
        
        # Fallback - prázdný seznam
        return templates.TemplateResponse("admin/users_list.html", {"request": request, "users": [], "error": str(e)})
    finally:
        session.close()

@admin_router.get("/users/new", response_class=HTMLResponse, name="admin_new_user_get")
def admin_new_user_get(request: Request):
    # Prázdný formulář pro nového uživatele
    return templates.TemplateResponse("admin/user_form.html", {"request": request, "user": None, "form": {"name": "", "phone": "", "language": "cs", "detail": "", "name.errors": [], "phone.errors": [], "language.errors": [], "detail.errors": []}})

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
        return templates.TemplateResponse("admin/user_form.html", {"request": request, "user": None, "form": {"name": name, "phone": phone, "language": language, "detail": detail, "name.errors": errors["name"], "phone.errors": errors["phone"], "language.errors": errors["language"], "detail.errors": errors["detail"]}})
    user = User(name=name, phone=phone, language=language, detail=detail)
    # Dočasně bez current_lesson_level
    session = SessionLocal()
    session.add(user)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        form = {"name": name, "phone": phone, "language": language, "detail": detail, "name.errors": [str(e)], "phone.errors": [], "language.errors": [], "detail.errors": []}
        session.close()
        return templates.TemplateResponse("admin/user_form.html", {"request": request, "user": None, "form": form})
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
    return templates.TemplateResponse("admin/user_form.html", {"request": request, "user": user, "form": form})

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
        return templates.TemplateResponse("admin/user_form.html", {"request": request, "user": user, "form": form})
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
        return templates.TemplateResponse("admin/user_form.html", {"request": request, "user": user, "form": form})
    session.close()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.post("/users/{user_id}/delete", name="admin_delete_user")
def admin_delete_user(request: Request, user_id: int = Path(...), force: bool = Query(False)):
    session = SessionLocal()
    try:
        user = session.query(User).get(user_id)
        if not user:
            logger.warning(f"❌ Pokus o smazání neexistujícího uživatele ID: {user_id}")
            return templates.TemplateResponse("message.html", {
                "request": request,
                "message": f"❌ Uživatel s ID {user_id} nebyl nalezen.",
                "back_url": "/admin/users",
                "back_text": "Zpět na uživatele"
            })
        
        # Zkontroluj závislé záznamy
        test_sessions_count = session.query(TestSession).filter(TestSession.user_id == user_id).count()
        attempts_count = session.query(Attempt).filter(Attempt.user_id == user_id).count()
        
        if (test_sessions_count > 0 or attempts_count > 0) and not force:
            logger.warning(f"❌ Nelze smazat uživatele {user.name} (ID: {user_id}) - má {test_sessions_count} test sessions a {attempts_count} pokusů")
            
            # Nabídni možnost vynutit smazání
            force_delete_url = f"/admin/users/{user_id}/delete?force=true"
            return templates.TemplateResponse("message.html", {
                "request": request,
                "message": f"❌ Uživatel '{user.name}' má související záznamy:\n\n• {test_sessions_count} aktivních testů\n• {attempts_count} pokusů\n\nChcete pokračovat a smazat uživatele i se všemi souvisejícími záznamy?",
                "back_url": "/admin/users",
                "back_text": "Zrušit",
                "action_url": force_delete_url,
                "action_text": "Vynutit smazání",
                "action_class": "btn-danger"
            })
        
        # Pokud force=true, smaž všechny související záznamy
        if force and (test_sessions_count > 0 or attempts_count > 0):
            logger.info(f"🔥 VYNUTIT SMAZÁNÍ: Mazání {test_sessions_count} test sessions a {attempts_count} pokusů pro uživatele {user.name}")
            
            # Smaž všechny test sessions
            session.query(TestSession).filter(TestSession.user_id == user_id).delete()
            
            # Smaž všechny attempts (a jejich answers se smažou automaticky díky cascade)
            session.query(Attempt).filter(Attempt.user_id == user_id).delete()
            
            logger.info(f"✅ Všechny související záznamy pro uživatele {user.name} byly smazány")
        
        # Smazání uživatele
        user_name = user.name
        session.delete(user)
        session.commit()
        
        logger.info(f"✅ Uživatel '{user_name}' (ID: {user_id}) byl úspěšně smazán")
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"✅ Uživatel '{user_name}' byl úspěšně smazán.",
            "back_url": "/admin/users",
            "back_text": "Zpět na uživatele"
        })
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Chyba při mazání uživatele ID {user_id}: {str(e)}")
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"❌ Chyba při mazání uživatele: {str(e)}",
            "back_url": "/admin/users",
            "back_text": "Zpět na uživatele"
        })
    finally:
        session.close()

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

@admin_router.post("/users/{user_id}/call/lesson/{lesson_number}", name="admin_call_user_lesson")
def admin_call_user_lesson(user_id: int = Path(...), lesson_number: int = Path(...)):
    """Zavolá uživateli s konkrétní lekcí podle čísla lekce"""
    session = SessionLocal()
    try:
        user = session.query(User).get(user_id)
        if not user:
            return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)
        
        # Najdi lekci podle čísla - FALLBACK na jakoukoliv lekci
        lesson = session.query(Lesson).filter_by(
            lesson_number=lesson_number,
            language=user.language
        ).first()
        
        # Fallback - pokud není lekce s číslem, vezmi první dostupnou
        if not lesson:
            logger.warning(f"Lekce {lesson_number} nenalezena, používám fallback")
            lesson = session.query(Lesson).filter_by(language=user.language).first()
        
        # Fallback - pokud není žádná lekce v jazyce, vezmi první lekci
        if not lesson:
            logger.warning(f"Žádná lekce v jazyce {user.language}, používám první dostupnou")
            lesson = session.query(Lesson).first()
        
        if not lesson:
            logger.error("Žádná lekce v databázi!")
            return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)
        
        # Vytvoření nového pokusu
        attempt = Attempt(
            user_id=user.id,
            lesson_id=lesson.id,
            next_due=datetime.now()
        )
        session.add(attempt)
        session.commit()
        
        # Volání přes Twilio
        from app.services.twilio_service import TwilioService
        twilio = TwilioService()
        base_url = os.getenv("WEBHOOK_BASE_URL", "https://lecture-app-production.up.railway.app")
        webhook_url = f"{base_url.rstrip('/')}/voice/?attempt_id={attempt.id}"
        
        logger.info(f"Volám uživatele {user.phone} s lekcí {lesson.id} (číslo {lesson_number}): {webhook_url}")
        twilio.call(user.phone, webhook_url)
        
    except Exception as e:
        logger.error(f"❌ KRITICKÁ CHYBA při volání s lekcí: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Fallback na původní funkci
        return admin_call_user(user_id)
    finally:
        session.close()
    
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.post("/users/{user_id}/advance", name="admin_advance_user")
def admin_advance_user(user_id: int = Path(...)):
    """Manuálně posune uživatele do další lekce"""
    session = SessionLocal()
    try:
        user = session.query(User).get(user_id)
        if not user:
            return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)
        
        # Bezpečná kontrola current_lesson_level
        if not hasattr(user, 'current_lesson_level') or user.current_lesson_level is None:
            user.current_lesson_level = 0
        
        if user.current_lesson_level < 10:
            user.current_lesson_level += 1
            
            # Bezpečné vytvoření progress záznamu
            try:
                from app.models import UserProgress
                progress = UserProgress(
                    user_id=user.id,
                    lesson_number=user.current_lesson_level - 1,  # Předchozí lekce je dokončena
                    is_completed=True,
                    best_score=95.0,  # Manuální postup = vysoké skóre
                    attempts_count=1,
                    first_completed_at=datetime.now()
                )
                session.add(progress)
            except Exception as progress_error:
                logger.warning(f"Chyba při vytváření progress záznamu: {progress_error}")
                # Pokračuj bez progress záznamu
            
            session.commit()
            logger.info(f"Uživatel {user.name} manuálně posunut na lekci {user.current_lesson_level}")
        
    except Exception as e:
        logger.error(f"❌ Chyba při posunu uživatele: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        session.rollback()
    finally:
        session.close()
    
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.post("/users/{user_id}/reset-test", name="admin_reset_test")
def admin_reset_test(user_id: int = Path(...)):
    """Resetuje test session pro uživatele"""
    session = SessionLocal()
    try:
        # Označ všechny aktivní test sessions jako dokončené
        active_sessions = session.query(TestSession).filter(
            TestSession.user_id == user_id,
            TestSession.is_completed == False
        ).all()
        
        for test_session in active_sessions:
            test_session.is_completed = True
            test_session.completed_at = datetime.utcnow()
        
        session.commit()
        logger.info(f"🔄 Admin resetoval test sessions pro uživatele {user_id}")
        return RedirectResponse(url="/admin/users", status_code=302)
    finally:
        session.close()

@admin_router.get("/create-lesson-0", name="admin_create_lesson_0")
def admin_create_lesson_0(request: Request):
    """Endpoint pro vytvoření Lekce 0 s 30 základními otázkami"""
    try:
        logger.info("🚀 Vytváření Lekce 0...")
        
        # 30 základních otázek z obráběcích kapalin a servisu
        questions = [
            {
                "number": 1,
                "question": "K čemu slouží obráběcí kapaliny při obrábění kovů?",
                "correct_answer": "K chlazení, mazání a odvodu třísek",
                "keywords": ["chlazení", "mazání", "třísky", "odvod"],
                "enabled": True
            },
            {
                "number": 2,
                "question": "Jaké jsou hlavní typy obráběcích kapalin?",
                "correct_answer": "Vodní roztoky, oleje a emulze",
                "keywords": ["vodní", "oleje", "emulze", "typy"],
                "enabled": True
            },
            {
                "number": 3,
                "question": "Proč je důležité pravidelně kontrolovat koncentraci emulze?",
                "correct_answer": "Pro zajištění správné funkce a předcházení bakteriálnímu růstu",
                "keywords": ["koncentrace", "funkce", "bakterie", "kontrola"],
                "enabled": True
            },
            {
                "number": 4,
                "question": "Jak se měří koncentrací obráběcí emulze?",
                "correct_answer": "Refraktometrem nebo titrací",
                "keywords": ["refraktometr", "titrace"],
                "enabled": True
            },
            {
                "number": 5,
                "question": "Jaká je optimální koncentrace pro většinu obráběcích emulzí?",
                "correct_answer": "3-8 procent",
                "keywords": ["3", "8", "procent", "koncentrace"],
                "enabled": True
            },
            {
                "number": 6,
                "question": "Co způsobuje pěnění obráběcích kapalin?",
                "correct_answer": "Vysoká rychlost oběhu, kontaminace nebo špatná koncentrace",
                "keywords": ["pěnění", "rychlost", "kontaminace", "koncentrace"],
                "enabled": True
            },
            {
                "number": 7,
                "question": "Jak často se má měnit obráběcí kapalina?",
                "correct_answer": "Podle stavu kapaliny, obvykle každé 2-6 měsíců",
                "keywords": ["měnit", "stav", "měsíc", "pravidelně"],
                "enabled": True
            },
            {
                "number": 8,
                "question": "Jaké jsou příznaky zkažené obráběcí kapaliny?",
                "correct_answer": "Zápach, změna barvy, pěnění nebo růst bakterií",
                "keywords": ["zápach", "barva", "pěnění", "bakterie"],
                "enabled": True
            },
            {
                "number": 9,
                "question": "Co je to pH obráběcí kapaliny a jaká má být hodnota?",
                "correct_answer": "Míra kyselosti, optimálně 8,5-9,5",
                "keywords": ["pH", "kyselost", "8,5", "9,5"],
                "enabled": True
            },
            {
                "number": 10,
                "question": "Proč je důležité udržovat správné pH?",
                "correct_answer": "Zabraňuje korozi a růstu bakterií",
                "keywords": ["koroze", "bakterie", "ochrana"],
                "enabled": True
            },
            {
                "number": 11,
                "question": "Jak se připravuje emulze z koncentrátu?",
                "correct_answer": "Koncentrát se přidává do vody, nikdy naopak",
                "keywords": ["koncentrát", "voda", "příprava", "pořadí"],
                "enabled": True
            },
            {
                "number": 12,
                "question": "Jaká je funkce biocidů v obráběcích kapalinách?",
                "correct_answer": "Zabíjejí bakterie a houby",
                "keywords": ["biocidy", "bakterie", "houby", "dezinfekce"],
                "enabled": True
            },
            {
                "number": 13,
                "question": "Co způsobuje korozi na obráběcích strojích?",
                "correct_answer": "Nízké pH, kontaminace nebo stará kapalina",
                "keywords": ["koroze", "pH", "kontaminace", "stará"],
                "enabled": True
            },
            {
                "number": 14,
                "question": "Jak se testuje kvalita obráběcí kapaliny?",
                "correct_answer": "Měření pH, koncentrace, čistoty a mikrobiologie",
                "keywords": ["pH", "koncentrace", "čistota", "mikrobiologie"],
                "enabled": True
            },
            {
                "number": 15,
                "question": "Jaké jsou bezpečnostní opatření při práci s obráběcími kapalinami?",
                "correct_answer": "Ochranné rukavice, brýle a větrání",
                "keywords": ["rukavice", "brýle", "větrání", "ochrana"],
                "enabled": True
            },
            {
                "number": 16,
                "question": "Co je filtrace obráběcích kapalin?",
                "correct_answer": "Odstranění nečistot a částic z kapaliny",
                "keywords": ["filtrace", "nečistoty", "částice", "čištění"],
                "enabled": True
            },
            {
                "number": 17,
                "question": "Proč se obráběcí kapaliny recyklují?",
                "correct_answer": "Kvůli úspoře nákladů a ochraně životního prostředí",
                "keywords": ["recyklace", "úspora", "prostředí", "náklady"],
                "enabled": True
            },
            {
                "number": 18,
                "question": "Jaká je role aditiv v obráběcích kapalinách?",
                "correct_answer": "Zlepšují vlastnosti jako mazání, ochranu před korozí",
                "keywords": ["aditiva", "mazání", "koroze", "vlastnosti"],
                "enabled": True
            },
            {
                "number": 19,
                "question": "Co je to EP přísada?",
                "correct_answer": "Extreme Pressure - přísada pro vysoké tlaky",
                "keywords": ["EP", "extreme", "pressure", "tlak"],
                "enabled": True
            },
            {
                "number": 20,
                "question": "Jak se likvidují použité obráběcí kapaliny?",
                "correct_answer": "Jako nebezpečný odpad ve specializovaných firmách",
                "keywords": ["likvidace", "nebezpečný", "odpad", "specializované"],
                "enabled": True
            },
            {
                "number": 21,
                "question": "Co způsobuje bakteriální růst v obráběcích kapalinách?",
                "correct_answer": "Vysoká teplota, nízké pH nebo kontaminace",
                "keywords": ["bakterie", "teplota", "pH", "kontaminace"],
                "enabled": True
            },
            {
                "number": 22,
                "question": "Jaké jsou výhody syntetických obráběcích kapalin?",
                "correct_answer": "Delší životnost, lepší čistota a stabilita",
                "keywords": ["syntetické", "životnost", "čistota", "stabilita"],
                "enabled": True
            },
            {
                "number": 23,
                "question": "Co je to mazací film?",
                "correct_answer": "Tenká vrstva kapaliny mezi nástrojem a obrobkem",
                "keywords": ["mazací", "film", "vrstva", "nástroj"],
                "enabled": True
            },
            {
                "number": 24,
                "question": "Proč je důležité chlazení při obrábění?",
                "correct_answer": "Zabraňuje přehřátí nástroje a obrobku",
                "keywords": ["chlazení", "přehřátí", "nástroj", "obrobek"],
                "enabled": True
            },
            {
                "number": 25,
                "question": "Co je to tramp oil?",
                "correct_answer": "Cizí olej kontaminující obráběcí kapalinu",
                "keywords": ["tramp", "oil", "cizí", "kontaminace"],
                "enabled": True
            },
            {
                "number": 26,
                "question": "Jak se odstraňuje tramp oil?",
                "correct_answer": "Skimmerem nebo separátorem oleje",
                "keywords": ["skimmer", "separátor", "odstranění"],
                "enabled": True
            },
            {
                "number": 27,
                "question": "Jaká je optimální teplota obráběcích kapalin?",
                "correct_answer": "20-35 stupňů Celsia",
                "keywords": ["teplota", "20", "35", "Celsius"],
                "enabled": True
            },
            {
                "number": 28,
                "question": "Co je to centrální systém obráběcích kapalin?",
                "correct_answer": "Systém zásobující více strojů z jednoho zdroje",
                "keywords": ["centrální", "systém", "více", "strojů"],
                "enabled": True
            },
            {
                "number": 29,
                "question": "Proč se kontroluje tvrdost vody pro přípravu emulzí?",
                "correct_answer": "Tvrdá voda může způsobit nestabilitu emulze",
                "keywords": ["tvrdost", "voda", "nestabilita", "emulze"],
                "enabled": True
            },
            {
                "number": 30,
                "question": "Co jsou to MWF (Metalworking Fluids)?",
                "correct_answer": "Obecný název pro všechny obráběcí kapaliny",
                "keywords": ["MWF", "metalworking", "fluids", "obecný"],
                "enabled": True
            }
        ]
        
        session = SessionLocal()
        
        # Zkontroluj, jestli už Lekce 0 neexistuje
        existing_lesson = session.query(Lesson).filter(Lesson.title.contains("Lekce 0")).first()
        if existing_lesson:
            session.close()
            return templates.TemplateResponse("message.html", {
                "request": request,
                "message": f"✅ Lekce 0 již existuje! (ID: {existing_lesson.id})",
                "back_url": "/admin/lessons",
                "back_text": "Zpět na lekce"
            })
        
        # Vytvoř novou lekci
        lesson = Lesson(
            title="Lekce 0: Vstupní test - Obráběcí kapaliny a servis",
            description="Základní test znalostí z oboru obráběcích kapalin a jejich servisu. Nutné dosáhnout 90% úspěšnosti pro postup do Lekce 1.",
            language="cs",
            script="",  # Prázdný script pro vstupní test
            questions=questions,
            level="entry_test"
        )
        
        session.add(lesson)
        session.commit()
        
        lesson_id = lesson.id
        session.close()
        
        logger.info(f"✅ Lekce 0 vytvořena s ID: {lesson_id}")
        
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"🎉 Lekce 0 úspěšně vytvořena!\n\n📝 ID: {lesson_id}\n📚 30 otázek z obráběcích kapalin\n🎯 Úroveň: Vstupní test",
            "back_url": "/admin/lessons",
            "back_text": "Zobrazit všechny lekce"
        })
        
    except Exception as e:
        logger.error(f"❌ Chyba při vytváření Lekce 0: {e}")
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"❌ Chyba při vytváření Lekce 0: {str(e)}",
            "back_url": "/admin/lessons",
            "back_text": "Zpět na lekce"
        })

@admin_router.get("/lessons", response_class=HTMLResponse, name="admin_list_lessons")
def admin_list_lessons(request: Request):
    session = SessionLocal()
    try:
        lessons = session.query(Lesson).order_by(Lesson.id.desc()).all()
        
        # Ošetření chybějících sloupců pro každou lekci v Pythonu, pokud by chyběly
        for lesson in lessons:
            if not hasattr(lesson, 'lesson_number'):
                lesson.lesson_number = 0
            if not hasattr(lesson, 'lesson_type'):
                lesson.lesson_type = 'standard'
            if not hasattr(lesson, 'required_score'):
                lesson.required_score = 90.0
            if not hasattr(lesson, 'description'):
                lesson.description = ''
                
        logger.info(f"✅ Načteno {len(lessons)} lekcí.")
        
        return templates.TemplateResponse("admin/lessons_list.html", {"request": request, "lessons": lessons})
        
    except Exception as e:
        logger.error(f"❌ KRITICKÁ CHYBA při načítání lekcí: {e}")
        session.rollback()  # Důležitý rollback pro vyčištění session
        
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"❌ Databázová chyba při načítání lekcí.\n\nChyba: {str(e)}\n\nZkuste obnovit stránku za chvíli.",
            "back_url": "/admin/dashboard",
            "back_text": "Zpět na dashboard"
        })
    finally:
        session.close()

@admin_router.get("/lessons/new", response_class=HTMLResponse, name="admin_new_lesson_get")
def admin_new_lesson_get(request: Request):
    form = {
        "title": "", "language": "cs", "script": "", "questions": "",
        "description": "", "lesson_number": "0", "lesson_type": "standard", "required_score": "90.0",
        "title.errors": [], "language.errors": [], "script.errors": [], "questions.errors": [],
        "description.errors": [], "lesson_number.errors": [], "lesson_type.errors": [], "required_score.errors": []
    }
    return templates.TemplateResponse("admin/lesson_form.html", {"request": request, "lesson": None, "form": form})

@admin_router.post("/lessons/new", response_class=HTMLResponse)
async def admin_new_lesson_post(request: Request):
    try:
        form_data = await request.form()
        
        title = form_data.get("title", "")
        language = form_data.get("language", "cs")
        script = form_data.get("script", "")
        questions = form_data.get("questions", "")
        description = form_data.get("description", "")
        lesson_number = form_data.get("lesson_number", "0")
        lesson_type = form_data.get("lesson_type", "standard")
        required_score = form_data.get("required_score", "90.0")
        
        errors = {"title": [], "language": [], "script": [], "questions": [], "lesson_number": [], "lesson_type": [], "required_score": [], "description": []}
        
        # Validace
        if not title:
            errors["title"].append("Název je povinný.")
        if language not in ["cs", "en"]:
            errors["language"].append("Neplatný jazyk.")
        if not script:
            errors["script"].append("Skript je povinný.")
        
        # Validace lesson_number
        try:
            lesson_number_int = int(lesson_number)
            if lesson_number_int < 0 or lesson_number_int > 100:
                errors["lesson_number"].append("Číslo lekce musí být mezi 0-100.")
        except ValueError:
            errors["lesson_number"].append("Číslo lekce musí být číslo.")
            lesson_number_int = 0
        
        # Validace required_score
        try:
            required_score_float = float(required_score)
            if required_score_float < 0 or required_score_float > 100:
                errors["required_score"].append("Skóre musí být mezi 0-100%.")
        except ValueError:
            errors["required_score"].append("Skóre musí být číslo.")
            required_score_float = 90.0
        
        if lesson_type not in ["entry_test", "standard", "advanced"]:
            errors["lesson_type"].append("Neplatný typ lekce.")
        
        if any(errors.values()):
            form = {
                "title": title, "language": language, "script": script, "questions": questions,
                "description": description, "lesson_number": lesson_number, "lesson_type": lesson_type, 
                "required_score": required_score,
                "title.errors": errors["title"], "language.errors": errors["language"], 
                "script.errors": errors["script"], "questions.errors": errors["questions"],
                "description.errors": errors["description"], "lesson_number.errors": errors["lesson_number"],
                "lesson_type.errors": errors["lesson_type"], "required_score.errors": errors["required_score"]
            }
            return templates.TemplateResponse("admin/lesson_form.html", {"request": request, "lesson": None, "form": form})
    
        # Vytvoření lekce
        lesson = Lesson(
            title=title,
            language=language,
            script=script,
            questions=questions,
            description=description,
            lesson_number=lesson_number_int,
            lesson_type=lesson_type,
            required_score=required_score_float
        )
        
        session = SessionLocal()
        session.add(lesson)
        try:
            session.commit()
            logger.info(f"✅ Nová lekce vytvořena: {title} (číslo={lesson_number_int}, typ={lesson_type})")
        except Exception as e:
            session.rollback()
            form = {
                "title": title, "language": language, "script": script, "questions": questions,
                "description": description, "lesson_number": lesson_number, "lesson_type": lesson_type,
                "required_score": required_score, "title.errors": [str(e)], "language.errors": [], 
                "script.errors": [], "questions.errors": [], "description.errors": [], 
                "lesson_number.errors": [], "lesson_type.errors": [], "required_score.errors": []
            }
            session.close()
            return templates.TemplateResponse("admin/lesson_form.html", {"request": request, "lesson": None, "form": form})
        session.close()
        return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)
        
    except Exception as e:
        logger.error(f"❌ Chyba při vytváření lekce: {e}")
        form = {
            "title": "", "language": "cs", "script": "", "questions": "",
            "description": "", "lesson_number": "0", "lesson_type": "standard", "required_score": "90.0",
            "title.errors": [f"Chyba: {str(e)}"], "language.errors": [], "script.errors": [], "questions.errors": [],
            "description.errors": [], "lesson_number.errors": [], "lesson_type.errors": [], "required_score.errors": []
        }
        return templates.TemplateResponse("admin/lesson_form.html", {"request": request, "lesson": None, "form": form})

@admin_router.get("/lessons/{id}/edit", response_class=HTMLResponse, name="admin_edit_lesson_get")
def admin_edit_lesson_get(request: Request, id: int = Path(...)):
    session = SessionLocal()
    lesson = session.query(Lesson).get(id)
    if not lesson:
        session.close()
        return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)
    
    # Pro Lekci 0 a nové lekce s otázkami použij novou template
    if lesson.title.startswith("Lekce 0") or (lesson.questions and isinstance(lesson.questions, list) and len(lesson.questions) > 0 and isinstance(lesson.questions[0], dict)):
        session.close()
        return templates.TemplateResponse("admin/lesson_edit.html", {"request": request, "lesson": lesson})
    
    # Pro staré lekce použij původní template s novými poli
    form = {
        "title": lesson.title, 
        "language": lesson.language, 
        "script": lesson.script, 
        "questions": lesson.questions,
        "description": getattr(lesson, 'description', ''),
        "lesson_number": getattr(lesson, 'lesson_number', 0),
        "lesson_type": getattr(lesson, 'lesson_type', 'standard'),
        "required_score": getattr(lesson, 'required_score', 90.0),
        "title.errors": [], "language.errors": [], "script.errors": [], "questions.errors": [],
        "description.errors": [], "lesson_number.errors": [], "lesson_type.errors": [], "required_score.errors": []
    }
    session.close()
    return templates.TemplateResponse("admin/lesson_form.html", {"request": request, "lesson": lesson, "form": form})

@admin_router.post("/lessons/{id}/edit", response_class=HTMLResponse)
async def admin_edit_lesson_post(request: Request, id: int = Path(...)):
    session = SessionLocal()
    lesson = session.query(Lesson).get(id)
    if not lesson:
        session.close()
        return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)
    
    try:
        form_data = await request.form()
        
        # Pro Lekci 0 a nové lekce s otázkami
        if lesson.title.startswith("Lekce 0") or (lesson.questions and isinstance(lesson.questions, list) and len(lesson.questions) > 0 and isinstance(lesson.questions[0], dict)):
            title = form_data.get("title", "")
            description = form_data.get("description", "")
            level = form_data.get("level", "beginner")
            enabled_questions = form_data.getlist("enabled_questions")
            
            logger.info(f"🔍 DEBUG: Přijato {len(enabled_questions)} aktivních otázek: {enabled_questions}")
            
            if not title:
                session.close()
                return templates.TemplateResponse("admin/lesson_edit.html", {
                    "request": request, 
                    "lesson": lesson, 
                    "error": "Název je povinný."
                })
            
            # Aktualizuj základní info
            lesson.title = title
            lesson.description = description
            lesson.level = level
            
            # Aktualizuj enabled stav otázek
            if lesson.questions and isinstance(lesson.questions, list):
                logger.info(f"🔍 DEBUG: Aktualizuji {len(lesson.questions)} otázek")
                for i, question in enumerate(lesson.questions):
                    if isinstance(question, dict):
                        old_enabled = question.get('enabled', True)
                        new_enabled = str(i) in enabled_questions
                        question['enabled'] = new_enabled
                        logger.info(f"🔍 DEBUG: Otázka {i}: {old_enabled} → {new_enabled}")
                
                # KRITICKÉ: Oznám SQLAlchemy, že se JSON sloupec změnil
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(lesson, 'questions')
                logger.info("🔍 DEBUG: flag_modified() zavolán pro questions sloupec")
            
            session.commit()
            logger.info(f"✅ Lekce {lesson.id} aktualizována: {len(enabled_questions)} aktivních otázek")
            session.close()
            return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)
        
        # Pro staré lekce - rozšířená logika s novými poli
        title = form_data.get("title", "")
        language = form_data.get("language", "cs")
        script = form_data.get("script", "")
        questions = form_data.get("questions", "")
        description = form_data.get("description", "")
        
        # Nová pole
        lesson_number = form_data.get("lesson_number", "0")
        lesson_type = form_data.get("lesson_type", "standard")
        required_score = form_data.get("required_score", "90.0")
        
        errors = {"title": [], "language": [], "script": [], "questions": [], "lesson_number": [], "lesson_type": [], "required_score": [], "description": []}
        
        # Validace
        if not title:
            errors["title"].append("Název je povinný.")
        if language not in ["cs", "en"]:
            errors["language"].append("Neplatný jazyk.")
        if not script:
            errors["script"].append("Skript je povinný.")
        
        # Validace lesson_number
        try:
            lesson_number_int = int(lesson_number)
            if lesson_number_int < 0 or lesson_number_int > 100:
                errors["lesson_number"].append("Číslo lekce musí být mezi 0-100.")
        except ValueError:
            errors["lesson_number"].append("Číslo lekce musí být číslo.")
            lesson_number_int = 0
        
        # Validace required_score
        try:
            required_score_float = float(required_score)
            if required_score_float < 0 or required_score_float > 100:
                errors["required_score"].append("Skóre musí být mezi 0-100%.")
        except ValueError:
            errors["required_score"].append("Skóre musí být číslo.")
            required_score_float = 90.0
        
        if lesson_type not in ["entry_test", "standard", "advanced"]:
            errors["lesson_type"].append("Neplatný typ lekce.")
        
        if any(errors.values()):
            form = {
                "title": title, "language": language, "script": script, "questions": questions,
                "description": description, "lesson_number": lesson_number, "lesson_type": lesson_type, 
                "required_score": required_score,
                "title.errors": errors["title"], "language.errors": errors["language"], 
                "script.errors": errors["script"], "questions.errors": errors["questions"],
                "description.errors": errors["description"], "lesson_number.errors": errors["lesson_number"],
                "lesson_type.errors": errors["lesson_type"], "required_score.errors": errors["required_score"]
            }
            session.close()
            return templates.TemplateResponse("admin/lesson_form.html", {"request": request, "lesson": lesson, "form": form})
        
        # Aktualizace lekce
        lesson.title = title
        lesson.language = language
        lesson.script = script
        lesson.questions = questions
        lesson.description = description
        lesson.lesson_number = lesson_number_int
        lesson.lesson_type = lesson_type
        lesson.required_score = required_score_float
        
        session.commit()
        logger.info(f"✅ Lekce {lesson.id} aktualizována: číslo={lesson_number_int}, typ={lesson_type}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Chyba při editaci lekce {id}: {e}")
        session.close()
        return templates.TemplateResponse("admin/lesson_edit.html", {
            "request": request, 
            "lesson": lesson, 
            "error": f"Chyba při ukládání: {str(e)}"
        })
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

@admin_router.get("/migrate-db", response_class=JSONResponse)
def admin_migrate_db():
    """Provede databázové migrace pro nové funkce"""
    session = SessionLocal()
    results = {"migrations": []}
    
    try:
        # 1. Přidej current_lesson_level do users
        try:
            session.execute(text("SELECT current_lesson_level FROM users LIMIT 1"))
            results["migrations"].append("current_lesson_level: již existuje")
        except Exception:
            try:
                session.execute(text("ALTER TABLE users ADD COLUMN current_lesson_level INTEGER DEFAULT 0"))
                session.commit()
                results["migrations"].append("current_lesson_level: ✅ přidán")
            except Exception as e:
                results["migrations"].append(f"current_lesson_level: ❌ {str(e)}")
                session.rollback()
        
        # 2. Přidej lesson_number do lessons
        try:
            session.execute(text("SELECT lesson_number FROM lessons LIMIT 1"))
            results["migrations"].append("lesson_number: již existuje")
        except Exception:
            try:
                session.execute(text("ALTER TABLE lessons ADD COLUMN lesson_number INTEGER DEFAULT 0"))
                session.execute(text("ALTER TABLE lessons ADD COLUMN required_score FLOAT DEFAULT 90.0"))
                session.execute(text("ALTER TABLE lessons ADD COLUMN lesson_type VARCHAR(20) DEFAULT 'standard'"))
                session.execute(text("ALTER TABLE lessons ADD COLUMN description TEXT"))
                session.commit()
                results["migrations"].append("lesson columns: ✅ přidány")
            except Exception as e:
                results["migrations"].append(f"lesson columns: ❌ {str(e)}")
                session.rollback()
        
        # 3. Vytvoř user_progress tabulku
        try:
            session.execute(text("SELECT id FROM user_progress LIMIT 1"))
            results["migrations"].append("user_progress: již existuje")
        except Exception:
            try:
                create_progress_table = """
                CREATE TABLE user_progress (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    lesson_number INTEGER NOT NULL,
                    is_completed BOOLEAN DEFAULT FALSE,
                    best_score FLOAT,
                    attempts_count INTEGER DEFAULT 0,
                    first_completed_at TIMESTAMP,
                    last_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                session.execute(text(create_progress_table))
                session.commit()
                results["migrations"].append("user_progress: ✅ vytvořena")
            except Exception as e:
                results["migrations"].append(f"user_progress: ❌ {str(e)}")
                session.rollback()
        
        results["status"] = "completed"
        
    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
        session.rollback()
    finally:
        session.close()
    
    return results

# NOVÉ ADMIN ENDPOINTY - MUSÍ BÝT PŘED REGISTRACÍ ROUTERU

@admin_router.get("/create-lesson-1", name="admin_create_lesson_1")
def admin_create_lesson_1(request: Request):
    """Endpoint pro vytvoření Lekce 1 - Základy obráběcích kapalin"""
    try:
        logger.info("🚀 Vytváření Lekce 1...")
        
        session = SessionLocal()
        
        # Zkontroluj, jestli už lekce 1 existuje
        existing_lesson = session.query(Lesson).filter(
            Lesson.title.contains("Lekce 1")
        ).first()
        
        if existing_lesson:
            session.close()
            return templates.TemplateResponse("message.html", {
                "request": request,
                "message": f"✅ Lekce 1 již existuje! (ID: {existing_lesson.id})",
                "back_url": "/admin/lessons",
                "back_text": "Zpět na lekce"
            })
        
        # Obsah lekce 1 - Základy obráběcích kapalin
        lesson_script = """
# Lekce 1: Základy obráběcích kapalin

## Úvod
Obráběcí kapaliny jsou nezbytnou součástí moderního obrábění kovů. Jejich správné použití a údržba výrazně ovlivňuje kvalitu výroby, životnost nástrojů a bezpečnost práce.

## Hlavní funkce obráběcích kapalin

### 1. Chlazení
- Odvod tepla vznikajícího při řezném procesu
- Zabránění přehřátí nástroje a obrobku
- Udržení stálé teploty řezné hrany

### 2. Mazání
- Snížení tření mezi nástrojem a obrobkem
- Zlepšení kvality povrchu
- Prodloužení životnosti nástroje

### 3. Odvod třísek
- Transport třísek pryč z místa řezu
- Zabránění zanášení nástroje
- Udržení čistoty řezné zóny

## Typy obráběcích kapalin

### Řezné oleje
- Vysoká mazací schopnost
- Použití při těžkém obrábění
- Nevhodné pro vysoké rychlosti

### Emulze (směsi oleje a vody)
- Kombinace mazání a chlazení
- Nejčastěji používané
- Koncentrace 3-8%

### Syntetické kapaliny
- Bez oleje, pouze chemické přísady
- Výborné chladicí vlastnosti
- Dlouhá životnost

## Kontrola a údržba

### Denní kontrola
- Měření koncentrace refraktometrem
- Kontrola pH hodnoty (8,5-9,5)
- Vizuální kontrola čistoty

### Týdenní údržba
- Doplnění kapaliny
- Odstranění nečistot
- Kontrola bakteriální kontaminace

### Měsíční servis
- Výměna filtrů
- Hloubková analýza
- Případná regenerace

## Bezpečnost
- Používání ochranných pomůcek
- Prevence kontaktu s kůží
- Správné skladování a likvidace

## Závěr
Správná práce s obráběcími kapalinami je základem efektivního obrábění. Pravidelná kontrola a údržba zajišťuje optimální výkon a bezpečnost provozu.
        """
        
        # Vytvoř lekci 1
        lesson = Lesson(
            title="Lekce 1: Základy obráběcích kapalin",
            description="Komplexní úvod do problematiky obráběcích kapalin - funkce, typy, kontrola a údržba.",
            language="cs",
            script=lesson_script,
            questions=[],  # Otázky se budou generovat dynamicky
            level="beginner"
        )
        
        session.add(lesson)
        session.commit()
        lesson_id = lesson.id
        session.close()
        
        logger.info(f"✅ Lekce 1 vytvořena s ID: {lesson_id}")
        
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"🎉 Lekce 1 úspěšně vytvořena!\n\n📝 ID: {lesson_id}\n📚 Obsah: Základy obráběcích kapalin\n🎯 Úroveň: Začátečník\n\n⚡ Otázky se generují automaticky při testování!",
            "back_url": "/admin/lessons",
            "back_text": "Zobrazit všechny lekce"
        })
        
    except Exception as e:
        logger.error(f"❌ Chyba při vytváření Lekce 1: {e}")
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"❌ Chyba při vytváření Lekce 1: {str(e)}",
            "back_url": "/admin/lessons",
            "back_text": "Zpět na lekce"
        })

@admin_router.get("/user-progress", response_class=HTMLResponse, name="admin_user_progress")
def admin_user_progress(request: Request):
    """Zobrazí pokrok všech uživatelů"""
    session = SessionLocal()
    try:
        users = session.query(User).all()
        
        # Připrav data o pokroku
        progress_data = []
        for user in users:
            user_level = getattr(user, 'current_lesson_level', 0)
            
            # Najdi název aktuální lekce
            current_lesson_name = "Vstupní test"
            if user_level == 1:
                current_lesson_name = "Lekce 1: Základy"
            elif user_level > 1:
                current_lesson_name = f"Lekce {user_level}"
            
            progress_data.append({
                'user': user,
                'level': user_level,
                'lesson_name': current_lesson_name,
                'attempts_count': len(user.attempts) if hasattr(user, 'attempts') else 0
            })
        
        session.close()
        return templates.TemplateResponse("admin/user_progress.html", {
            "request": request, 
            "progress_data": progress_data
        })
        
    except Exception as e:
        session.close()
        logger.error(f"❌ Chyba při načítání pokroku: {e}")
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"❌ Chyba při načítání pokroku uživatelů: {str(e)}",
            "back_url": "/admin/users",
            "back_text": "Zpět na uživatele"
        })

@admin_router.get("/lesson-0-questions", response_class=HTMLResponse, name="admin_lesson_0_questions")
def admin_lesson_0_questions(request: Request):
    """Zobrazení a editace otázek vstupního testu (Lekce 0)"""
    session = SessionLocal()
    try:
        # Najdi Lekci 0
        lesson_0 = session.query(Lesson).filter(Lesson.lesson_number == 0).first()
        
        if not lesson_0:
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Správa otázek - Lekce 0</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            </head>
            <body>
                <div class="container mt-4">
                    <h2>❌ Lekce 0 nebyla nalezena</h2>
                    <p>Nejprve vytvořte Lekci 0 pomocí <a href="/admin/create-lesson-0">tohoto odkazu</a>.</p>
                    <a href="/admin" class="btn btn-primary">← Zpět na admin</a>
                </div>
            </body>
            </html>
            """)
        
        questions = lesson_0.questions if isinstance(lesson_0.questions, list) else []
        
        # Vytvoření HTML tabulky s otázkami
        questions_html = ""
        for i, question in enumerate(questions):
            if isinstance(question, dict):
                question_text = question.get('question', 'N/A')
                correct_answer = question.get('correct_answer', 'N/A')
                keywords = ', '.join(question.get('keywords', []))
                enabled = question.get('enabled', True)
                
                questions_html += f"""
                <tr>
                    <td>{i + 1}</td>
                    <td>
                        <textarea class="form-control" name="question_{i}" rows="2">{question_text}</textarea>
                    </td>
                    <td>
                        <textarea class="form-control" name="answer_{i}" rows="2">{correct_answer}</textarea>
                    </td>
                    <td>
                        <input type="text" class="form-control" name="keywords_{i}" value="{keywords}" placeholder="klíčová slova oddělená čárkami">
                    </td>
                    <td>
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" name="enabled_{i}" {'checked' if enabled else ''}>
                        </div>
                    </td>
                </tr>
                """
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Správa otázek - Lekce 0</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <script src="https://unpkg.com/htmx.org@1.9.10"></script>
        </head>
        <body>
            <div class="container mt-4">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h2>📝 Správa otázek - Vstupní test (Lekce 0)</h2>
                    <a href="/admin" class="btn btn-secondary">← Zpět na admin</a>
                </div>
                
                <div class="alert alert-info">
                    <strong>💡 Tip:</strong> Můžete upravit otázky, správné odpovědi, klíčová slova a povolit/zakázat otázky.
                    Klíčová slova oddělujte čárkami (např. "refraktometr, titrace").
                </div>
                
                <form hx-post="/admin/lesson-0-questions" hx-target="#result" class="mb-4">
                    <div class="table-responsive">
                        <table class="table table-striped">
                            <thead class="table-dark">
                                <tr>
                                    <th>#</th>
                                    <th>Otázka</th>
                                    <th>Správná odpověď</th>
                                    <th>Klíčová slova</th>
                                    <th>Povoleno</th>
                                </tr>
                            </thead>
                            <tbody>
                                {questions_html}
                            </tbody>
                        </table>
                    </div>
                    
                    <div class="d-flex gap-2">
                        <button type="submit" class="btn btn-primary">
                            💾 Uložit změny
                        </button>
                        <a href="/admin/create-lesson-0" class="btn btn-warning">
                            🔄 Obnovit výchozí otázky
                        </a>
                    </div>
                </form>
                
                <div id="result"></div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Chyba při načítání otázek Lekce 0: {e}")
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Chyba</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-4">
                <div class="alert alert-danger">
                    <h4>❌ Chyba při načítání otázek</h4>
                    <p>{str(e)}</p>
                </div>
                <a href="/admin" class="btn btn-primary">← Zpět na admin</a>
            </div>
        </body>
        </html>
        """)
    finally:
        session.close()

@admin_router.post("/lesson-0-questions", response_class=HTMLResponse)
async def admin_lesson_0_questions_post(request: Request):
    """Uložení změn v otázkách vstupního testu"""
    session = SessionLocal()
    try:
        form = await request.form()
        
        # Najdi Lekci 0
        lesson_0 = session.query(Lesson).filter(Lesson.lesson_number == 0).first()
        if not lesson_0:
            return HTMLResponse(content="<div class='alert alert-danger'>❌ Lekce 0 nebyla nalezena</div>")
        
        # Získej aktuální otázky
        current_questions = lesson_0.questions if isinstance(lesson_0.questions, list) else []
        updated_questions = []
        
        # Zpracuj každou otázku
        for i, question in enumerate(current_questions):
            if isinstance(question, dict):
                # Získej hodnoty z formuláře
                question_text = form.get(f'question_{i}', question.get('question', ''))
                correct_answer = form.get(f'answer_{i}', question.get('correct_answer', ''))
                keywords_str = form.get(f'keywords_{i}', '')
                enabled = form.get(f'enabled_{i}') == 'on'
                
                # Zpracuj klíčová slova
                keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
                
                # Vytvoř aktualizovanou otázku
                updated_question = {
                    'number': i + 1,
                    'question': question_text,
                    'correct_answer': correct_answer,
                    'keywords': keywords,
                    'enabled': enabled
                }
                updated_questions.append(updated_question)
        
        # Ulož změny
        lesson_0.questions = updated_questions
        session.commit()
        
        return HTMLResponse(content=f"""
        <div class="alert alert-success">
            ✅ Otázky byly úspěšně uloženy! ({len(updated_questions)} otázek)
        </div>
        """)
        
    except Exception as e:
        logger.error(f"Chyba při ukládání otázek Lekce 0: {e}")
        session.rollback()
        return HTMLResponse(content=f"""
        <div class="alert alert-danger">
            ❌ Chyba při ukládání: {str(e)}
        </div>
        """)
    finally:
        session.close()

# Připojení admin routeru
app.include_router(admin_router)
app.include_router(system_router) # Připojení nového routeru

logger = logging.getLogger("uvicorn")

# PŘÍMÝ ENDPOINT NA HLAVNÍ APP - GARANTOVANĚ DOSTUPNÝ
@app.get("/admin/system/run-migrations", response_class=HTMLResponse)
def direct_run_migrations(request: Request):
    """
    PŘÍMÝ endpoint pro databázové migrace - registrovaný přímo na hlavní app.
    """
    session = SessionLocal()
    results = {"success": [], "errors": []}
    
    # Kompletní seznam migrací
    migrations = {
        "lessons": [
            ("base_difficulty", "VARCHAR(20)", "medium"),
        ],
        "test_sessions": [
            ("difficulty_score", "FLOAT", 50.0),
            ("failed_categories", "JSON", "[]"),
        ]
    }
    
    try:
        for table, columns in migrations.items():
            for column_name, column_type, default_value in columns:
                # Pro default hodnoty stringového typu potřebujeme uvozovky
                default_sql = f"'{default_value}'" if isinstance(default_value, str) else default_value
                
                try:
                    # Zkusit přidat sloupec
                    session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type} DEFAULT {default_sql}"))
                    session.commit()
                    results["success"].append(f"✅ Sloupec '{column_name}' úspěšně přidán do tabulky '{table}'.")
                except Exception as e:
                    # Pokud sloupec již existuje, ignorovat chybu
                    if "already exists" in str(e) or "duplicate column" in str(e):
                        results["success"].append(f"☑️ Sloupec '{column_name}' v tabulce '{table}' již existuje.")
                    else:
                        results["errors"].append(f"❌ Chyba při přidávání sloupce '{column_name}': {e}")
                    session.rollback() # Důležitý rollback po každé chybě
                    
        if not results["errors"]:
            message = "🎉 Všechny migrace proběhly úspěšně! Databáze je nyní synchronizována."
        else:
            message = "⚠️ Některé migrace selhaly. Zkontrolujte detaily níže."
            
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": message,
            "details": results,
            "back_url": "/admin/dashboard",
            "back_text": "Zpět na dashboard"
        })

    except Exception as e:
        session.rollback()
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"❌ Kritická chyba při migraci: {e}",
            "back_url": "/admin/dashboard",
            "back_text": "Zpět na dashboard"
        })
    finally:
        session.close()

@app.get("/")
async def root():
    """Health check endpoint - MUSÍ být rychlý pro Railway health check"""
    # Nejjednodušší možná odpověď - žádné importy, žádné databázové dotazy
    return {
        "status": "healthy",
        "message": "Lecture App FastAPI běží!",
        "port": os.getenv('PORT', '8000'),
        "time": str(datetime.now())
    }

@app.post("/")
async def root_post(request: Request, attempt_id: str = Query(None)):
    """Twilio někdy volá root endpoint místo /voice/ - použijeme stejnou logiku"""
    logger.info("Přijat Twilio webhook na ROOT / endpoint")
    logger.info(f"Attempt ID: {attempt_id}")
    
    # PŘESMĚRUJ NA /voice/ handler pro konzistentní chování
    logger.info("🔄 Přesměrovávám ROOT request na voice_handler")
    return await voice_handler(request)

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
    <Say language="cs-CZ" rate="0.9" voice="Google.cs-CZ-Standard-A">WebSocket test - pokud slyšíte tuto zprávu, HTTP funguje.</Say>
    <Say language="cs-CZ" rate="0.9" voice="Google.cs-CZ-Standard-A">Nyní testuji WebSocket připojení.</Say>
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
    attempt_id = request.query_params.get('attempt_id')
    logger.info(f"Attempt ID: {attempt_id}")
    
    # Získání parametrů hovoru
    form = await request.form()
    caller_country = form.get("CallerCountry", "")
    to_country = form.get("ToCountry", "")
    logger.info(f"Volající: {caller_country} -> {to_country}")
    
    response = VoiceResponse()
    
    # Inteligentní uvítání podle aktuální lekce uživatele
    session = SessionLocal()
    try:
        current_user = None
        current_lesson = None
        lesson_info = ""
        
        # Pokusíme se najít uživatele podle attempt_id
        if attempt_id:
            try:
                attempt = session.query(Attempt).get(int(attempt_id))
                if attempt:
                    current_user = attempt.user
                    current_lesson = attempt.lesson
            except:
                pass
        
        # Pokud není attempt, najdi posledního uživatele
        if not current_user:
            current_user = session.query(User).order_by(User.id.desc()).first()
        
        if current_user:
            # Získej aktuální úroveň uživatele
            user_level = getattr(current_user, 'current_lesson_level', 0)
            
            # Najdi správnou lekci podle úrovně
            if user_level == 0:
                target_lesson = session.query(Lesson).filter(
                    Lesson.lesson_number == 0
                ).first()
                if target_lesson:
                    lesson_info = f"Lekce {target_lesson.lesson_number}: Vstupní test z obráběcích kapalin. Hned začneme s testem!"
                else:
                    lesson_info = "Lekce 0: Vstupní test. Hned začneme!"
            else:
                target_lesson = session.query(Lesson).filter(
                    Lesson.lesson_number == user_level
                ).first()
                if target_lesson:
                    lesson_info = f"Lekce {target_lesson.lesson_number}: {target_lesson.title.replace(f'Lekce {target_lesson.lesson_number}:', '').strip()}. Začínáme s výukou!"
                else:
                    lesson_info = f"Lekce {user_level}. Začínáme s výukou!"
    except Exception as e:
        logger.error(f"Chyba při načítání lekce: {e}")
        lesson_info = "Lekce 0: Vstupní test. Hned začneme!"
    finally:
        session.close()
    
    # Nové, lepší uvítání s první otázkou (pokud je to nová session)
    if current_user and user_level == 0:
        # Pro vstupní test zkontroluj, jestli už existuje aktivní session
        test_session_check = session.query(TestSession).filter(
            TestSession.user_id == current_user.id,
            TestSession.lesson_id == target_lesson.id if target_lesson else None,
            TestSession.is_completed == False
        ).first()
        
        if not test_session_check and target_lesson:
            # NOVÁ SESSION - řekni uvítání + první otázku
            enabled_questions = []
            if isinstance(target_lesson.questions, list):
                enabled_questions = [
                    q for q in target_lesson.questions 
                    if isinstance(q, dict) and q.get('enabled', True)
                ]
            
            if enabled_questions:
                first_question = enabled_questions[0].get('question', '')
                full_intro = f"Ahoj, jsem tvůj lektor! Začínáme s {lesson_info} První otázka: {first_question}"
                # Přidej přirozenější pauzy do úvodní řeči
                intro_with_pauses = create_natural_speech_response(full_intro)
                response.say(intro_with_pauses, language="cs-CZ", rate="0.8", voice="Google.cs-CZ-Standard-A")
                logger.info(f"🎯 Úvodní otázka řečena v voice_handler: {first_question}")
            else:
                intro_text = f"Ahoj, jsem tvůj lektor! Začínáme s {lesson_info}"
                intro_with_pauses = create_natural_speech_response(intro_text)
                response.say(intro_with_pauses, language="cs-CZ", rate="0.8", voice="Google.cs-CZ-Standard-A")
        else:
            # EXISTUJÍCÍ SESSION - pouze uvítání
            existing_intro = "Ahoj, jsem tvůj lektor! Pokračujeme v testu."
            existing_intro_with_pauses = create_natural_speech_response(existing_intro)
            response.say(existing_intro_with_pauses, language="cs-CZ", rate="0.8", voice="Google.cs-CZ-Standard-A")
    else:
        # Běžné lekce
        lesson_intro = f"Ahoj, jsem tvůj lektor! Začínáme s {lesson_info}"
        lesson_intro_with_pauses = create_natural_speech_response(lesson_intro)
        response.say(lesson_intro_with_pauses, language="cs-CZ", rate="0.8", voice="Google.cs-CZ-Standard-A")
    
    # Kratší pauza a přechod do action
    response.pause(length=1)
    
    # Gather s vylepšenými parametry pro lepší detekci konce odpovědi
    gather = response.gather(
        input='speech',
        timeout=8,  # Kratší základní timeout
        speech_timeout=3,  # Konkrétní hodnota místo 'auto' pro lepší detekci konce
        action='/voice/process',
        method='POST',
        language='cs-CZ',
        speech_model='phone_call',
        partial_result_callback='',  # Zakážeme partial results pro čistší zpracování
        enhanced='true'  # Vylepšené rozpoznávání
    )
    
    gather.say(
        "Píp.",
        language="cs-CZ",
        rate="0.8",
        voice="Google.cs-CZ-Standard-A"
    )
    
    # Vylepšený fallback s možností připomenutí
    response.say(
        "Nerozuměl jsem vám nebo jste neodpověděl. Zkuste mluvit jasně a výrazně.",
        language="cs-CZ",
        rate="0.8",
        voice="Google.cs-CZ-Standard-A"
    )
    
    # Nabídka opakování
    response.redirect('/voice/process?reminder=true')
    
    logger.info(f"TwiML odpověď s inteligentním uvítáním: {response}")
    return Response(content=str(response), media_type="text/xml")

@app.post("/voice/process")
async def process_speech(request: Request):
    """Vylepšené zpracování hlasového vstupu s inteligentním flow"""
    logger.info("🎙️ === PROCESS_SPEECH START ===")
    
    form = await request.form()
    speech_result = form.get('SpeechResult', '').strip()
    confidence = form.get('Confidence', '0')
    attempt_id = request.query_params.get('attempt_id')
    is_reminder = request.query_params.get('reminder') == 'true'
    is_confirmation = request.query_params.get('confirmation') == 'true'
    original_text = request.query_params.get('original_text', '')
    
    # URL decode original_text pokud je potřeba
    if original_text:
        from urllib.parse import unquote_plus
        original_text = unquote_plus(original_text)
    
    logger.info(f"📝 Rozpoznaná řeč: '{speech_result}' (confidence: {confidence})")
    logger.info(f"🔗 attempt_id: {attempt_id}, reminder: {is_reminder}, confirmation: {is_confirmation}")
    
    response = VoiceResponse()
    
    # Zpracování confirmation workflow
    if is_confirmation and original_text:
        logger.info(f"🔄 === CONFIRMATION WORKFLOW ===")
        logger.info(f"📋 Původní text: '{original_text}'")
        logger.info(f"🎤 Nová odpověď: '{speech_result}'")
        
        # Zkontroluj jestli uživatel potvrdil ("ano", "yes", "správně", atd.)
        confirmation_words = ['ano', 'yes', 'správně', 'jo', 'jasně', 'přesně', 'souhlasím']
        speech_lower = speech_result.lower()
        
        found_confirmation = [word for word in confirmation_words if word in speech_lower]
        
        if found_confirmation:
            # Potvrzeno - použij původní text
            speech_result = original_text
            logger.info(f"✅ POTVRZENO ('{found_confirmation[0]}') → používám původní: '{speech_result}'")
        else:
            # Nepotvrzeno - použij nový text
            logger.info(f"❌ NEPOTVRZENO → používám nový text: '{speech_result}'")
        
        logger.info(f"🎯 Finální text pro zpracování: '{speech_result}'")
        
        # Pokračuj normálním flow (bez dalších confidence kontrol)
        confidence_float = 1.0  # Nastavíme vysokou confidence aby se přeskočily další kontroly
    else:
        # Kontrola confidence threshold pro ASR
        confidence_float = float(confidence) if confidence else 0.0

    LOW_CONFIDENCE_THRESHOLD = 0.5  # Zvýšený práh pro lepší kontrolu

    # Pokud máme speech_result ale confidence je 0, pravděpodobně je to false positive
    # Twilio někdy neposkytne confidence i když rozpoznání bylo úspěšné
    if speech_result and confidence_float == 0.0:
        logger.info(f"🔍 Speech result existuje ale confidence je 0 - pravděpodobně OK rozpoznání")
        confidence_float = 0.5  # Nastavíme střední confidence pro pokračování

    # Zpracování připomenutí když uživatel neodpověděl
    if is_reminder:
        response.say(
            "Připomínám - pokud mi nerozumíte nebo potřebujete čas na zamyšlení, řekněte to prosím nahlas.",
            language="cs-CZ",
            rate="0.9",
            voice="Google.cs-CZ-Standard-A"
        )
        # Pokračuj do normálního flow
    
    # Použij chytřejší logiku rozpoznávání
    elif speech_result:
        # Kontrola, zda uživatel signalizuje dokončení odpovědi
        if is_completion_signal(speech_result):
            logger.info(f"✅ Uživatel signalizoval dokončení: '{speech_result}' - pokračuji s vyhodnocením")
            # Pokračuj s normálním flow jako by měl vysokou confidence
            confidence_float = 1.0
        
        recognition_decision = should_ask_for_confirmation(speech_result, confidence_float)
        logger.info(f"🧠 Rozpoznání: {recognition_decision['reason']} → {recognition_decision['action']}")
        
        if recognition_decision['action'] in ['ask_confirm', 'ask_repeat', 'ask_complete']:
            # Vytvoř přirozenější odpověď s pauzami
            message_with_pauses = create_natural_speech_response(recognition_decision['message'])
            
            response.say(
                message_with_pauses,
                language="cs-CZ",
                rate="0.8",  # Trochu pomalejší pro jasnost
                voice="Google.cs-CZ-Standard-A"
            )
            
            if recognition_decision['action'] == 'ask_confirm':
                # URL encode pro bezpečné předání parametrů
                from urllib.parse import quote_plus
                encoded_text = quote_plus(speech_result)
                
                gather = response.gather(
                    input='speech',
                    timeout=12,  # Více času na rozmyšlení
                    speech_timeout=4,
                    action=f'/voice/process?confirmation=true&original_text={encoded_text}',
                    method='POST',
                    language='cs-CZ',
                    speech_model='phone_call',
                    enhanced='true'
                )
                
                gather.say(
                    "Řekněte 'ano' pokud je to správně, nebo zopakujte vaši odpověď.",
                    language="cs-CZ",
                    rate="0.8",
                    voice="Google.cs-CZ-Standard-A"
                )
            
            elif recognition_decision['action'] == 'ask_complete':
                # Nabídka doplnění odpovědi
                gather = response.gather(
                    input='speech',
                    timeout=15,  # Více času na rozmyšlení delší odpovědi
                    speech_timeout=5,
                    action='/voice/process',
                    method='POST',
                    language='cs-CZ',
                    speech_model='phone_call',
                    enhanced='true'
                )
                
                gather.say(
                    "Pokud chcete něco doplnit, pokračujte. Nebo řekněte 'hotovo' pokud je odpověď kompletní.",
                    language="cs-CZ",
                    rate="0.8",
                    voice="Google.cs-CZ-Standard-A"
                )
            
            else:  # ask_repeat
                gather = response.gather(
                    input='speech',
                    timeout=12,
                    speech_timeout=4,
                    action='/voice/process',
                    method='POST',
                    language='cs-CZ',
                    speech_model='phone_call',
                    enhanced='true'
                )
            
            response.say(
                "Nerozuměl jsem vám. Zkuste to prosím znovu pomaleji.",
                language="cs-CZ",
                rate="0.8",
                voice="Google.cs-CZ-Standard-A"
            )
            response.redirect('/voice/process?reminder=true')
            
            return Response(content=str(response), media_type="text/xml")
    
    # Pokud je odpověď prázdná a není to reminder
    if not speech_result and not is_reminder:
        response.say(
            "Nerozuměl jsem vám nebo jste neodpověděl. Zkuste mluvit jasně a zřetelně.",
            language="cs-CZ",
            rate="0.9",
            voice="Google.cs-CZ-Standard-A"
        )
        
        # Vylepšený gather s lepšími parametry
        gather = response.gather(
            input='speech',
            timeout=10,
            speech_timeout=4,  # Delší speech_timeout pro lepší detekci konce
            action='/voice/process',
            method='POST',
            language='cs-CZ',
            speech_model='phone_call',
            enhanced='true'
        )
        
        gather.say(
            "Zkuste to prosím znovu. Naslouchám...",
            language="cs-CZ",
            rate="0.9",
            voice="Google.cs-CZ-Standard-A"
        )
        
        response.say(
            "Pokud máte potíže s připojením, zkuste zavolat znovu.",
            language="cs-CZ",
            rate="0.9",
            voice="Google.cs-CZ-Standard-A"
        )
        response.hangup()
        
        return Response(content=str(response), media_type="text/xml")
    
    # Hlavní zpracování s OpenAI
    try:
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            response.say("AI služba není dostupná.", language="cs-CZ")
            response.hangup()
            return Response(content=str(response), media_type="text/xml")
        
        import openai
        client = openai.OpenAI(api_key=openai_api_key)
        
        session = SessionLocal()
        current_user = None
        user_level = 0
        should_continue = False
        
        try:
            # Načtení uživatele
            if attempt_id:
                try:
                    attempt = session.query(Attempt).get(int(attempt_id))
                    if attempt:
                        current_user = attempt.user
                except:
                    pass
            
            if not current_user:
                current_user = session.query(User).order_by(User.id.desc()).first()
            
            if not current_user:
                response.say("Technická chyba - uživatel nenalezen.", language="cs-CZ")
                response.hangup()
                return Response(content=str(response), media_type="text/xml")
            
            user_level = getattr(current_user, 'current_lesson_level', 0)
            logger.info(f"👤 Uživatel: {current_user.name}, Úroveň: {user_level}")
            
            if user_level == 0:
                # === VSTUPNÍ TEST (LEKCE 0) ===
                should_continue = await handle_entry_test(session, current_user, speech_result, response, client, attempt_id, confidence_float)
            else:
                # === BĚŽNÉ LEKCE (1+) ===
                should_continue = await handle_regular_lesson(session, current_user, user_level, speech_result, response, client)
                
        except Exception as db_error:
            logger.error(f"❌ DB chyba: {db_error}")
            response.say("Došlo k technické chybě. Zkuste to prosím později.", language="cs-CZ")
            response.hangup()
            return Response(content=str(response), media_type="text/xml")
        finally:
            session.close()
    
    except Exception as e:
        logger.error(f"❌ Celková chyba: {e}")
        response.say("Došlo k neočekávané chybě.", language="cs-CZ")
        response.hangup()
        return Response(content=str(response), media_type="text/xml")
    
    # === POKRAČOVÁNÍ KONVERZACE ===
    if should_continue:
        gather = response.gather(
            input='speech',
            timeout=15,  # Delší timeout pro úvahu
            speech_timeout=4,  # Lepší detekce konce odpovědi
            action='/voice/process',
            method='POST',
            language='cs-CZ',
            speech_model='phone_call',
            enhanced='true'
        )
        
        if user_level == 0:
            gather.say(
                "Píp.",
                language="cs-CZ",
                rate="0.8",
                voice="Google.cs-CZ-Standard-A"
            )
        else:
            question_prompt = "Máte další otázku?"
            question_prompt_with_pauses = create_natural_speech_response(question_prompt)
            gather.say(
                question_prompt_with_pauses,
                language="cs-CZ",
                rate="0.8",
                voice="Google.cs-CZ-Standard-A"
            )
        
        # Vylepšený fallback
        response.say(
            "Nerozuměl jsem vaší odpovědi. Zkuste mluvit jasně nebo řekněte 'konec' pro ukončení.",
            language="cs-CZ",
            rate="0.8",
            voice="Google.cs-CZ-Standard-A"
        )
        response.redirect('/voice/process?reminder=true')
    else:
        response.say(
            "Děkuji za rozhovor. Na shledanou!",
            language="cs-CZ",
            rate="0.9",
            voice="Google.cs-CZ-Standard-A"
        )
        response.hangup()
    
    return Response(content=str(response), media_type="text/xml")


async def handle_entry_test(session, current_user, speech_result, response, client, attempt_id, confidence_float):
    """Zpracování vstupního testu (Lekce 0)"""
    logger.info("🎯 Zpracovávám vstupní test...")
    
    # Najdi Lekci 0
    target_lesson = session.query(Lesson).filter(
        Lesson.lesson_number == 0
    ).first()
    
    if not target_lesson:
        target_lesson = session.query(Lesson).filter(
            Lesson.title.contains("Lekce 0")
        ).first()
    
    if not target_lesson:
        response.say("Vstupní test nebyl nalezen. Kontaktujte administrátora.", language="cs-CZ")
        return False
    
    # Zkontroluj, jestli už existuje aktivní session PŘED jejím získáním
    session_db = SessionLocal()
    existing_active_session = session_db.query(TestSession).filter(
        TestSession.user_id == current_user.id,
        TestSession.lesson_id == target_lesson.id,
        TestSession.is_completed == False
    ).first()
    session_db.close()
    
    # Získej nebo vytvoř test session
    test_session = get_or_create_test_session(
        user_id=current_user.id,
        lesson_id=target_lesson.id,
        attempt_id=int(attempt_id) if attempt_id else None
    )
    
    # Rozlišení: NOVÁ session (první otázka) vs EXISTUJÍCÍ session (odpověď)
    if not existing_active_session:
        # NOVÁ SESSION - první otázka už byla řečena v voice_handler
        logger.info(f"🎯 Nová session vytvořena, první otázka už byla řečena")
        return True
    else:
        # EXISTUJÍCÍ SESSION - vyhodnotit odpověď
        logger.info(f"💬 Vyhodnocuji odpověď: '{speech_result}'")
        
        current_question = get_current_question(test_session)
        if not current_question or not speech_result:
            response.say("Nerozuměl jsem vaší odpovědi. Zkuste to prosím znovu.", language="cs-CZ")
            return True
        
        # AI vyhodnocení podle nových instrukcí s vylepšeným matching algoritmem
        keywords = current_question.get('keywords', [])
        system_prompt = f"""ÚKOL:
Vyhodnoť studentskou odpověď na zadanou otázku a porovnej ji s ideální správnou odpovědí.

OTÁZKA: {current_question.get('question', '')}
SPRÁVNÁ ODPOVĚĎ: {current_question.get('correct_answer', '')}
STUDENTSKÁ ODPOVĚĎ: "{speech_result}"

DŮLEŽITÉ PRAVIDLA PRO VYHODNOCENÍ:
1. POROVNÁVÁNÍ SE SPRÁVNOU ODPOVĚDÍ: Hlavní kritérium je podobnost s ideální správnou odpovědí, ne klíčová slova.

2. ROZPOZNÁVÁNÍ CHYB ASR: Ber v úvahu možné chyby rozpoznávání řeči:
   - 'operátorem' = 'separátorem' (ČASTÁ CHYBA ASR!)
   - 'reparátor' = 'separátor' (ČASTÁ CHYBA ASR!)
   - 'chlazení' = 'hlazení'
   - 'mazání' = 'mazaní'
   - 'odvod' = 'odvod'

3. SYNONYMA A VARIANTY: Uznávej tyto varianty:
   - 'refraktometr' = 'refraktometrický', 'refraktometrické'
   - 'koncentrace' = 'koncentrovaný', 'koncentrovaná'
   - 'bakterie' = 'bakteriální', 'bakterií', 'bakteriálního'
   - 'pH' = 'ph', 'PH', 'ph hodnota'
   - 'emulze' = 'emulzní', 'emulzní kapalina'
   - 'chlazení' = 'chlazen', 'ochlazován', 'chlazená'
   - 'separátor' = 'separátor oleje', 'separátorem', 'separátoru', 'operátorem', 'operátor', 'reparátor', 'reparátorem'
   - 'odstranění' = 'odstranit', 'odstraňuje', 'odstraněno', 'odstraňování'
   - 'skimmer' = 'skimmerem', 'skimmeru', 'skimmer'

4. KRITICKÉ PRAVIDLO: 
   - Pokud student řekne 'operátorem' nebo 'operátor', považuj to za 'separátorem'!
   - Pokud student řekne 'separátor', považuj to za 'separátorem' (stejný význam)!
   - Různé tvary slov mají stejný význam: 'separátor' = 'separátorem' = 'separátoru'

5. PRAVIDLO PRO ČÁSTEČNÉ SHODY:
   - Pokud student zmíní hlavní koncept (např. 'separátor'), ale chybí upřesnění (např. 'oleje'), stále to považuj za správné, pokud je kontext jasný.
   - Příklad: Na otázku "Jak se odstraňuje tramp oil?" je odpověď "separátorem" správná, i když ideální je "separátorem oleje".

6. ROZPOZNÁVÁNÍ KOŘENŮ SLOV:
   - Pokud kořen slova je správný, považuj to za správné
   - Příklad: 'chlazení' = 'chlazen', 'chlazená', 'chlazený', 'ochlazování'
   - Příklad: 'mazání' = 'mazan', 'mazaný', 'mazán', 'mazání'
   - Příklad: 'odstranění' = 'odstranit', 'odstraňuje', 'odstraněno', 'odstraňování'
   - Příklad: 'separátor' = 'separátorem', 'separátoru', 'separátorový'
   - Příklad: 'skimmer' = 'skimmerem', 'skimmeru', 'skimmerový'
   - Příklad: 'refraktometr' = 'refraktometrický', 'refraktometrické', 'refraktometrů'
   - Příklad: 'koncentrace' = 'koncentrovaný', 'koncentrovaná', 'koncentrovat'
   - Příklad: 'bakterie' = 'bakteriální', 'bakterií', 'bakteriálního'

7. VYPOČET SKÓRE: 
   - 100%: Odpověď obsahuje všechny klíčové koncepty ze správné odpovědi
   - 80-99%: Odpověď obsahuje většinu klíčových konceptů
   - 60-79%: Odpověď obsahuje některé klíčové koncepty
   - 40-59%: Odpověď obsahuje málo klíčových konceptů
   - 0-39%: Odpověď neobsahuje klíčové koncepty

VÝSTUP:
1. Procentuální skóre: Vypočítej podle pravidel výše
2. Ultra krátká zpětná vazba (max. 1–2 věty):  
   - Pokud chybí klíčové koncepty, vyjmenuj je stručně: „Chybí: …"  
   - Pokud odpověď obsahuje všechny klíčové koncepty: „Výborně, úplná odpověď!"

Formát odpovědi: [FEEDBACK] [SKÓRE: XX%]"""
        
        try:
            gpt_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_prompt}],
                max_tokens=150,
                temperature=0.3
            )
            
            ai_answer = gpt_response.choices[0].message.content
            
            # Extrakce skóre - robustní regex pro různé formáty
            import re
            score_match = re.search(r'\[SKÓRE:\s*(\d+)%?\]', ai_answer, re.IGNORECASE)
            current_score = int(score_match.group(1)) if score_match else 0
            
            # Vyčistění feedback od skóre tagu
            clean_feedback = re.sub(r'\[SKÓRE:\s*\d+%?\]', '', ai_answer, flags=re.IGNORECASE).strip()
            
            # Log pro debug AI odpovědi
            logger.info(f"🤖 AI raw odpověď: '{ai_answer}'")
            logger.info(f"🎯 Extrahované skóre: {current_score}%")
            logger.info(f"💬 Čistý feedback: '{clean_feedback}'")
            
            # Vylepšené logování před uložením odpovědi
            log_answer_analysis(
                user_id=current_user.id,
                question=current_question,
                user_answer=speech_result,
                ai_score=current_score,
                ai_feedback=clean_feedback,
                confidence=confidence_float
            )
            
            # Uložení odpovědi a posun
            updated_session = save_answer_and_advance(
                test_session.id, 
                speech_result, 
                float(current_score), 
                clean_feedback,
                test_session.current_question_index  # Přidán chybějící parametr
            )
            
            if updated_session and updated_session.get('is_completed'):
                # Test dokončen
                final_score = updated_session.get('current_score', 0)
                total_questions = len(updated_session.get('answers', []))
                
                if final_score >= 90:
                    current_user.current_lesson_level = 1
                    session.commit()
                    final_message = f"{clean_feedback} Test dokončen! Skóre: {final_score:.1f}% z {total_questions} otázek. Gratulujeme, postoupili jste do Lekce 1!"
                else:
                    final_message = f"{clean_feedback} Test dokončen. Skóre: {final_score:.1f}% z {total_questions} otázek. Pro postup potřebujete 90%. Můžete zkusit znovu!"
                
                # Použij přirozenější pauzy pro finální zprávu
                final_message_with_pauses = create_natural_speech_response(final_message)
                response.say(final_message_with_pauses, language="cs-CZ", rate="0.8")
                return False  # Ukončit konverzaci
            else:
                # Další otázka - použij adaptivní výběr
                next_question = get_next_adaptive_question(updated_session)
                if next_question:
                    # Aktualizace indexu v databázi
                    test_session = session.query(TestSession).get(updated_session['id'])
                    test_session.current_question_index = next_question['original_index']
                    session.commit()
                    
                    difficulty_indicator = {"easy": "⭐", "medium": "⭐⭐", "hard": "⭐⭐⭐"}.get(
                        next_question.get('difficulty', 'medium'), "⭐⭐"
                    )
                    
                    next_text = f"{clean_feedback} Další otázka {difficulty_indicator}: {next_question.get('question', '')}"
                    # Použij přirozenější pauzy
                    next_text_with_pauses = create_natural_speech_response(next_text)
                    response.say(next_text_with_pauses, language="cs-CZ", rate="0.8")
                    return True  # Pokračovat
                else:
                    response.say("Všechny otázky zodpovězeny. Test končí.", language="cs-CZ", rate="0.8")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ AI chyba: {e}")
            response.say("Chyba při vyhodnocování odpovědi.", language="cs-CZ")
            return False


def log_answer_analysis(user_id: int, question: dict, user_answer: str, ai_score: int, ai_feedback: str, confidence: float):
    """Detailní logování odpovědi pro analýzu typických chyb"""
    try:
        question_text = question.get('question', 'N/A')
        correct_answer = question.get('correct_answer', 'N/A')
        keywords = question.get('keywords', [])
        
        logger.info(f"""
📊 === ANALÝZA ODPOVĚDI ===
👤 User ID: {user_id}
❓ Otázka: {question_text}
✅ Správná odpověď: {correct_answer}
🔑 Klíčová slova: {', '.join(keywords) if keywords else 'žádná'}
💬 Odpověď uživatele: '{user_answer}'
🎯 AI skóre: {ai_score}%
📝 AI feedback: {ai_feedback}
🎤 Speech confidence: {confidence:.2f}
📏 Délka odpovědi: {len(user_answer)} znaků, {len(user_answer.split())} slov
===========================""")
        
        # Analýza typických problémů
        issues = []
        
        # Příliš krátká odpověď
        if len(user_answer.split()) < 2:
            issues.append("KRÁTKÁ_ODPOVĚĎ")
        
        # Nízká confidence
        if confidence < 0.3:
            issues.append("NÍZKÁ_CONFIDENCE")
        elif confidence < 0.5:
            issues.append("STŘEDNÍ_CONFIDENCE")
        
        # Nízké skóre
        if ai_score < 30:
            issues.append("VELMI_NÍZKÉ_SKÓRE")
        elif ai_score < 60:
            issues.append("NÍZKÉ_SKÓRE")
        
        # Detailní analýza klíčových slov
        if keywords:
            found_keywords = []
            missing_keywords = []
            
            for kw in keywords:
                kw_lower = kw.lower()
                answer_lower = user_answer.lower()
                found_match = False
                match_type = ""
                
                # 1. PŘESNÁ SHODA
                if kw_lower in answer_lower:
                    found_keywords.append(kw)
                    found_match = True
                    match_type = "přesná"
                
                # 2. SUBSTRING MATCHING (hotfix) - klíčové slovo jako součást delšího slova
                elif not found_match:
                    # Hledej klíčové slovo jako substring v libovolném slově odpovědi
                    words_in_answer = answer_lower.split()
                    for word in words_in_answer:
                        if kw_lower in word or word in kw_lower:
                            found_keywords.append(f"{kw}({word})")
                            found_match = True
                            match_type = "substring"
                            break
                
                # 3. SYNONYMA A VARIANTY (rozšířený seznam)
                if not found_match:
                    synonyms = {
                        'chlazení': ['hlazení', 'chladění', 'ochlazování', 'chlazen', 'ochlazován'],
                        'mazání': ['mazaní', 'lubrication', 'lubrikace', 'mazan', 'mazán'],
                        'odvod': ['odvedení', 'odvádění', 'odváděn', 'odváděný'],
                        'refraktometr': ['refraktometric', 'refraktometrický', 'refraktometrů'],
                        'koncentrace': ['koncentrac', 'koncentraci', 'koncentrovat'],
                        'bakterie': ['bakterií', 'bakteriálního', 'mikroorganismy'],
                        'pH': ['ph', 'kyselost', 'kyselá', 'zásaditá'],
                        'emulze': ['emulzní', 'emulgovat', 'emulgovaný'],
                        'separátor': ['separátor oleje', 'separátorem', 'operátorem', 'operátor', 'reparátor', 'reparátorem'],
                        'odstranění': ['odstranit', 'odstraňuje', 'odstraněno', 'odstraňování'],
                        'skimmer': ['skimmerem', 'skimmeru', 'skimmer']
                    }
                    
                    if kw_lower in synonyms:
                        for syn in synonyms[kw_lower]:
                            if syn in answer_lower:
                                found_keywords.append(f"{kw}({syn})")
                                found_match = True
                                match_type = "synonymum"
                                break
                
                # 4. POKUD NEBYLO NALEZENO
                if not found_match:
                    missing_keywords.append(kw)
                    
                # Log pro debug
                if found_match:
                    logger.debug(f"✓ '{kw}' nalezeno jako {match_type}: {found_keywords[-1]}")
            
            # Výpočet pokrytí klíčových slov
            keyword_coverage = len(found_keywords) / len(keywords) * 100 if keywords else 0
            
            if not found_keywords:
                issues.append("ŽÁDNÁ_KLÍČOVÁ_SLOVA")
            elif keyword_coverage < 50:
                issues.append("MÁLO_KLÍČOVÝCH_SLOV")
                
            # Detailní breakdown matchingu
            exact_matches = [kw for kw in found_keywords if '(' not in str(kw)]
            fuzzy_matches = [kw for kw in found_keywords if '(' in str(kw)]
            
            logger.info(f"🔍 ANALÝZA KLÍČOVÝCH SLOV ({len(found_keywords)}/{len(keywords)}):")
            logger.info(f"  ✅ Přesné shody: {exact_matches}")
            logger.info(f"  🔄 Fuzzy/substring shody: {fuzzy_matches}")
            logger.info(f"  ❌ Chybějící: {missing_keywords}")
            logger.info(f"📊 Celkové pokrytí: {keyword_coverage:.1f}%")
        
        if issues:
            logger.warning(f"⚠️ Identifikované problémy: {', '.join(issues)}")
        else:
            logger.info(f"✅ Odpověď bez evidentních problémů")
            
    except Exception as e:
        logger.error(f"❌ Chyba při logování analýzy: {e}")


async def handle_regular_lesson(session, current_user, user_level, speech_result, response, client):
    """Zpracování běžných lekcí (1+)"""
    logger.info(f"📚 Zpracovávám lekci úrovně {user_level}")
    
    # Najdi lekci podle čísla
    target_lesson = session.query(Lesson).filter(
        Lesson.lesson_number == user_level
    ).first()
    
    if not target_lesson:
        # Fallback - najdi podle úrovně
        target_lesson = session.query(Lesson).filter(
            Lesson.level == "beginner"
        ).first()
    
    if not target_lesson:
        response.say(f"Lekce {user_level} nebyla nalezena. Kontaktujte administrátora.", language="cs-CZ")
        return False
    
    logger.info(f"✅ Nalezena lekce: {target_lesson.title}")
    
    # Obecná konverzace nebo testování
    lesson_content = target_lesson.script or target_lesson.description or ""
    
    # Jednoduchý AI chat o lekci
    system_prompt = f"""Jsi AI lektor pro lekci: {target_lesson.title}

OBSAH LEKCE:
{lesson_content[:800]}

INSTRUKCE:
1. Odpovídej na otázky studenta o lekci
2. Buď věcný a srozumitelný
3. Pokud student chce test, připrav otázku
4. Udržuj rozhovor aktivní

Student řekl: "{speech_result}"
Odpověz mu v češtině (max 2 věty)."""
    
    try:
        gpt_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}],
            max_tokens=200,
            temperature=0.6
        )
        
        ai_answer = gpt_response.choices[0].message.content
        response.say(ai_answer, language="cs-CZ", rate="0.9")
        return True  # Pokračovat v konverzaci
        
    except Exception as e:
        logger.error(f"❌ AI chyba: {e}")
        response.say("Chyba při zpracování dotazu.", language="cs-CZ")
        return False

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
        logger.info(f"🎧 === PROCESS_AUDIO_CHUNK SPUŠTĚN === ({len(audio_data)} bajtů)")
        
        if len(audio_data) < 1000:  # Příliš malý chunk, ignorujeme
            logger.info(f"⚠️ Příliš malý chunk ({len(audio_data)} bajtů), ignoruji")
            return
            
        logger.info(f"🎧 Zpracovávám audio chunk ({len(audio_data)} bajtů)")
        
        # Uložíme audio do dočasného souboru
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            logger.info("📁 Vytvářím dočasný WAV soubor")
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
            logger.info(f"📁 WAV soubor vytvořen: {tmp_file_path}")
        
        try:
            logger.info("🎤 Spouštím Whisper STT...")
            # OpenAI Whisper pro STT
            with open(tmp_file_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="cs"
                )
            
            user_text = transcript.text.strip()
            logger.info(f"📝 Transkripce DOKONČENA: '{user_text}'")
            
            if not user_text or len(user_text) < 3:
                logger.info("⚠️ Příliš krátká transkripce, ignoruji")
                return
            
            logger.info("🤖 Přidávám zprávu do Assistant threadu...")
            # Přidáme zprávu do threadu
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_text
            )
            
            logger.info("🚀 Spouštím Assistant run...")
            # Spustíme asistenta
            run = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )
            
            logger.info(f"⏳ Čekám na dokončení Assistant run (ID: {run.id})...")
            # Čekáme na dokončení (s timeout)
            import time
            max_wait = 15  # 15 sekund timeout pro rychlejší odpověď
            start_time = time.time()
            
            while run.status in ["queued", "in_progress"] and (time.time() - start_time) < max_wait:
                await asyncio.sleep(0.5)  # Kratší interval pro rychlejší odpověď
                run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                logger.info(f"⏳ Run status: {run.status}")
            
            if run.status == "completed":
                logger.info("✅ Assistant run DOKONČEN! Získávám odpověď...")
                # Získáme nejnovější odpověď
                messages = client.beta.threads.messages.list(thread_id=thread_id, limit=1)
                
                for message in messages.data:
                    if message.role == "assistant":
                        for content in message.content:
                            if content.type == "text":
                                assistant_response = content.text.value
                                logger.info(f"🤖 Assistant odpověď ZÍSKÁNA: '{assistant_response}'")
                                
                                # Pošleme jako TTS
                                logger.info("🔊 Odesílám TTS odpověď...")
                                await send_tts_to_twilio(websocket, assistant_response, stream_sid, client)
                                logger.info("✅ TTS odpověď ODESLÁNA!")
                                return
                
                logger.warning("⚠️ Žádná assistant odpověď nenalezena")
            else:
                logger.warning(f"⚠️ Assistant run neúspěšný: {run.status}")
                
        finally:
            # Vyčistíme dočasný soubor
            import os
            try:
                os.unlink(tmp_file_path)
                logger.info("🗑️ Dočasný soubor vymazán")
            except:
                pass
                
    except Exception as e:
        logger.error(f"❌ CHYBA při zpracování audio: {e}")
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
    
    # PRINT pro Railway stdout
    print("🚀 === AUDIO_STREAM FUNKCE SPUŠTĚNA! ===")
    print(f"🔗 WebSocket client: {websocket.client}")
    print(f"📋 WebSocket headers: {dict(websocket.headers)}")
    
    logger.info("🚀 === AUDIO_STREAM FUNKCE SPUŠTĚNA! ===")
    logger.info(f"🔗 WebSocket client: {websocket.client}")
    logger.info(f"📋 WebSocket headers: {dict(websocket.headers)}")
    
    # KRITICKÉ: Musíme nejprve přijmout WebSocket připojení
    try:
        await websocket.accept()
        print("✅ DEBUG: WebSocket connection accepted.")
        logger.info("✅ DEBUG: WebSocket connection accepted.")
    except Exception as accept_error:
        print(f"❌ CHYBA při websocket.accept(): {accept_error}")
        logger.error(f"❌ CHYBA při websocket.accept(): {accept_error}")
        return
        
    # Inicializace OpenAI klienta
    openai_api_key = os.getenv('OPENAI_API_KEY')
    if not openai_api_key:
        logger.error("❌ OPENAI_API_KEY není nastaven")
        await websocket.close()
        return
        
    logger.info("🤖 Inicializuji OpenAI klienta...")
    import openai
    client = openai.OpenAI(api_key=openai_api_key)
    logger.info("✅ OpenAI klient inicializován")
    
    # Vytvoříme nového assistanta s českými instrukcemi pro výuku jazyků
    logger.info("🎯 Vytvářím nového Assistant...")
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

Vždy zůstávaj v roli učitele jazyků a komunikuj pouze v češtině.""",
            model="gpt-4-1106-preview",
            tools=[]
        )
        assistant_id = assistant.id
        logger.info(f"✅ Vytvořen nový Assistant: {assistant_id}")
    except Exception as e:
        logger.error(f"❌ Chyba při vytváření Assistanta: {e}")
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
        
        # Okamžitá úvodní zpráva (bez čekání na stream_sid)
        welcome_message = "Připojuji se k AI asistentovi. Moment prosím."
        welcome_sent = False
        
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
                logger.info("🔄 DEBUG: Čekám na WebSocket data...")
                
                # Kontrola stavu WebSocket před čtením
                try:
                    # Pokusíme se o rychlý ping test
                    await websocket.ping()
                    logger.info("✅ DEBUG: WebSocket ping OK")
                except Exception as ping_error:
                    logger.info(f"❌ DEBUG: WebSocket ping failed: {ping_error}")
                    logger.info("DEBUG: WebSocket je pravděpodobně zavřen, ukončujem smyčku")
                    websocket_active = False
                    break
                
                logger.info("📥 DEBUG: Volám websocket.receive_text()...")
                data = await websocket.receive_text()
                logger.info(f"📨 DEBUG: Přijata data ({len(data)} znaků): {data[:200]}...")
                
                try:
                    msg = json.loads(data)
                    logger.info(f"✅ DEBUG: JSON parsování OK")
                    event = msg.get("event", "unknown")
                    logger.info(f"🎯 DEBUG: Event typ: '{event}'")
                except json.JSONDecodeError as json_error:
                    logger.error(f"❌ DEBUG: JSON parsing CHYBA: {json_error}")
                    logger.error(f"❌ DEBUG: Problematická data: {data}")
                    continue
                
                if event == "start":
                    logger.info("=== MEDIA STREAM START EVENT PŘIJAT! ===")
                    stream_sid = msg.get("streamSid")
                    logger.info(f"Stream SID: {stream_sid}")
                    
                    # Spustíme keepalive task
                    if not keepalive_task:
                        keepalive_task = asyncio.create_task(keepalive_sender())
                        logger.info("💓 Keepalive task spuštěn")
                    
                    # Pošleme okamžitou welcome zprávu
                    if not welcome_sent:
                        logger.info("🔊 Odesílám welcome zprávu")
                        await send_tts_to_twilio(websocket, welcome_message, stream_sid, client)
                        welcome_sent = True
                    
                    # Pošleme úvodní zprávu po krátké pauze
                    if not initial_message_sent:
                        await asyncio.sleep(3)  # Krátká pauza po welcome zprávě
                        logger.info("🔊 Odesílám úvodní zprávu")
                        await send_tts_to_twilio(websocket, initial_message, stream_sid, client)
                        initial_message_sent = True
                    
                elif event == "media":
                    logger.info(f"🎵 MEDIA EVENT PŘIJAT! Track: {msg['media'].get('track', 'unknown')}")
                    payload = msg["media"]["payload"]
                    track = msg["media"]["track"]
                    
                    if track == "inbound":
                        logger.info("📥 INBOUND TRACK - zpracovávám audio data")
                        # Real-time zpracování - zpracujeme audio ihned
                        audio_data = base64.b64decode(payload)
                        audio_buffer.extend(audio_data)
                        
                        logger.info(f"📊 Audio buffer: {len(audio_buffer)} bajtů")
                        
                        # Zpracujeme audio každých 800 bajtů (~1 sekunda audio při 8kHz)
                        if len(audio_buffer) >= 800:  # ~1 sekunda audio při 8kHz
                            logger.info(f"🎧 Zpracovávám audio chunk ({len(audio_buffer)} bajtů) - PRÁH DOSAŽEN!")
                            
                            # Zkopírujeme buffer před vymazáním
                            audio_to_process = bytes(audio_buffer)
                            audio_buffer.clear()
                            
                            # Zpracujeme audio v background tasku
                            asyncio.create_task(
                                process_audio_chunk(
                                    websocket, audio_to_process, stream_sid, 
                                    client, assistant_id, thread.id
                                )
                            )
                    else:
                        logger.info(f"📤 OUTBOUND TRACK - ignoruji (track: {track})")
                    
                elif event == "stop":
                    logger.info("Media Stream ukončen")
                    websocket_active = False
                    
                    # Zpracujeme zbývající audio i když je malé
                    if audio_buffer and len(audio_buffer) > 100:  # Alespoň 100 bajtů
                        logger.info(f"🎧 Zpracovávám zbývající audio ({len(audio_buffer)} bajtů)")
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

@app.get("/test-websocket")
async def test_websocket():
    """Test endpoint pro ověření WebSocket funkčnosti"""
    return {
        "message": "WebSocket test endpoint",
        "websocket_url": "wss://lecture-app-production.up.railway.app/audio",
        "test_url": "wss://lecture-app-production.up.railway.app/audio-test"
    } 

@app.websocket("/test")
async def websocket_test(websocket: WebSocket):
    """Velmi jednoduchý WebSocket test"""
    logger.info("🧪 === WEBSOCKET TEST ENDPOINT SPUŠTĚN ===")
    await websocket.accept()
    logger.info("🧪 WebSocket test připojení přijato")
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"🧪 Test přijal: {data}")
            await websocket.send_text(f"Echo: {data}")
    except Exception as e:
        logger.info(f"🧪 Test WebSocket ukončen: {e}")
    finally:
        logger.info("🧪 === WEBSOCKET TEST UKONČEN ===") 

@app.get("/websocket-status")
async def websocket_status():
    """Kontrola stavu WebSocket endpointů"""
    return {
        "message": "WebSocket status check",
        "endpoints": {
            "audio": "/audio",
            "test": "/test", 
            "audio-test": "/audio-test"
        },
        "railway_websocket_support": "Testing...",
        "timestamp": "2025-07-24T19:15:00Z"
    } 

@app.post("/tts")
async def generate_tts(request: Request):
    """HTTP endpoint pro generování TTS audio"""
    try:
        data = await request.json()
        text = data.get('text', '')
        
        if not text:
            return {"error": "Missing text parameter"}
        
        logger.info(f"🔊 Generuji TTS pro: {text[:50]}...")
        
        # OpenAI TTS
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            return {"error": "OpenAI API key not configured"}
        
        import openai
        client = openai.OpenAI(api_key=openai_api_key)
        
        response = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
            response_format="wav"
        )
        
        # Převod na base64 pro Twilio
        import base64
        audio_b64 = base64.b64encode(response.content).decode()
        
        logger.info("✅ TTS audio vygenerováno")
        
        return {
            "success": True,
            "audio": audio_b64,
            "format": "wav",
            "text": text[:100]
        }
        
    except Exception as e:
        logger.error(f"Chyba při TTS: {e}")
        return {"error": str(e)} 

@admin_router.get("/create-lesson-1", name="admin_create_lesson_1")
def admin_create_lesson_1(request: Request):
    """Endpoint pro vytvoření Lekce 1 - Základy obráběcích kapalin"""
    try:
        logger.info("🚀 Vytváření Lekce 1...")
        
        session = SessionLocal()
        
        # Zkontroluj, jestli už lekce 1 existuje
        existing_lesson = session.query(Lesson).filter(
            Lesson.title.contains("Lekce 1")
        ).first()
        
        if existing_lesson:
            session.close()
            return templates.TemplateResponse("message.html", {
                "request": request,
                "message": f"✅ Lekce 1 již existuje! (ID: {existing_lesson.id})",
                "back_url": "/admin/lessons",
                "back_text": "Zpět na lekce"
            })
        
        # Obsah lekce 1 - Základy obráběcích kapalin
        lesson_script = """
# Lekce 1: Základy obráběcích kapalin

## Úvod
Obráběcí kapaliny jsou nezbytnou součástí moderního obrábění kovů. Jejich správné použití a údržba výrazně ovlivňuje kvalitu výroby, životnost nástrojů a bezpečnost práce.

## Hlavní funkce obráběcích kapalin

### 1. Chlazení
- Odvod tepla vznikajícího při řezném procesu
- Zabránění přehřátí nástroje a obrobku
- Udržení stálé teploty řezné hrany

### 2. Mazání
- Snížení tření mezi nástrojem a obrobkem
- Zlepšení kvality povrchu
- Prodloužení životnosti nástroje

### 3. Odvod třísek
- Transport třísek pryč z místa řezu
- Zabránění zanášení nástroje
- Udržení čistoty řezné zóny

## Typy obráběcích kapalin

### Řezné oleje
- Vysoká mazací schopnost
- Použití při těžkém obrábění
- Nevhodné pro vysoké rychlosti

### Emulze (směsi oleje a vody)
- Kombinace mazání a chlazení
- Nejčastěji používané
- Koncentrace 3-8%

### Syntetické kapaliny
- Bez oleje, pouze chemické přísady
- Výborné chladicí vlastnosti
- Dlouhá životnost

## Kontrola a údržba

### Denní kontrola
- Měření koncentrace refraktometrem
- Kontrola pH hodnoty (8,5-9,5)
- Vizuální kontrola čistoty

### Týdenní údržba
- Doplnění kapaliny
- Odstranění nečistot
- Kontrola bakteriální kontaminace

### Měsíční servis
- Výměna filtrů
- Hloubková analýza
- Případná regenerace

## Bezpečnost
- Používání ochranných pomůcek
- Prevence kontaktu s kůží
- Správné skladování a likvidace

## Závěr
Správná práce s obráběcími kapalinami je základem efektivního obrábění. Pravidelná kontrola a údržba zajišťuje optimální výkon a bezpečnost provozu.
        """
        
        # Vytvoř lekci 1
        lesson = Lesson(
            title="Lekce 1: Základy obráběcích kapalin",
            description="Komplexní úvod do problematiky obráběcích kapalin - funkce, typy, kontrola a údržba.",
            language="cs",
            script=lesson_script,
            questions=[],  # Otázky se budou generovat dynamicky
            level="beginner"
        )
        
        session.add(lesson)
        session.commit()
        lesson_id = lesson.id
        session.close()
        
        logger.info(f"✅ Lekce 1 vytvořena s ID: {lesson_id}")
        
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"🎉 Lekce 1 úspěšně vytvořena!\n\n📝 ID: {lesson_id}\n📚 Obsah: Základy obráběcích kapalin\n🎯 Úroveň: Začátečník\n\n⚡ Otázky se generují automaticky při testování!",
            "back_url": "/admin/lessons",
            "back_text": "Zobrazit všechny lekce"
        })
        
    except Exception as e:
        logger.error(f"❌ Chyba při vytváření Lekce 1: {e}")
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"❌ Chyba při vytváření Lekce 1: {str(e)}",
            "back_url": "/admin/lessons",
            "back_text": "Zpět na lekce"
        })

@admin_router.get("/user-progress", response_class=HTMLResponse, name="admin_user_progress")
def admin_user_progress(request: Request):
    """Zobrazí pokrok všech uživatelů"""
    session = SessionLocal()
    try:
        users = session.query(User).all()
        
        # Připrav data o pokroku
        progress_data = []
        for user in users:
            user_level = getattr(user, 'current_lesson_level', 0)
            
            # Najdi název aktuální lekce
            current_lesson_name = "Vstupní test"
            if user_level == 1:
                current_lesson_name = "Lekce 1: Základy"
            elif user_level > 1:
                current_lesson_name = f"Lekce {user_level}"
            
            progress_data.append({
                'user': user,
                'level': user_level,
                'lesson_name': current_lesson_name,
                'attempts_count': len(user.attempts) if hasattr(user, 'attempts') else 0
            })
        
        session.close()
        return templates.TemplateResponse("admin/user_progress.html", {
            "request": request, 
            "progress_data": progress_data
        })
        
    except Exception as e:
        session.close()
        logger.error(f"❌ Chyba při načítání pokroku: {e}")
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"❌ Chyba při načítání pokroku uživatelů: {str(e)}",
            "back_url": "/admin/users",
            "back_text": "Zpět na uživatele"
        })


# Funkce pro správu test sessions
def get_or_create_test_session(user_id: int, lesson_id: int, attempt_id: int = None) -> TestSession:
    """Najde existující aktivní test session nebo vytvoří novou"""
    session = SessionLocal()
    try:
        # NEJDŘÍV zkus najít existující aktivní session
        existing_session = session.query(TestSession).filter(
            TestSession.user_id == user_id,
            TestSession.lesson_id == lesson_id,
            TestSession.is_completed == False
        ).first()
        
        # Pokud existuje aktivní session, vrať ji
        if existing_session:
            logger.info(f"📋 Pokračuji v existující test session {existing_session.id} (otázka {existing_session.current_question_index + 1}/{existing_session.total_questions})")
            session.close()
            return existing_session
        
        # Pokud neexistuje aktivní session, vytvoř novou
        logger.info(f"🆕 Vytvářím novou test session pro uživatele {user_id}")
        
        # Vytvoř novou session
        lesson = session.query(Lesson).get(lesson_id)
        if not lesson:
            raise ValueError(f"Lekce {lesson_id} neexistuje")
        
        # Získej aktivní otázky z lekce
        enabled_questions = []
        if isinstance(lesson.questions, list):
            enabled_questions = [
                q for q in lesson.questions 
                if isinstance(q, dict) and q.get('enabled', True)
            ]
        
        if not enabled_questions:
            raise ValueError("Žádné aktivní otázky v lekci")
        
        # Vytvoř novou test session
        test_session = TestSession(
            user_id=user_id,
            lesson_id=lesson_id,
            attempt_id=attempt_id,
            current_question_index=0,
            total_questions=len(enabled_questions),
            questions_data=enabled_questions,
            answers=[],
            scores=[]
        )
        
        session.add(test_session)
        session.commit()
        
        logger.info(f"🆕 Vytvořena nová test session: {test_session.id} s {len(enabled_questions)} otázkami")
        logger.info(f"🔍 První 3 otázky: {[q.get('question', 'N/A')[:50] for q in enabled_questions[:3]]}")
        return test_session
        
    finally:
        session.close()

def get_current_question(test_session) -> dict:
    """Získá aktuální otázku pro test session (přijímá TestSession objekt nebo dict)"""
    if isinstance(test_session, dict):
        current_index = test_session.get('current_question_index', 0)
        questions_data = test_session.get('questions_data', [])
    else:
        current_index = test_session.current_question_index
        questions_data = test_session.questions_data
    
    if current_index >= len(questions_data):
        return None
    
    return questions_data[current_index]

def get_next_adaptive_question(test_session) -> Optional[dict]:
    """
    Vybere další otázku na základě adaptivní obtížnosti.
    """
    if isinstance(test_session, dict):
        answered_indices = {a['question_index'] for a in test_session.get('answers', [])}
        all_questions = test_session.get('questions_data', [])
        difficulty_score = test_session.get('difficulty_score', 50.0)
    else: # Je to TestSession objekt
        # Bezpečnější přístup k potentially None 'answers'
        answered_indices = {a['question_index'] for a in (test_session.answers or [])}
        all_questions = test_session.questions_data
        difficulty_score = getattr(test_session, 'difficulty_score', 50.0) or 50.0

    unanswered_questions = [
        (idx, q) for idx, q in enumerate(all_questions) if idx not in answered_indices
    ]

    if not unanswered_questions:
        return None

    difficulty_map = {"easy": 25, "medium": 50, "hard": 75}
    
    best_question = None
    min_diff = float('inf')

    for idx, q_data in unanswered_questions:
        q_difficulty = difficulty_map.get(q_data.get("difficulty", "medium"), 50)
        diff = abs(q_difficulty - difficulty_score)
        
        if diff < min_diff:
            min_diff = diff
            best_question = q_data.copy() # Vytvoříme kopii
            best_question['original_index'] = idx 
            
    return best_question

def save_answer_and_advance(test_session_id: int, user_answer: str, score: float, feedback: str, question_index: int):
    """
    Uloží odpověď, aktualizuje skóre obtížnosti, sleduje chyby a posune na další otázku.
    """
    session = SessionLocal()
    try:
        test_session = session.query(TestSession).get(test_session_id)
        if not test_session:
            return None
        
        # Získání otázky podle předaného indexu
        current_question = test_session.questions_data[question_index]
        
        # Aktualizace skóre obtížnosti
        difficulty_map = {"easy": 25, "medium": 50, "hard": 75}
        q_difficulty_val = difficulty_map.get(current_question.get("difficulty", "medium"), 50)
        
        if score >= 80:
            adjustment = (100 - q_difficulty_val) / 10
            current_difficulty = getattr(test_session, 'difficulty_score', 50.0) or 50.0
            test_session.difficulty_score = current_difficulty + adjustment
        else:
            adjustment = q_difficulty_val / 10
            current_difficulty = getattr(test_session, 'difficulty_score', 50.0) or 50.0
            test_session.difficulty_score = current_difficulty - adjustment
            
            category = current_question.get("category", "Neznámá")
            if not test_session.failed_categories:
                test_session.failed_categories = []
            if category not in test_session.failed_categories:
                test_session.failed_categories.append(category)
                flag_modified(test_session, "failed_categories")

        current_difficulty = getattr(test_session, 'difficulty_score', 50.0) or 50.0
        test_session.difficulty_score = max(0, min(100, current_difficulty))
        final_difficulty = getattr(test_session, 'difficulty_score', 50.0) or 50.0
        logger.info(f"🧠 Nové skóre obtížnosti: {final_difficulty:.2f} (změna: {adjustment:.2f})")

        answer_data = {
            "question": current_question.get("question", ""),
            "correct_answer": current_question.get("correct_answer", ""),
            "user_answer": user_answer,
            "score": score,
            "feedback": feedback,
            "question_index": question_index
        }
        
        if not test_session.answers:
            test_session.answers = []
        if not test_session.scores:
            test_session.scores = []
            
        test_session.answers.append(answer_data)
        test_session.scores.append(score)
        
        test_session.current_score = sum(test_session.scores) / len(test_session.scores)
        
        question_num = len(test_session.answers)
        logger.info(f"""
💾 === ODPOVĚĎ ULOŽENA ===
🔢 Otázka: {question_num}/{test_session.total_questions}
📝 Uživatel: "{user_answer}"
🎯 Skóre: {score}%
💬 Feedback: "{feedback}"
📊 Průměr: {test_session.current_score:.1f}%
=========================""")
        
        if len(test_session.answers) >= test_session.total_questions:
            test_session.is_completed = True
            test_session.completed_at = datetime.utcnow()
        
        # KRITICKÉ: Oznámení SQLAlchemy o změnách JSON sloupců
        flag_modified(test_session, 'answers')
        flag_modified(test_session, 'scores')
        flag_modified(test_session, 'failed_categories')
        
        # KRITICKÉ: Commit změn do databáze
        session.commit()
        
        return {
            'id': test_session.id,
            'current_question_index': test_session.current_question_index,
            'total_questions': test_session.total_questions,
            'questions_data': test_session.questions_data,
            'answers': test_session.answers,
            'scores': test_session.scores,
            'current_score': test_session.current_score,
            'is_completed': test_session.is_completed,
            'completed_at': test_session.completed_at,
            'failed_categories': test_session.failed_categories,
            'difficulty_score': getattr(test_session, 'difficulty_score', 50.0)
        }
            
    finally:
        session.close()
    
    return None

# === NOVÁ FUNKCE: Inteligentní rozhodování o kvalitě rozpoznání ===
def should_ask_for_confirmation(speech_result: str, confidence_float: float, context: str = "") -> dict:
    """
    Chytrá logika pro rozhodování, zda se ptát na potvrzení odpovědi.
    Vrací slovník s doporučením a důvodem.
    """
    
    # Základní kontroly
    if not speech_result:
        return {"action": "ask_repeat", "reason": "empty_response", "message": "Nerozuměl jsem vám. Můžete zopakovat svou odpověď?"}
    
    speech_lower = speech_result.lower().strip()
    word_count = len(speech_result.split())
    
    # 1. VYSOKÁ KVALITA - pokračovat bez ptaní
    if confidence_float >= 0.8 and word_count >= 2:
        return {"action": "continue", "reason": "high_confidence", "message": ""}
    
    # 2. VELMI KRÁTKÉ ODPOVĚDI - možná neúplné
    if word_count == 1 and confidence_float < 0.7:
        return {
            "action": "ask_complete", 
            "reason": "too_short", 
            "message": f"Rozuměl jsem: '{speech_result}'. Chtěli byste svou odpověď rozšířit nebo je to vše?"
        }
    
    # 3. STŘEDNÍ KVALITA - rozhoduj podle obsahu
    if 0.4 <= confidence_float < 0.8:
        # Pokud obsahuje jasná slova, pravděpodobně je OK
        clear_indicators = ['ano', 'ne', 'nevím', 'není', 'je', 'má', 'nemá']
        has_clear_word = any(word in speech_lower for word in clear_indicators)
        
        if has_clear_word and word_count >= 2:
            return {"action": "continue", "reason": "clear_content", "message": ""}
        elif word_count >= 4:  # Delší odpověď, pravděpodobně OK
            return {"action": "continue", "reason": "sufficient_length", "message": ""}
        else:
            return {
                "action": "ask_confirm", 
                "reason": "medium_confidence", 
                "message": f"Rozuměl jsem: '{speech_result}'. Je to správně?"
            }
    
    # 4. NÍZKÁ KVALITA - požádat o zopakování
    if confidence_float < 0.4:
        return {
            "action": "ask_repeat", 
            "reason": "low_confidence", 
            "message": "Omlouvám se, nerozuměl jsem vám dobře. Můžete zopakovat svou odpověď pomaleji a jasněji?"
        }
    
    # 5. VÝCHOZÍ - pokračovat
    return {"action": "continue", "reason": "default", "message": ""}


def create_natural_speech_response(text: str, language: str = "cs-CZ", add_pauses: bool = True) -> str:
    """
    Vrací čistý text bez SSML tagů - TwiML je nepodporuje správně.
    Používáme pomalejší tempo řeči místo SSML pauz.
    """
    # Jednoduchý return bez jakýchkoliv SSML modifikací
    return text.strip()


def is_completion_signal(speech_text: str) -> bool:
    """
    Rozpozná, zda uživatel signalizuje dokončení odpovědi.
    """
    if not speech_text:
        return False
    
    completion_signals = [
        'hotovo', 'konec', 'dokončeno', 'to je vše', 'to je všechno',
        'stačí', 'už ne', 'už nechci', 'končím', 'finish', 'done'
    ]
    
    speech_lower = speech_text.lower().strip()
    return any(signal in speech_lower for signal in completion_signals)

# --- NOVÉ SYSTÉMOVÉ ENDPOINTY ---
@system_router.get("/run-migrations", response_class=HTMLResponse, name="admin_run_migrations")
def admin_run_migrations(request: Request):
    """
    Bezpečný endpoint pro jednorázové spuštění databázových migrací.
    Přidává chybějící sloupce, které mohly vzniknout při vývoji.
    """
    session = SessionLocal()
    results = {"success": [], "errors": []}
    
    # Kompletní seznam migrací pro synchronizaci DB s modely
    migrations = {
        "lessons": [
            ("base_difficulty", "VARCHAR(20)", "medium"),
        ],
        "test_sessions": [
            ("difficulty_score", "FLOAT", 50.0),
            ("failed_categories", "JSON", "[]"),
        ]
    }
    
    try:
        for table, columns in migrations.items():
            for column_name, column_type, default_value in columns:
                # Pro default hodnoty stringového typu potřebujeme uvozovky
                default_sql = f"'{default_value}'" if isinstance(default_value, str) else default_value
                
                try:
                    # Zkusit přidat sloupec
                    session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type} DEFAULT {default_sql}"))
                    session.commit()
                    results["success"].append(f"✅ Sloupec '{column_name}' úspěšně přidán do tabulky '{table}'.")
                except Exception as e:
                    # Pokud sloupec již existuje, ignorovat chybu
                    if "already exists" in str(e) or "duplicate column" in str(e):
                        results["success"].append(f"☑️ Sloupec '{column_name}' v tabulce '{table}' již existuje.")
                    else:
                        results["errors"].append(f"❌ Chyba při přidávání sloupce '{column_name}': {e}")
                    session.rollback() # Důležitý rollback po každé chybě
                    
        if not results["errors"]:
            message = "Všechny migrace proběhly úspěšně!"
        else:
            message = "Některé migrace selhaly. Zkontrolujte logy."
            
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": message,
            "details": results,
            "back_url": "/admin/dashboard",
            "back_text": "Zpět na dashboard"
        })

    except Exception as e:
        session.rollback()
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"Kritická chyba při migraci: {e}",
            "back_url": "/admin/dashboard",
            "back_text": "Zpět na dashboard"
        })
    finally:
        session.close()


@admin_router.get("/lessons/new", response_class=HTMLResponse, name="admin_new_lesson_get")
def admin_new_lesson_get(request: Request):
    form = {
        "title": "", "language": "cs", "script": "", "questions": "",
        "description": "", "lesson_number": "0", "lesson_type": "standard", "required_score": "90.0",
        "title.errors": [], "language.errors": [], "script.errors": [], "questions.errors": [],
        "description.errors": [], "lesson_number.errors": [], "lesson_type.errors": [], "required_score.errors": []
    }
    return templates.TemplateResponse("admin/lesson_form.html", {"request": request, "lesson": None, "form": form})