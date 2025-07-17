from flask import Blueprint, request, Response, url_for, current_app
from app.services.twilio_service import TwilioService
from app.services.openai_service import OpenAIService
from app.services.realtime_service import handle_media_stream_websocket
from app.database import db
from app.models import Attempt, User, Lesson, Answer
import logging
import traceback
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream, Gather
from flask_wtf.csrf import CSRFProtect
import openai
import requests
import os
import json
import base64
from dotenv import load_dotenv
import re

load_dotenv()

logger = logging.getLogger(__name__)

voice_bp = Blueprint('voice', __name__)
twilio_service = TwilioService()
openai_service = OpenAIService()

# Konfigurace
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_ASSISTANT_ID = os.getenv('TWILIO_ASSISTANT_ID')

# Kontrola povinných environment variables
missing_vars = []
if not OPENAI_API_KEY:
    missing_vars.append('OPENAI_API_KEY')
if not TWILIO_ACCOUNT_SID:
    missing_vars.append('TWILIO_ACCOUNT_SID')
if not TWILIO_AUTH_TOKEN:
    missing_vars.append('TWILIO_AUTH_TOKEN')

if missing_vars:
    logger.warning(f"Chybí některé požadované proměnné prostředí: {', '.join(missing_vars)}")
    logger.warning("Některé funkce nemusí fungovat správně")
    
    # Pro testování povolíme spuštění i bez všech proměnných
    # if os.getenv('TESTING') != 'true':
    #     raise ValueError(f"Chybí některé požadované proměnné prostředí: {', '.join(missing_vars)}")

if not TWILIO_ASSISTANT_ID:
    logger.warning("TWILIO_ASSISTANT_ID není nastavena - některé funkce nebudou dostupné")

SYSTEM_MESSAGE = (
    "Jsi užitečný a přátelský AI asistent, který rád komunikuje v češtině. "
    "Máš rád vtipy a jsi připraven pomoci s jakýmkoliv dotazem. "
    "Vždy zůstávej pozitivní a přátelský. "
    "Odpovídej stručně a jasně, ideálně do 2-3 vět. "
    "Pokud neznáš odpověď, upřímně to přiznej."
)
VOICE = 'alloy'
MODEL = 'gpt-4.1-turbo-preview'  # Aktualizovaná verze modelu
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created'
]

# Konfigurace pro lepší detekci řeči
SPEECH_DETECTION = {
    "type": "server_vad",
    "threshold": 0.5,  # Citlivost detekce řeči (0.0 - 1.0)
    "silence_duration_ms": 1000,  # Doba ticha pro ukončení řeči
    "speech_duration_ms": 300  # Minimální délka řeči pro detekci
}

# Konfigurace pro lepší audio kvalitu
AUDIO_CONFIG = {
    "input_audio_format": "g711_ulaw",
    "output_audio_format": "g711_ulaw",
    "sample_rate": 8000,
    "channels": 1
}

