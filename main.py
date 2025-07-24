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

@admin_router.get("/", response_class=HTMLResponse)
def admin_root(request: Request):
    # Přesměrování na seznam uživatelů (jako ve Flasku)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)

@admin_router.get("/users", response_class=HTMLResponse, name="admin_list_users")
def admin_list_users(request: Request):
    session = SessionLocal()
    try:
        # FORCE migrace při každém načtení
        logger.info("🔧 Spouštím force migrace...")
        
        # 1. Přidej current_lesson_level do users
        try:
            session.execute(text("ALTER TABLE users ADD COLUMN current_lesson_level INTEGER DEFAULT 0"))
            session.commit()
            logger.info("✅ current_lesson_level přidán")
        except Exception as e:
            if "already exists" in str(e) or "duplicate column" in str(e):
                logger.info("✅ current_lesson_level již existuje")
            else:
                logger.warning(f"Chyba při přidávání current_lesson_level: {e}")
            session.rollback()
        
        # 2. Přidej lesson sloupce
        try:
            session.execute(text("ALTER TABLE lessons ADD COLUMN lesson_number INTEGER DEFAULT 0"))
            session.execute(text("ALTER TABLE lessons ADD COLUMN required_score FLOAT DEFAULT 90.0"))
            session.execute(text("ALTER TABLE lessons ADD COLUMN lesson_type VARCHAR(20) DEFAULT 'standard'"))
            session.execute(text("ALTER TABLE lessons ADD COLUMN description TEXT"))
            session.commit()
            logger.info("✅ lesson sloupce přidány")
        except Exception as e:
            if "already exists" in str(e) or "duplicate column" in str(e):
                logger.info("✅ lesson sloupce již existují")
            else:
                logger.warning(f"Chyba při přidávání lesson sloupců: {e}")
            session.rollback()
        
        # 3. Vytvoř user_progress tabulku
        try:
            create_progress_table = """
            CREATE TABLE IF NOT EXISTS user_progress (
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
            logger.info("✅ user_progress tabulka vytvořena")
        except Exception as e:
            logger.warning(f"Chyba při vytváření user_progress: {e}")
            session.rollback()
        
        # Bezpečné načtení uživatelů s fallback
        try:
            users = session.query(User).all()
        except Exception as query_error:
            logger.error(f"Chyba při načítání uživatelů: {query_error}")
            # Fallback - načti bez current_lesson_level
            users_raw = session.execute(text("SELECT id, name, phone, language, detail FROM users")).fetchall()
            users = []
            for row in users_raw:
                user = type('User', (), {
                    'id': row[0],
                    'name': row[1], 
                    'phone': row[2],
                    'language': row[3],
                    'detail': row[4],
                    'current_lesson_level': 0  # Default hodnota
                })()
                users.append(user)
        
        # Zajisti, že všichni uživatelé mají current_lesson_level
        for user in users:
            if not hasattr(user, 'current_lesson_level') or user.current_lesson_level is None:
                user.current_lesson_level = 0
        
        return templates.TemplateResponse("users/list.html", {"request": request, "users": users})
    except Exception as e:
        logger.error(f"❌ Kritická chyba v admin_list_users: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Fallback - prázdný seznam
        return templates.TemplateResponse("users/list.html", {"request": request, "users": []})
    finally:
        session.close()

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
    # Dočasně bez current_lesson_level
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
                "keywords": ["refraktometr", "titrace", "měření"],
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
        # KRITICKÁ MIGRACE - musí proběhnout PŘED načítáním dat
        logger.info("🔧 Spouštím kritickou migraci pro lessons...")
        
        # 1. Přidej description sloupec
        try:
            session.execute(text("ALTER TABLE lessons ADD COLUMN description TEXT"))
            session.commit()
            logger.info("✅ Description sloupec přidán")
        except Exception as e:
            if "already exists" in str(e) or "duplicate column" in str(e):
                logger.info("✅ Description sloupec již existuje")
            else:
                logger.warning(f"Chyba při přidávání description: {e}")
            session.rollback()
        
        # 2. Přidej další potřebné sloupce pro budoucí použití
        try:
            session.execute(text("ALTER TABLE lessons ADD COLUMN lesson_number INTEGER DEFAULT 0"))
            session.execute(text("ALTER TABLE lessons ADD COLUMN required_score FLOAT DEFAULT 90.0"))
            session.execute(text("ALTER TABLE lessons ADD COLUMN lesson_type VARCHAR(20) DEFAULT 'standard'"))
            session.commit()
            logger.info("✅ Další lesson sloupce přidány")
        except Exception as e:
            if "already exists" in str(e) or "duplicate column" in str(e):
                logger.info("✅ Další lesson sloupce již existují")
            else:
                logger.warning(f"Chyba při přidávání dalších sloupců: {e}")
            session.rollback()
        
        # 3. Nyní teprve načti data
        lessons = session.query(Lesson).order_by(Lesson.id.desc()).all()
        logger.info(f"✅ Načteno {len(lessons)} lekcí")
        
        session.close()
        return templates.TemplateResponse("lessons/list.html", {"request": request, "lessons": lessons})
        
    except Exception as e:
        session.close()
        logger.error(f"❌ KRITICKÁ CHYBA při načítání lekcí: {e}")
        logger.error(f"❌ Traceback: {str(e)}")
        
        # Zkus vytvořit tabulku znovu
        try:
            from app.database import Base, engine
            Base.metadata.create_all(engine)
            logger.info("✅ Tabulky znovu vytvořeny")
        except Exception as create_error:
            logger.error(f"❌ Chyba při vytváření tabulek: {create_error}")
        
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"❌ Databázová chyba při načítání lekcí.\n\nChyba: {str(e)}\n\nZkuste obnovit stránku za chvíli.",
            "back_url": "/admin/users",
            "back_text": "Zpět na uživatele"
        })

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
    
    # Pro Lekci 0 a nové lekce s otázkami použij novou template
    if lesson.title.startswith("Lekce 0") or (lesson.questions and isinstance(lesson.questions, list) and len(lesson.questions) > 0 and isinstance(lesson.questions[0], dict)):
        session.close()
        return templates.TemplateResponse("lessons/edit.html", {"request": request, "lesson": lesson})
    
    # Pro staré lekce použij původní template
    form = {"title": lesson.title, "language": lesson.language, "script": lesson.script, "questions": lesson.questions, "title.errors": [], "language.errors": [], "script.errors": [], "questions.errors": []}
    session.close()
    return templates.TemplateResponse("lessons/form.html", {"request": request, "lesson": lesson, "form": form})

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
            
            if not title:
                session.close()
                return templates.TemplateResponse("lessons/edit.html", {
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
                for i, question in enumerate(lesson.questions):
                    if isinstance(question, dict):
                        question['enabled'] = str(i) in enabled_questions
            
            session.commit()
            logger.info(f"✅ Lekce {lesson.id} aktualizována: {len(enabled_questions)} aktivních otázek")
            session.close()
            return RedirectResponse(url="/admin/lessons", status_code=status.HTTP_302_FOUND)
        
        # Pro staré lekce - původní logika
        title = form_data.get("title", "")
        language = form_data.get("language", "cs")
        script = form_data.get("script", "")
        questions = form_data.get("questions", "")
        
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
        session.commit()
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Chyba při editaci lekce {id}: {e}")
        session.close()
        return templates.TemplateResponse("lessons/edit.html", {
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
    logger.info(f"Attempt ID: {request.query_params.get('attempt_id')}")
    
    # Získání parametrů hovoru
    form = await request.form()
    caller_country = form.get("CallerCountry", "")
    to_country = form.get("ToCountry", "")
    logger.info(f"Volající: {caller_country} -> {to_country}")
    
    response = VoiceResponse()
    
    # Uvítání s funkčním TTS
    response.say(
        "Vítejte u AI asistenta pro výuku jazyků!",
        language="cs-CZ",
        rate="0.9",
        voice="Google.cs-CZ-Standard-A"
    )
    
    response.say(
        "Můžete se mě zeptat na cokoliv nebo mi říct, co vás zajímá.",
        language="cs-CZ",
        rate="0.9",
        voice="Google.cs-CZ-Standard-A"
    )
    
    # Gather pro zachycení hlasového vstupu
    gather = response.gather(
        input='speech',
        timeout=10,
        speech_timeout='auto',
        action='/voice/process',
        method='POST',
        language='cs-CZ',
        speech_model='phone_call'
    )
    
    gather.say(
        "Mluvte prosím, naslouchám...",
        language="cs-CZ",
        rate="0.9",
        voice="Google.cs-CZ-Standard-A"
    )
    
    # Fallback pokud uživatel neodpoví
    response.say(
        "Nerozuměl jsem vám. Zkuste to prosím znovu nebo hovor ukončete.",
        language="cs-CZ",
        rate="0.9",
        voice="Google.cs-CZ-Standard-A"
    )
    
    response.hangup()
    
    logger.info(f"TwiML odpověď (hybridní): {response}")
    return Response(content=str(response), media_type="text/xml")

@app.post("/voice/process")
async def process_speech(request: Request):
    """Zpracuje hlasový vstup od uživatele s inteligentním systémem lekcí"""
    logger.info("Přijat hlasový vstup od uživatele")
    
    form = await request.form()
    speech_result = form.get('SpeechResult', '')
    confidence = form.get('Confidence', '0')
    
    logger.info(f"Rozpoznaná řeč: '{speech_result}' (confidence: {confidence})")
    
    response = VoiceResponse()
    
    if speech_result:
        try:
            openai_api_key = os.getenv('OPENAI_API_KEY')
            if openai_api_key:
                import openai
                client = openai.OpenAI(api_key=openai_api_key)
                
                logger.info("🤖 Generuji odpověď pomocí OpenAI GPT...")
                
                # Získej attempt_id z query parametrů
                attempt_id = request.query_params.get('attempt_id')
                current_lesson = None
                current_user = None
                lesson_content = ""
                
                session = SessionLocal()
                try:
                    if attempt_id:
                        attempt = session.query(Attempt).get(int(attempt_id))
                        if attempt:
                            current_lesson = attempt.lesson
                            current_user = attempt.user
                            logger.info(f"👤 Uživatel: {current_user.name}, Lekce: {current_lesson.title}")
                    
                    # Pokud není attempt, najdi posledního uživatele
                    if not current_user:
                        current_user = session.query(User).order_by(User.id.desc()).first()
                    
                    if not current_user:
                        logger.error("❌ Žádný uživatel nenalezen!")
                        session.close()
                        response.say("Omlouvám se, došlo k technické chybě.", language="cs-CZ")
                        response.hangup()
                        return Response(content=str(response), media_type="text/xml")
                    
                    # INTELIGENTNÍ VÝBĚR LEKCE PODLE POKROKU UŽIVATELE
                    user_level = getattr(current_user, 'current_lesson_level', 0)
                    logger.info(f"🎯 Uživatel je na úrovni: {user_level}")
                    
                    # Najdi správnou lekci podle úrovně uživatele
                    if user_level == 0:
                        # Vstupní test - Lekce 0
                        target_lesson = session.query(Lesson).filter(
                            Lesson.title.contains("Lekce 0")
                        ).first()
                        
                        if target_lesson and target_lesson.questions:
                            # VSTUPNÍ TEST - konkrétní otázky
                            enabled_questions = []
                            if isinstance(target_lesson.questions, list):
                                enabled_questions = [
                                    q for q in target_lesson.questions 
                                    if isinstance(q, dict) and q.get('enabled', True)
                                ]
                            
                            if enabled_questions:
                                # Vyber náhodnou otázku pro testování
                                import random
                                test_question = random.choice(enabled_questions)
                                
                                system_prompt = f"""Jsi AI examinátor pro vstupní test z obráběcích kapalin a servisu.

TESTOVACÍ OTÁZKA:
{test_question.get('question', '')}

SPRÁVNÁ ODPOVĚĎ:
{test_question.get('correct_answer', '')}

KLÍČOVÁ SLOVA:
{', '.join(test_question.get('keywords', []))}

INSTRUKCE:
1. Porovnej odpověď studenta se správnou odpovědí
2. Vyhodnoť na škále 0-100%
3. Poskytni krátkou zpětnou vazbu
4. POVINNĚ přidej na konec: [SKÓRE: XX%]

PŘÍKLAD: "Správně! Obráběcí kapaliny skutečně slouží k chlazení a mazání. [SKÓRE: 90%]"

Student odpověděl: "{speech_result}"
Vyhodnoť jeho odpověď."""

                                gpt_response = client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[
                                        {"role": "system", "content": system_prompt}
                                    ],
                                    max_tokens=150,
                                    temperature=0.3
                                )
                                
                                ai_answer = gpt_response.choices[0].message.content
                                
                                # Extrakce skóre
                                import re
                                score_match = re.search(r'\[SKÓRE:\s*(\d+)%\]', ai_answer)
                                current_score = int(score_match.group(1)) if score_match else 0
                                clean_answer = re.sub(r'\[SKÓRE:\s*\d+%\]', '', ai_answer).strip()
                                
                                logger.info(f"📊 Vstupní test skóre: {current_score}%")
                                
                                # Kontrola postupu do Lekce 1
                                if current_score >= 90:
                                    current_user.current_lesson_level = 1
                                    session.commit()
                                    clean_answer += f" Gratulujeme! Dosáhli jste {current_score}% a postoupili do Lekce 1!"
                                    logger.info(f"🎉 Uživatel postoupil do Lekce 1")
                                else:
                                    clean_answer += f" Dosáhli jste {current_score}%. Pro postup potřebujete alespoň 90%. Zkuste to znovu!"
                                
                                response.say(clean_answer, language="cs-CZ", rate="0.9")
                            else:
                                response.say("Vstupní test není připraven. Kontaktujte administrátora.", language="cs-CZ")
                        else:
                            response.say("Vstupní test nebyl nalezen. Kontaktujte administrátora.", language="cs-CZ")
                    
                    elif user_level >= 1:
                        # ŠKOLNÍ LEKCE - najdi lekci podle úrovně
                        target_lesson = session.query(Lesson).filter(
                            Lesson.level == "beginner"
                        ).first()
                        
                        if target_lesson and target_lesson.script:
                            lesson_content = target_lesson.script
                            
                            # AUTOMATICKÉ GENEROVÁNÍ OTÁZEK Z OBSAHU LEKCE
                            from app.services.openai_service import OpenAIService
                            openai_service = OpenAIService()
                            
                            # Generuj 10 náhodných otázek z obsahu lekce
                            generated_questions = openai_service.generate_questions_from_lesson(
                                lesson_script=lesson_content,
                                language="cs",
                                num_questions=10
                            )
                            
                            if generated_questions:
                                # Vyber náhodnou otázku pro testování
                                import random
                                test_question = random.choice(generated_questions)
                                
                                system_prompt = f"""Jsi AI učitel pro lekci: {target_lesson.title}