@voice_bp.route("/", methods=["GET", "POST"])
def voice():
    """Zpracuje příchozí hovor a vytvoří interaktivní hlasové menu."""
    try:
        logger.info("=== ZAČÁTEK ZPRACOVÁNÍ VOICE WEBHOOKU ===")
        
        # Získání attempt_id z parametrů
        attempt_id = request.args.get('attempt_id')
        logger.info(f"Attempt ID: {attempt_id}")
        
        # Vytvoření TwiML odpovědi
        response = VoiceResponse()
        
        # Přidání uvítací zprávy
        response.say(
            "Vítejte u AI asistenta pro výuku jazyků.",
            language="cs-CZ",
            voice="Google.cs-CZ-Standard-A",
            rate="0.9"
        )
        
        if attempt_id:
            # Pokud máme attempt_id, načteme lekci a připojíme k OpenAI Realtime API
            try:
                attempt = Attempt.query.get(attempt_id)
                if attempt and attempt.lesson:
                    lesson = attempt.lesson
                    response.say(
                        f"Začínáme s lekcí: {lesson.title}",
                        language="cs-CZ",
                        voice="Google.cs-CZ-Standard-A",
                        rate="0.9"
                    )
                    response.pause(length=1)
                    
                    # Krátké představení lekce
                    response.say(
                        f"Téma lekce: {lesson.script[:200]}...",
                        language="cs-CZ",
                        voice="Google.cs-CZ-Standard-A",
                        rate="0.8"
                    )
                    response.pause(length=1)
                    
                    # Připojení k OpenAI Realtime API
                    response.say(
                        "Nyní vás připojuji k AI asistentovi, se kterým si můžete povídat o lekci.",
                        language="cs-CZ",
                        voice="Google.cs-CZ-Standard-A",
                        rate="0.9"
                    )
                    
                    # Přesměrování na OpenAI Realtime endpoint
                    base_url = current_app.config.get("WEBHOOK_BASE_URL", "https://lecture-app-production.up.railway.app").rstrip("/")
                    response.redirect(f"{base_url}/voice/?attempt_id={attempt_id}")
                else:
                    response.say(
                        "Lekce nebyla nalezena. Zkuste to prosím znovu.",
                        language="cs-CZ",
                        voice="Google.cs-CZ-Standard-A"
                    )
                    response.hangup()
            except Exception as e:
                logger.error(f"Chyba při načítání lekce: {str(e)}")
                response.say(
                    "Došlo k chybě při načítání lekce. Zkuste to prosím znovu.",
                    language="cs-CZ",
                    voice="Google.cs-CZ-Standard-A"
                )
                response.hangup()
        else:
            # Obecné uvítání bez konkrétní lekce - také připojíme k AI asistentovi
            response.say(
                "Připojuji vás k AI asistentovi pro obecnou konverzaci.",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A",
                rate="0.9"
            )
            
            # Přesměrování na OpenAI Realtime endpoint bez attempt_id
            base_url = current_app.config.get("WEBHOOK_BASE_URL", "https://lecture-app-production.up.railway.app").rstrip("/")
            response.redirect(f"{base_url}/voice/")
        
        logger.info("TwiML odpověď:")
        logger.info(str(response))
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Neočekávaná chyba při zpracování hovoru: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        response = VoiceResponse()
        response.say(
            "Omlouváme se, došlo k neočekávané chybě. Zkuste to prosím znovu později.",
            language="cs-CZ",
            voice="Google.cs-CZ-Standard-A",
            rate="0.9"
        )
        response.hangup()
        return Response(str(response), mimetype='text/xml')