OBSAH LEKCE:
{lesson_content[:500]}...

TESTOVACÍ OTÁZKA:
{test_question.get('question', '')}

SPRÁVNÁ ODPOVĚĎ:
{test_question.get('correct_answer', '')}

INSTRUKCE:
1. Vyhodnoť odpověď studenta podle obsahu lekce
2. Porovnej se správnou odpovědí
3. Poskytni konstruktivní zpětnou vazbu
4. POVINNĚ přidej skóre: [SKÓRE: XX%]

Student odpověděl: "{speech_result}"
Vyhodnoť jeho odpověď podle lekce."""

                                gpt_response = client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[
                                        {"role": "system", "content": system_prompt}
                                    ],
                                    max_tokens=200,
                                    temperature=0.4
                                )
                                
                                ai_answer = gpt_response.choices[0].message.content
                                
                                # Extrakce skóre
                                import re
                                score_match = re.search(r'\[SKÓRE:\s*(\d+)%\]', ai_answer)
                                current_score = int(score_match.group(1)) if score_match else 0
                                clean_answer = re.sub(r'\[SKÓRE:\s*\d+%\]', '', ai_answer).strip()
                                
                                logger.info(f"📊 Lekce {user_level} skóre: {current_score}%")
                                
                                # Kontrola postupu do další lekce
                                if current_score >= 90:
                                    current_user.current_lesson_level = user_level + 1
                                    session.commit()
                                    clean_answer += f" Výborně! Dosáhli jste {current_score}% a postoupili do další lekce!"
                                    logger.info(f"🎉 Uživatel postoupil do lekce {user_level + 1}")
                                else:
                                    clean_answer += f" Dosáhli jste {current_score}%. Pro postup potřebujete alespoň 90%."
                                
                                response.say(clean_answer, language="cs-CZ", rate="0.9")
                            else:
                                # Fallback - obecná konverzace o lekci
                                system_prompt = f"""Jsi AI učitel. Odpovídej na otázky o této lekci:

{lesson_content}

Student se zeptal: "{speech_result}"
Odpověz mu jasně a srozumitelně v češtině."""

                                gpt_response = client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[
                                        {"role": "system", "content": system_prompt}
                                    ],
                                    max_tokens=150,
                                    temperature=0.7
                                )
                                
                                ai_answer = gpt_response.choices[0].message.content
                                response.say(ai_answer, language="cs-CZ", rate="0.9")
                        else:
                            response.say("Lekce pro vaši úroveň nebyla nalezena. Kontaktujte administrátora.", language="cs-CZ")
                    
                except Exception as db_error:
                    logger.error(f"❌ Chyba při práci s databází: {db_error}")
                    response.say("Došlo k technické chybě. Zkuste to prosím později.", language="cs-CZ")
                finally:
                    session.close()
            else:
                logger.warning("⚠️ OPENAI_API_KEY není nastaven")
                response.say("AI služba není dostupná.", language="cs-CZ")
        
        except Exception as e:
            logger.error(f"❌ Chyba při zpracování: {e}")
            response.say("Došlo k neočekávané chybě.", language="cs-CZ")
        
        # Další kolo konverzace
        gather = response.gather(
            input='speech',
            timeout=15,
            action='/voice/process',
            method='POST',
            language='cs-CZ',
            speech_model='phone_call'
        )
        
        gather.say(
            "Máte další otázku nebo chcete pokračovat?",
            language="cs-CZ",
            rate="0.9"
        )
        
        response.say(
            "Děkuji za rozhovor. Na shledanou!",
            language="cs-CZ",
            rate="0.9"
        )
    else:
        response.say(
            "Nerozuměl jsem vám. Hovor ukončuji.",
            language="cs-CZ",
            rate="0.9"
        )
    
    response.hangup()
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