@voice_bp.route("/questions", methods=["GET", "POST"])
def questions():
    """Zpracuje otázky k lekci."""
    try:
        attempt_id = request.args.get('attempt_id')
        question_index = int(request.args.get('question_index', 0))
        
        logger.info(f"=== ZAČÁTEK ZPRACOVÁNÍ OTÁZEK ===")
        logger.info(f"Zpracovávám otázky pro attempt_id: {attempt_id}, question_index: {question_index}")
        
        if not attempt_id:
            logger.error("Chybí attempt_id")
            response = VoiceResponse()
            response.say("Chybí identifikace pokusu.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
            response.hangup()
            return Response(str(response), mimetype='text/xml')
        
        logger.info(f"Hledám pokus s ID: {attempt_id}")
        attempt = Attempt.query.get(attempt_id)
        logger.info(f"Nalezený pokus: {attempt}")
        
        if not attempt:
            logger.error(f"Pokus s ID {attempt_id} nebyl nalezen")
            response = VoiceResponse()
            response.say("Lekce nebyla nalezena.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
            response.hangup()
            return Response(str(response), mimetype='text/xml')
        
        logger.info(f"Pokus nalezen, kontroluji lekci: {attempt.lesson}")
        if not attempt.lesson:
            logger.error(f"Pokus {attempt_id} nemá přiřazenou lekci")
            response = VoiceResponse()
            response.say("Lekce nebyla nalezena.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
            response.hangup()
            return Response(str(response), mimetype='text/xml')
        
        logger.info(f"Načtená lekce: {attempt.lesson.title}")
        logger.info(f"Typ otázek: {type(attempt.lesson.questions)}")
        logger.info(f"Otázky z databáze: {attempt.lesson.questions}")
        
        # Načtení otázek z lekce s lepším error handlingem
        questions_data = []
        try:
            if attempt.lesson.questions:
                logger.info("Otázky existují, začínám zpracování...")
                # Pokud jsou otázky už dict/JSON objekt, použij je přímo
                if isinstance(attempt.lesson.questions, dict):
                    logger.info("Otázky jsou dict objekt")
                    if 'all' in attempt.lesson.questions:
                        questions_data = attempt.lesson.questions['all']
                        logger.info(f"Úspěšně načteno {len(questions_data)} otázek z dict struktury")
                        logger.info(f"První otázka: {questions_data[0] if questions_data else 'Žádná'}")
                    else:
                        logger.warning("Dict struktura neobsahuje klíč 'all'")
                        logger.info(f"Dostupné klíče: {list(attempt.lesson.questions.keys())}")
                elif isinstance(attempt.lesson.questions, str):
                    logger.info("Otázky jsou string, pokouším se parsovat jako JSON")
                    # Pokud je to string, pokus se ho parsovat jako JSON
                    questions_data = json.loads(attempt.lesson.questions)
                    logger.info(f"Úspěšně načteno {len(questions_data)} otázek z JSON stringu")
                else:
                    logger.warning(f"Neočekávaný typ otázek: {type(attempt.lesson.questions)}")
            else:
                logger.warning("Lekce nemá žádné otázky")
        except json.JSONDecodeError as e:
            logger.error(f"Chyba při parsování JSON otázek: {str(e)}")
            logger.error(f"Obsah questions pole: {attempt.lesson.questions}")
        except Exception as e:
            logger.error(f"Neočekávaná chyba při načítání otázek: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        
        logger.info(f"Finální questions_data: {questions_data}")
        logger.info(f"Počet otázek: {len(questions_data)}")
        logger.info(f"Question index: {question_index}")
        
        response = VoiceResponse()
        
        if questions_data and question_index < len(questions_data):
            question = questions_data[question_index]
            logger.info(f"Zpracovávám otázku {question_index + 1}: {question}")
            
            response.say(
                f"Otázka číslo {question_index + 1}:",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A"
            )
            response.pause(length=0.5)
            
            # Bezpečné získání textu otázky
            question_text = question.get('question', '') if isinstance(question, dict) else str(question)
            logger.info(f"Text otázky: {question_text}")
            
            if question_text:
                response.say(
                    question_text,
                    language="cs-CZ",
                    voice="Google.cs-CZ-Standard-A",
                    rate="0.8"
                )
            else:
                response.say(
                    "Otázka není k dispozici.",
                    language="cs-CZ",
                    voice="Google.cs-CZ-Standard-A"
                )
            
            # Gather pro odpověď
            gather = Gather(
                input='speech',
                timeout=15,
                speech_timeout=5,
                action=url_for('voice.handle_answer', attempt_id=attempt_id, question_index=question_index, _external=True),
                method='POST'
            )
            gather.say(
                "Prosím odpovězte, nebo řekněte 'otázka' pokud se chcete na něco zeptat:",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A"
            )
            response.append(gather)
            
            # Pokud není odpověď, přejdeme na další otázku
            response.redirect(url_for('voice.questions', attempt_id=attempt_id, question_index=question_index+1, _external=True))
        else:
            # Konec otázek nebo žádné otázky
            logger.info("Žádné otázky k zobrazení nebo konec otázek")
            if not questions_data:
                logger.info("Žádné otázky nejsou k dispozici")
                response.say(
                    "Pro tuto lekci nejsou k dispozici žádné otázky.",
                    language="cs-CZ",
                    voice="Google.cs-CZ-Standard-A"
                )
            else:
                logger.info("Konec všech otázek")
                response.say(
                    "To byly všechny otázky. Děkuji za váš čas a pozornost.",
                    language="cs-CZ",
                    voice="Google.cs-CZ-Standard-A"
                )
            
            response.say(
                "Lekce je dokončena. Na shledanou!",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A"
            )
            response.hangup()
        
        logger.info(f"=== KONEC ZPRACOVÁNÍ OTÁZEK ===")
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"KRITICKÁ CHYBA při zpracování otázek: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        response = VoiceResponse()
        response.say("Došlo k chybě při zpracování otázek. Lekce bude ukončena.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
        response.hangup()
        return Response(str(response), mimetype='text/xml')

@voice_bp.route("/handle_input", methods=["POST"])
def handle_input():
    """Zpracuje obecný vstup od uživatele."""
    try:
        speech_result = request.form.get('SpeechResult', '')
        digits = request.form.get('Digits', '')
        attempt_id = request.args.get('attempt_id')
        
        logger.info(f"Přijatý vstup - Řeč: '{speech_result}', Číslice: '{digits}'")
        
        response = VoiceResponse()
        
        if digits == '*':
            response.say("Děkuji za váš hovor. Na shledanou.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
            response.hangup()
        elif speech_result:
            # Kontrola klíčových slov pro otázky
            speech_lower = speech_result.lower()
            if any(word in speech_lower for word in ['otázka', 'otázku', 'zeptat', 'ptám']):
                response.say("Jaká je vaše otázka?", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
                
                gather = response.gather(
                    input='speech',
                    action=url_for('voice.handle_user_question', attempt_id=attempt_id, _external=True),
                    speech_timeout=10,
                    timeout=15,
                    language='cs-CZ'
                )
                gather.say("Poslouchám...", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
                
                # Fallback pokud není odpověď
                if attempt_id:
                    response.redirect(url_for('voice.questions', attempt_id=attempt_id, _external=True))
                else:
                    response.say("Děkuji za váš zájem. Na shledanou!", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
                    response.hangup()
            else:
                # Obecné zpracování řeči
                response.say(
                    f"Slyšel jsem: {speech_result}. Pokud máte otázku, řekněte 'otázka'.",
                    language="cs-CZ",
                    voice="Google.cs-CZ-Standard-A"
                )
                response.pause(length=1)
                
                if attempt_id:
                    response.say("Pokračujeme v lekci.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
                    response.redirect(url_for('voice.questions', attempt_id=attempt_id, _external=True))
                else:
                    response.say("Na shledanou!", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
                    response.hangup()
        else:
            response.say("Nerozuměl jsem vašemu vstupu. Na shledanou.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
            response.hangup()
        
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Chyba při zpracování vstupu: {str(e)}")
        response = VoiceResponse()
        response.say("Došlo k chybě. Na shledanou.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
        response.hangup()
        return Response(str(response), mimetype='text/xml')

@voice_bp.route("/handle_answer", methods=["POST"])
def handle_answer():
    """Zpracuje odpověď uživatele s AI vyhodnocením a uloží do databáze."""
    response = VoiceResponse()
    
    # Získej parametry z požadavku
    attempt_id = request.values.get('attempt_id')
    question_index = int(request.values.get('question_index', 0))
    speech_result = request.values.get('SpeechResult', '').strip()
    
    logging.info(f"Zpracovávám odpověď pro attempt_id: {attempt_id}, question_index: {question_index}")
    logging.info(f"Uživatelova odpověď: {speech_result}")
    
    try:
        if speech_result and attempt_id:
            # Kontrola, zda uživatel chce položit otázku
            speech_lower = speech_result.lower()
            if any(word in speech_lower for word in ['otázka', 'otázku', 'zeptat', 'ptám']):
                logger.info("Uživatel chce položit otázku místo odpovědi")
                response.say("Jaká je vaše otázka?", language="cs-CZ")
                
                gather = response.gather(
                    input='speech',
                    action=url_for('voice.handle_user_question', attempt_id=attempt_id, _external=True),
                    speech_timeout=10,
                    timeout=15,
                    language='cs-CZ'
                )
                gather.say("Poslouchám...", language="cs-CZ")
                
                # Fallback - návrat k otázce
                response.redirect(url_for('voice.questions', attempt_id=attempt_id, question_index=question_index, _external=True))
                return Response(str(response), mimetype='text/xml')
            
            # Získej pokus a otázky
            attempt = Attempt.query.get(attempt_id)
            if attempt and attempt.lesson and attempt.lesson.questions:
                # Načtení otázek z lekce s lepším error handlingem
                questions_data = []
                try:
                    if attempt.lesson.questions:
                        # Pokud jsou otázky už dict/JSON objekt, použij je přímo
                        if isinstance(attempt.lesson.questions, dict):
                            if 'all' in attempt.lesson.questions:
                                questions_data = attempt.lesson.questions['all']
                                logger.info(f"Úspěšně načteno {len(questions_data)} otázek z dict struktury")
                            else:
                                logger.warning("Dict struktura neobsahuje klíč 'all'")
                        elif isinstance(attempt.lesson.questions, str):
                            # Pokud je to string, pokus se ho parsovat jako JSON
                            questions_data = json.loads(attempt.lesson.questions)
                            logger.info(f"Úspěšně načteno {len(questions_data)} otázek z JSON stringu")
                        else:
                            logger.warning(f"Neočekávaný typ otázek: {type(attempt.lesson.questions)}")
                    else:
                        logger.warning("Lekce nemá žádné otázky")
                except json.JSONDecodeError as e:
                    logger.error(f"Chyba při parsování JSON otázek: {str(e)}")
                    logger.error(f"Obsah questions pole: {attempt.lesson.questions}")
                except Exception as e:
                    logger.error(f"Neočekávaná chyba při načítání otázek: {str(e)}")
                
                if questions_data and question_index < len(questions_data):
                    current_question = questions_data[question_index]
                    
                    # Bezpečné získání textu otázky a odpovědi
                    question_text = current_question.get('question', '') if isinstance(current_question, dict) else str(current_question)
                    correct_answer = current_question.get('answer', '') if isinstance(current_question, dict) else ''
                    
                    if not question_text:
                        logger.error(f"Prázdný text otázky na indexu {question_index}")
                        response.say("Chyba při načítání otázky. Přecházíme na další.", language="cs-CZ")
                        response.redirect(url_for('voice.questions', attempt_id=attempt_id, question_index=question_index+1, _external=True))
                        return Response(str(response), mimetype='text/xml')
                    
                    # Informuj uživatele o vyhodnocování
                    response.say("Vyhodnocuji vaši odpověď pomocí AI...", language="cs-CZ")
                    
                    # Vyhodnoť odpověď pomocí AI
                    logger.info(f"Spouštím AI vyhodnocení odpovědi: '{speech_result}' na otázku: '{question_text}'")
                    evaluation = openai_service.evaluate_voice_answer(
                        user_answer=speech_result,
                        correct_answer=correct_answer,
                        question=question_text,
                        language="cs"
                    )
                    
                    if evaluation:
                        # Ulož odpověď do databáze
                        answer = Answer(
                            attempt_id=attempt_id,
                            question_index=question_index,
                            question_text=question_text,
                            correct_answer=correct_answer,
                            user_answer=speech_result,
                            score=evaluation.get('score', 0),
                            is_correct=evaluation.get('is_correct', False),
                            feedback=evaluation.get('feedback', ''),
                            suggestions=evaluation.get('suggestions', '')
                        )
                        
                        db.session.add(answer)
                        db.session.commit()
                        
                        logger.info(f"Odpověď uložena s skóre: {evaluation.get('score', 0)}")
                        
                        # Poskytni zpětnou vazbu
                        if evaluation.get('is_correct', False):
                            response.say(f"Správně! {evaluation.get('feedback', '')}", language="cs-CZ")
                        else:
                            response.say(f"Bohužel ne. {evaluation.get('feedback', '')}", language="cs-CZ")
                            if evaluation.get('suggestions'):
                                response.say(f"Tip: {evaluation.get('suggestions')}", language="cs-CZ")
                        
                        # Přejdi na další otázku nebo ukonči
                        next_question_index = question_index + 1
                        if next_question_index < len(questions_data):
                            response.say("Přecházíme na další otázku.", language="cs-CZ")
                            response.redirect(url_for('voice.questions', attempt_id=attempt_id, question_index=next_question_index, _external=True))
                        else:
                            # Vypočítej celkové skóre a ukonči lekci
                            try:
                                attempt.score = attempt.calculate_overall_score()
                                attempt.status = "completed"
                                attempt.completed_at = db.func.now()
                                attempt.calculate_next_due()
                                db.session.commit()
                                
                                response.say(f"Gratulujeme! Dokončili jste lekci s celkovým skóre {attempt.score:.1f}%.", language="cs-CZ")
                            except Exception as e:
                                logger.error(f"Chyba při výpočtu skóre: {str(e)}")
                                response.say("Gratulujeme! Dokončili jste lekci.", language="cs-CZ")
                            
                            response.say("Děkujeme za váš čas. Na shledanou!", language="cs-CZ")
                            response.hangup()
                    else:
                        response.say("Omlouváme se, nepodařilo se vyhodnotit vaši odpověď. Zkuste to prosím znovu.", language="cs-CZ")
                        response.redirect(url_for('voice.questions', attempt_id=attempt_id, question_index=question_index, _external=True))
                else:
                    response.say("Všechny otázky byly zodpovězeny. Děkujeme!", language="cs-CZ")
                    response.hangup()
            else:
                response.say("Nepodařilo se najít otázky pro tuto lekci.", language="cs-CZ")
                response.hangup()
        else:
            response.say("Nerozuměl jsem vaší odpovědi. Zkuste to prosím znovu.", language="cs-CZ")
            response.redirect(f'/voice/answer?attempt_id={attempt_id}&question_index={question_index}')
            
    except Exception as e:
        logging.error(f"Chyba při zpracování odpovědi: {str(e)}")
        response.say("Omlouváme se, došlo k chybě. Zkuste to prosím později.", language="cs-CZ")
        response.hangup()
    
    return Response(str(response), mimetype='text/xml')

@voice_bp.route("/repeat", methods=["POST"])
def voice_repeat():
    """Opakování hlasového hovoru - přesměruje na hlavní voice endpoint."""
    try:
        attempt_id = request.args.get('attempt_id')
        logger.info(f"Opakování hovoru pro attempt_id: {attempt_id}")
        
        if not attempt_id:
            logger.error("Chybí attempt_id v parametrech")
            response = VoiceResponse()
            response.say("Chybí identifikace pokusu. Zavěšujeme.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
            response.hangup()
            return Response(str(response), mimetype='text/xml')
        
        # Přesměrujeme na hlavní voice endpoint s attempt_id
        response = VoiceResponse()
        response.redirect(url_for('voice.voice', attempt_id=attempt_id, _external=True))
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Chyba při opakování hovoru: {str(e)}")
        response = VoiceResponse()
        response.say("Došlo k neočekávané chybě. Zavěšujeme.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
        response.hangup()
        return Response(str(response), mimetype='text/xml')

@voice_bp.route("/chat", methods=["POST"])
def chat():
    """Jednoduchý chat endpoint pro testování."""
    try:
        logger.info("=== ZAČÁTEK ZPRACOVÁNÍ CHAT WEBHOOKU ===")
        
        # Získání hlasového vstupu
        speech_result = request.values.get('SpeechResult', '')
        logger.info(f"Přijat hlasový vstup: {speech_result}")
        
        response = VoiceResponse()
        
        if speech_result:
            response.say(
                f"Rozuměl jsem vašemu vstupu: {speech_result}",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A"
            )
        else:
            response.say(
                "Nerozuměl jsem vašemu vstupu.",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A"
            )
        
        response.hangup()
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Chyba při zpracování chat: {str(e)}")
        response = VoiceResponse()
        response.say("Došlo k chybě.", language="cs-CZ", voice="Google.cs-CZ-Standard-A")
        response.hangup()
        return Response(str(response), mimetype='text/xml')

@voice_bp.route("/question", methods=["POST"])
def handle_user_question():
    """Zpracuje obecnou otázku uživatele s využitím hierarchie zdrojů."""
    try:
        # Získání parametrů
        attempt_id = request.values.get('attempt_id')
        speech_result = request.values.get('SpeechResult', '').strip()
        
        logger.info(f"Zpracovávám otázku uživatele: {speech_result}")
        
        response = VoiceResponse()
        
        if not speech_result:
            response.say("Nerozuměl jsem vaší otázce. Zkuste to prosím znovu.", language="cs-CZ")
            response.redirect(url_for('voice.voice', attempt_id=attempt_id, _external=True))
            return Response(str(response), mimetype='text/xml')
        
        # Získání aktuální lekce
        current_lesson_data = None
        other_lessons_data = []
        
        if attempt_id:
            attempt = Attempt.query.get(attempt_id)
            if attempt and attempt.lesson:
                current_lesson_data = {
                    'title': attempt.lesson.title,
                    'script': attempt.lesson.script
                }
                
                # Získání dalších lekcí stejného jazyka a úrovně
                from app.models import Lesson
                other_lessons = Lesson.query.filter(
                    Lesson.id != attempt.lesson.id,
                    Lesson.language == attempt.lesson.language,
                    Lesson.level == attempt.lesson.level
                ).limit(5).all()
                
                other_lessons_data = [
                    {
                        'title': lesson.title,
                        'script': lesson.script
                    }
                    for lesson in other_lessons
                ]
        
        # Informování uživatele o zpracování
        response.say("Hledám odpověď na vaši otázku...", language="cs-CZ")
        
        # Získání odpovědi od AI
        ai_response = openai_service.answer_user_question(
            user_question=speech_result,
            current_lesson=current_lesson_data,
            other_lessons=other_lessons_data,
            language="cs"
        )
        
        if ai_response and ai_response.get('answer'):
            # Poskytnutí odpovědi
            answer_text = ai_response.get('answer', '')
            source = ai_response.get('source', 'unknown')
            confidence = ai_response.get('confidence', 0)
            explanation = ai_response.get('explanation', '')
            
            # Přečtení odpovědi
            response.say(answer_text, language="cs-CZ", rate="0.8")
            
            # Informace o zdroji (pokud je důvěra vysoká)
            if confidence > 70:
                if source == "current_lesson":
                    response.say("Tuto informaci jsem našel v aktuální lekci.", language="cs-CZ")
                elif source == "other_lessons":
                    response.say("Tuto informaci jsem našel v dalších lekcích.", language="cs-CZ")
                    related_lessons = ai_response.get('related_lessons', [])
                    if related_lessons:
                        response.say(f"Souvisí s lekcemi: {', '.join(related_lessons[:2])}", language="cs-CZ")
                elif source == "general_knowledge":
                    response.say("Tuto informaci jsem čerpal ze svých obecných znalostí.", language="cs-CZ")
            
            # Nabídka dalších otázek nebo pokračování
            response.pause(length=1)
            response.say("Máte další otázku, nebo chcete pokračovat v lekci?", language="cs-CZ")
            
            gather = response.gather(
                input='speech',
                action=url_for('voice.handle_user_question', attempt_id=attempt_id, _external=True),
                speech_timeout=10,
                timeout=15,
                language='cs-CZ'
            )
            gather.say("Řekněte 'otázka' pro další otázku nebo 'pokračovat' pro návrat k lekci.", language="cs-CZ")
            
            # Pokud není odpověď, pokračujeme v lekci
            if attempt_id:
                response.redirect(url_for('voice.questions', attempt_id=attempt_id, _external=True))
            else:
                response.say("Děkuji za váš zájem. Na shledanou!", language="cs-CZ")
                response.hangup()
        else:
            response.say("Omlouváme se, nepodařilo se najít odpověď na vaši otázku.", language="cs-CZ")
            if attempt_id:
                response.say("Pokračujeme v lekci.", language="cs-CZ")
                response.redirect(url_for('voice.questions', attempt_id=attempt_id, _external=True))
            else:
                response.hangup()
        
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Chyba při zpracování otázky uživatele: {str(e)}")
        response = VoiceResponse()
        response.say("Omlouváme se, došlo k chybě při zpracování vaší otázky.", language="cs-CZ")
        if attempt_id:
            response.redirect(url_for('voice.questions', attempt_id=attempt_id, _external=True))
        else:
            response.hangup()
        return Response(str(response), mimetype='text/xml')

@voice_bp.route("/follow_up", methods=["POST"])
def handle_follow_up():
    """Zpracuje následnou akci uživatele po odpovědi na otázku."""
    try:
        attempt_id = request.values.get('attempt_id')
        speech_result = request.values.get('SpeechResult', '').strip().lower()
        
        logger.info(f"Zpracovávám následnou akci: {speech_result}")
        
        response = VoiceResponse()
        
        if 'otázka' in speech_result or 'otázku' in speech_result:
            response.say("Jaká je vaše další otázka?", language="cs-CZ")
            
            gather = response.gather(
                input='speech',
                action=url_for('voice.handle_user_question', attempt_id=attempt_id, _external=True),
                speech_timeout=10,
                timeout=15,
                language='cs-CZ'
            )
            gather.say("Poslouchám...", language="cs-CZ")
            
        elif 'pokračovat' in speech_result or 'lekce' in speech_result:
            if attempt_id:
                response.say("Pokračujeme v lekci.", language="cs-CZ")
                response.redirect(url_for('voice.questions', attempt_id=attempt_id, _external=True))
            else:
                response.say("Děkuji za váš zájem. Na shledanou!", language="cs-CZ")
                response.hangup()
        else:
            # Nerozpoznaný vstup - nabídneme možnosti znovu
            response.say("Nerozuměl jsem. Řekněte 'otázka' pro další otázku nebo 'pokračovat' pro návrat k lekci.", language="cs-CZ")
            
            gather = response.gather(
                input='speech',
                action=url_for('voice.handle_follow_up', attempt_id=attempt_id, _external=True),
                speech_timeout=5,
                timeout=10,
                language='cs-CZ'
            )
            gather.say("Poslouchám...", language="cs-CZ")
            
            # Pokud stále není odpověď, pokračujeme v lekci
            if attempt_id:
                response.redirect(url_for('voice.questions', attempt_id=attempt_id, _external=True))
            else:
                response.hangup()
            
            return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Chyba při zpracování následné akce: {str(e)}")
        response = VoiceResponse()
        response.say("Omlouváme se, došlo k chybě.", language="cs-CZ")
        if attempt_id:
            response.redirect(url_for('voice.questions', attempt_id=attempt_id, _external=True))
        else:
            response.hangup()
        return Response(str(response), mimetype='text/xml')

@voice_bp.route("/openai-realtime", methods=["POST"])
def openai_realtime():
    """Endpoint pro OpenAI Realtime API s WebSocket připojením."""
    try:
        logger.info("=== ZAČÁTEK OPENAI REALTIME PŘIPOJENÍ ===")
        
        # Získání attempt_id z parametrů
        attempt_id = request.args.get('attempt_id')
        logger.info(f"Attempt ID: {attempt_id}")
        
        # Vytvoření TwiML odpovědi s Media Stream
        response = VoiceResponse()
        
        # Přidání uvítací zprávy
        response.say(
            "Připojuji vás k AI asistentovi. Prosím počkejte.",
            language="cs-CZ",
            voice="Google.cs-CZ-Standard-A"
        )
        
        # Vytvoření Media Stream pro WebSocket připojení
        connect = Connect()
        stream = Stream(
            url=f"wss://{request.host}/voice/media-stream?attempt_id={attempt_id}",
            track="both_tracks"  # Opraveno na správnou hodnotu
        )
        connect.append(stream)
        response.append(connect)
        
        logger.info("TwiML odpověď s Media Stream byla vytvořena")
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Chyba při vytváření OpenAI Realtime připojení: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        response = VoiceResponse()
        response.say(
            "Omlouváme se, došlo k chybě při připojování k AI asistentovi.",
            language="cs-CZ",
            voice="Google.cs-CZ-Standard-A"
        )
        response.hangup()
        return Response(str(response), mimetype='text/xml')

@voice_bp.route("/media-stream")
def media_stream():
    """Zpracuje WebSocket připojení pro Media Stream s OpenAI Realtime API."""
    try:
        logger.info("=== ZAČÁTEK MEDIA STREAM WEBSOCKET ===")
        
        # Získání attempt_id z parametrů
        attempt_id = request.args.get('attempt_id')
        logger.info(f"Media Stream Attempt ID: {attempt_id}")
        
        # Použití nového realtime service pro zpracování WebSocket připojení
        return handle_media_stream_websocket(request, attempt_id)
        
    except Exception as e:
        logger.error(f"Chyba při zpracování Media Stream: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return "Error", 500 