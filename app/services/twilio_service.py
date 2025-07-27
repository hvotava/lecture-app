from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
import os
from typing import Optional, List, Tuple
from twilio.base.exceptions import TwilioRestException
import logging
import traceback
from dotenv import load_dotenv
import re
import html
import xml.etree.ElementTree as ET
import sys
from twilio.twiml.voice_response import Connect, Stream

logger = logging.getLogger(__name__)

# Nastavení logování - potlačíme verbose výstup z python_multipart
logging.basicConfig(level=logging.INFO)
logger.setLevel(logging.DEBUG)  # Zachováme DEBUG pro vlastní kód
logging.getLogger('python_multipart.multipart').setLevel(logging.WARNING)  # Potlačíme verbose multipart debug

# Slovník předvoleb a odpovídajících jazyků
COUNTRY_CODES = {
    '420': ('cs-CZ', 'Google.cs-CZ-Standard-A'),  # Česká republika
    '421': ('sk-SK', 'Google.sk-SK-Standard-A'),  # Slovensko
    '48': ('pl-PL', 'Google.pl-PL-Standard-A'),   # Polsko
    '43': ('de-AT', 'Google.de-AT-Standard-A'),   # Rakousko
    '49': ('de-DE', 'Google.de-DE-Standard-A'),   # Německo
    '36': ('hu-HU', 'Google.hu-HU-Standard-A'),   # Maďarsko
    '1': ('en-US', 'Google.en-US-Standard-A'),    # USA/Kanada
    '44': ('en-GB', 'Google.en-GB-Standard-A'),   # Velká Británie
}

def detect_language_from_number(phone_number: str) -> Tuple[str, str]:
    """
    Detekuje jazyk a hlas podle telefonní předvolby.
    Vrací tuple (language_code, voice_code)
    """
    try:
        # Odstranění mezer a speciálních znaků
        clean_number = re.sub(r'[^0-9+]', '', phone_number)
        
        # Pokud číslo začíná na +, odstraníme ho
        if clean_number.startswith('+'):
            clean_number = clean_number[1:]
        
        # Hledání předvolby
        for code, (lang, voice) in COUNTRY_CODES.items():
            if clean_number.startswith(code):
                logger.info(f"Detekován jazyk {lang} pro předvolbu {code}")
                return lang, voice
        
        # Výchozí hodnota pro neznámou předvolbu
        logger.warning(f"Neznámá předvolba pro číslo {phone_number}, používám výchozí češtinu")
        return 'cs-CZ', 'Google.cs-CZ-Standard-A'
        
    except Exception as e:
        logger.error(f"Chyba při detekci jazyka: {str(e)}")
        return 'cs-CZ', 'Google.cs-CZ-Standard-A'

class TwilioService:
    def __init__(self):
        try:
            logger.info("Inicializuji TwilioService...")
            
            # Standardní a flexibilní načtení .env
            # python-dotenv automaticky hledá .env v aktuálním a nadřazených adresářích
            if load_dotenv():
                logger.info("✅ .env soubor nalezen a načten (standardní metoda).")
            else:
                logger.warning("⚠️ Standardní .env soubor nenalezen, zkouším alternativní cesty...")
                # Zde může být záložní logika pro specifické produkční prostředí
                env_path_prod = os.path.join('/home/synqflows', 'lecture', '.env')
                if os.path.exists(env_path_prod) and load_dotenv(env_path_prod):
                     logger.info(f"✅ .env soubor načten z produkční cesty: {env_path_prod}")
                else:
                     logger.error("❌ Nepodařilo se najít .env soubor ani na jedné ze známých cest.")

            self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
            self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
            self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")
            
            if not all([self.account_sid, self.auth_token, self.phone_number]):
                logger.error("❌ CHYBA: Některé klíčové proměnné pro Twilio (ACCOUNT_SID, AUTH_TOKEN, PHONE_NUMBER) nebyly nalezeny v prostředí!")
                raise ValueError("Chybí povinné Twilio proměnné.")
            
            # Kontrola formátu hodnot
            if not self.account_sid.startswith("AC"):
                logger.error("TWILIO_ACCOUNT_SID musí začínat na 'AC'")
                raise ValueError("Neplatný formát TWILIO_ACCOUNT_SID")
            
            if len(self.account_sid) != 34:
                logger.error(f"TWILIO_ACCOUNT_SID musí mít 34 znaků, má {len(self.account_sid)}")
                raise ValueError("Neplatná délka TWILIO_ACCOUNT_SID")
            
            if len(self.auth_token) != 32:
                logger.error(f"TWILIO_AUTH_TOKEN musí mít 32 znaků, má {len(self.auth_token)}")
                raise ValueError("Neplatná délka TWILIO_AUTH_TOKEN")
            
            if not self.phone_number.startswith("+"):
                logger.error("TWILIO_PHONE_NUMBER musí začínat na '+'")
                raise ValueError("Neplatný formát TWILIO_PHONE_NUMBER")
            
            logger.info("✅ Všechny Twilio přihlašovací údaje jsou nastaveny, inicializuji klienta.")
            self.client = Client(self.account_sid, self.auth_token)
            self.enabled = True
            logger.info("✅ Twilio služba byla úspěšně inicializována.")
        except Exception as e:
            self.enabled = False
            logger.error(f"❌ Kritická chyba při inicializaci Twilio služby: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            logger.error(f"Python verze: {sys.version}")
            logger.error(f"Python cesta: {sys.path}")

    @property
    def openai_service(self):
        """Lazy inicializace OpenAI služby."""
        if self._openai_service is None:
            try:
                from app.services.openai_service import OpenAIService
                self._openai_service = OpenAIService()
                logger.info("OpenAI služba byla úspěšně inicializována")
            except Exception as e:
                logger.error(f"Chyba při inicializaci OpenAI služby: {str(e)}")
                self._openai_service = None
        return self._openai_service

    def call(self, to_number: str, webhook_url: str) -> None:
        """Zavolá na zadané číslo a přehraje TwiML z webhooku."""
        if not self.enabled:
            logger.warning("Twilio služba není povolena - volání nebude provedeno")
            return
            
        try:
            logger.info(f"Pokus o volání na číslo {to_number} s webhook URL {webhook_url}")
            logger.info(f"Používám Twilio číslo: {self.phone_number}")
            
            # Validace telefonního čísla
            if not to_number.startswith('+'):
                raise ValueError("Telefonní číslo musí začínat na '+'")
            
            # Validace webhook URL
            if not webhook_url.startswith('http'):
                raise ValueError("Webhook URL musí začínat na 'http'")
            
            call = self.client.calls.create(
                to=to_number,
                from_=self.phone_number,
                url=webhook_url
            )
            logger.info(f"Volání bylo úspěšně zahájeno: {call.sid}")
            return call.sid
        except TwilioRestException as e:
            logger.error(f"Twilio chyba při volání: {str(e)}")
            logger.error(f"Twilio Account SID: {self.account_sid[:6]}...")
            logger.error(f"Twilio Auth Token: {self.auth_token[:6]}...")
            logger.error(f"Twilio Phone Number: {self.phone_number}")
            raise
        except Exception as e:
            logger.error(f"Neočekávaná chyba při volání: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
    
    def create_chat_response(self, user_input: str, language: str = "cs-CZ", phone_number: str = None) -> str:
        """Vytvoří TwiML odpověď s ChatGPT odpovědí."""
        try:
            logger.info(f"Vytvářím chat odpověď pro vstup: {user_input}")
            
            # Kontrola dostupnosti OpenAI služby
            openai_svc = self.openai_service
            if not openai_svc or not openai_svc.enabled or not openai_svc.client:
                logger.warning("OpenAI služba není dostupná - používám výchozí odpověď")
                chat_response = "Omlouvám se, služba pro generování odpovědí není momentálně dostupná. Zkuste to prosím později."
            else:
            # Získání odpovědi od ChatGPT
                response = openai_svc.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Jsi užitečný asistent, který mluví česky. Odpovídej stručně a jasně. Používej přirozený konverzační styl."
                    },
                    {
                        "role": "user",
                        "content": user_input
                    }
                ]
            )
            
            chat_response = response.choices[0].message.content
            logger.info(f"ChatGPT odpověď: {chat_response}")
            
            # Vytvoření TwiML odpovědi
            response = VoiceResponse()
            
            # Nastavení hlasu a jazyka
            voice = "Google.cs-CZ-Standard-A"
            
            # Přidání odpovědi s pomalejší dikcí a přirozenější intonací
            response.say(
                chat_response,
                voice=voice,
                language=language,
                rate="0.9",  # Pomalejší dikce
                pitch="+0.1"  # Přirozenější tón
            )
            
            # Přidání gather elementu pro další vstup s podporou hlasového vstupu
            gather = response.gather(
                input='speech',  # Pouze hlasový vstup
                timeout=5,  # Kratší timeout pro rychlejší reakci
                speech_timeout='auto',
                action=None, # url_for('voice.chat', _external=True), # SMAZAT
                method='POST',
                speech_model='phone_call',  # Optimalizováno pro telefonní hovory
                enhanced='true',  # Vylepšené rozpoznávání řeči
                language=language
            )
            
            # Přidání instrukce pro uživatele
            gather.say(
                "Můžete mluvit nebo stisknout hvězdičku pro ukončení.",
                voice=voice,
                language=language,
                rate="0.9",
                pitch="+0.1"
            )
            
            return str(response)
            
        except Exception as e:
            logger.error(f"Chyba při vytváření chat odpovědi: {str(e)}")
            logger.error(traceback.format_exc())
            response = VoiceResponse()
            response.say(
                "Omlouvám se, došlo k chybě. Zkuste to prosím znovu.",
                voice="Google.cs-CZ-Standard-A",
                language="cs-CZ",
                rate="0.9",
                pitch="+0.1"
            )
            response.hangup()
            return str(response)

    def create_voice_response(self, text: str, language: str = "cs-CZ", hints: List[str] = None, phone_number: str = None, attempt_id: str = None) -> str:
        """Vytvoří TwiML odpověď s textem a možností odpovědi."""
        try:
            logger.info(f"Vytvářím TwiML odpověď pro text délky {len(text)}")
            logger.info(f"Jazyk: {language}, Telefonní číslo: {phone_number}")
            
            response = VoiceResponse()
            
            # Nastavení hlasu a jazyka
            voice = "Google.cs-CZ-Standard-A"
            if language == "en":
                voice = "Google.en-US-Standard-A"
            
            # Přidání textu s pomalejší dikcí a přirozenější intonací
            response.say(
                text,
                voice=voice,
                language=language,
                rate="0.9",  # Pomalejší dikce (0.8-1.0)
                pitch="+0.1"  # Mírně vyšší tón pro přirozenější zvuk
            )
            
            # Přidání gather elementu pro odpověď
            gather = response.gather(
                input='speech',  # Pouze hlasový vstup
                timeout=5,  # Kratší timeout pro rychlejší reakci
                speech_timeout='auto',
                action=None, # url_for('voice.voice', _external=True, attempt_id=attempt_id) if attempt_id else None, # SMAZAT
                method='POST',
                speech_model='phone_call',  # Optimalizováno pro telefonní hovory
                enhanced='true',  # Vylepšené rozpoznávání řeči
                language=language
            )
            
            # Přidání nápovědy pro odpověď
            if hints:
                gather.say(
                    "Můžete mluvit nebo stisknout hvězdičku pro ukončení.",
                    voice=voice,
                    language=language,
                    rate="0.9",
                    pitch="+0.1"
                )
            
            return str(response)
        except Exception as e:
            logger.error(f"Neočekávaná chyba při vytváření TwiML: {str(e)}")
            logger.error(traceback.format_exc())
            response = VoiceResponse()
            response.say("Došlo k neočekávané chybě. Zkuste to prosím později.", language=language, voice=voice)
            response.hangup()
            return str(response)
    
    def create_stop_response(self, language: str = "cs-CZ", phone_number: str = None) -> str:
        """Vytvoří TwiML odpověď pro ukončení hovoru."""
        logger.info(f"Vytvářím stop odpověď v jazyce {language}")
        
        # Detekce jazyka podle telefonního čísla
        if phone_number:
            language, voice = detect_language_from_number(phone_number)
            logger.info(f"Detekovaný jazyk: {language}, hlas: {voice}")
        else:
            language, voice = 'cs-CZ', 'Google.cs-CZ-Standard-A'
            logger.info(f"Používám výchozí jazyk: {language}, hlas: {voice}")
            
        response = VoiceResponse()
        response.say(
            "Děkujeme za volání. Hovor byl ukončen.",
            language=language,
            voice=voice
        )
        response.hangup()
        twiml = str(response)
        logger.info(f"Vygenerovaný TwiML pro stop: {twiml}")
        return twiml 

    def create_introduction_response(self, lesson=None) -> str:
        """Vytvoří úvodní TwiML odpověď."""
        response = VoiceResponse()
        
        # Přivítání
        response.say(
            "Vítejte u AI asistenta pro výuku jazyků!",
            language="cs-CZ",
            voice="Google.cs-CZ-Standard-A",
            rate="0.9"
        )
        
        if lesson:
            response.say(
                f"Dnes se budeme učit o tématu: {lesson.title}",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A",
                rate="0.9"
            )
            response.pause(length=1)
            response.say(
                "Můžete se mě ptát na cokoliv ohledně tohoto tématu. Až budete připraveni na zkoušení, řekněte 'otázky' nebo 'zkoušení'.",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A",
                rate="0.9"
            )
        else:
            response.say(
                "Můžeme si povídat o různých tématech. Řekněte mi, co vás zajímá!",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A",
                rate="0.9"
            )
        
        # Připojení na Media Stream
        connect = Connect()
        stream = Stream(
            url="wss://lecture-app-production.up.railway.app/audio",
            track="both"
        )
        connect.append(stream)
        response.append(connect)
        
        return str(response)
    
    def create_teaching_response(self, lesson) -> str:
        """Vytvoří TwiML odpověď pro fázi výuky."""
        response = VoiceResponse()
        
        if lesson:
            # Přečtení části skriptu lekce
            script_preview = lesson.script[:300] + "..." if len(lesson.script) > 300 else lesson.script
            response.say(
                f"Téma lekce: {script_preview}",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A",
                rate="0.8"
            )
            response.pause(length=1)
            response.say(
                "Můžete se mě ptát na cokoliv ohledně tohoto tématu. Až budete připraveni na zkoušení, řekněte 'otázky' nebo 'zkoušení'.",
                language="cs-CZ",
                voice="Google.cs-CZ-Standard-A",
                rate="0.9"
            )
        
        # Připojení na Media Stream
        connect = Connect()
        stream = Stream(
            url="wss://lecture-app-production.up.railway.app/audio",
            track="both"
        )
        connect.append(stream)
        response.append(connect)
        
        return str(response)
    
    def create_questioning_start_response(self) -> str:
        """Vytvoří TwiML odpověď pro začátek zkoušení."""
        response = VoiceResponse()
        
        response.say(
            "Výborně! Nyní začneme se zkoušením. Budu vám klást otázky a vy mi odpovíte. Řekněte mi, když jste připraveni.",
            language="cs-CZ",
            voice="Google.cs-CZ-Standard-A",
            rate="0.9"
        )
        
        # Připojení na Media Stream
        connect = Connect()
        stream = Stream(
            url="wss://lecture-app-production.up.railway.app/audio",
            track="both"
        )
        connect.append(stream)
        response.append(connect)
        
        return str(response)
    
    def create_question_response(self, question: str, language: str = "cs-CZ", include_beep: bool = True) -> str:
        """Vytvoří TwiML odpověď s otázkou."""
        response = VoiceResponse()
        
        response.say(
            f"Otázka: {question}",
            language=language,
            voice="Google.cs-CZ-Standard-A",
            rate="0.8"  # Pomalejší pro lepší srozumitelnost
        )
        response.pause(length=1)
        
        if include_beep:
            response.say(
                "Píp.",
                language=language,
                voice="Google.cs-CZ-Standard-A",
                rate="0.8"
            )
        
        # Připojení na Media Stream
        connect = Connect()
        stream = Stream(
            url="wss://lecture-app-production.up.railway.app/audio",
            track="both"
        )
        connect.append(stream)
        response.append(connect)
        
        return str(response)
    
    def create_feedback_response(self, feedback: str, language: str = "cs-CZ") -> str:
        """Vytvoří TwiML odpověď s feedbackem."""
        response = VoiceResponse()
        
        response.say(
            feedback,
            language=language,
            voice="Google.cs-CZ-Standard-A",
            rate="0.9"
        )
        response.pause(length=1)
        
        # Připojení na Media Stream
        connect = Connect()
        stream = Stream(
            url="wss://lecture-app-production.up.railway.app/audio",
            track="both"
        )
        connect.append(stream)
        response.append(connect)
        
        return str(response)
    
    def create_evaluation_response(self, user_answers: list, language: str = "cs-CZ") -> str:
        """Vytvoří TwiML odpověď s celkovým vyhodnocením."""
        response = VoiceResponse()
        
        if user_answers:
            total_score = sum(answer["score"] for answer in user_answers)
            average_score = total_score / len(user_answers)
            
            response.say(
                f"Zkoušení je ukončeno! Vaše celkové skóre je {average_score:.1f} procent.",
                language=language,
                voice="Google.cs-CZ-Standard-A",
                rate="0.9"
            )
            response.pause(length=1)
            
            if average_score >= 80:
                response.say(
                    "Výborně! Máte velmi dobré znalosti tohoto tématu.",
                    language=language,
                    voice="Google.cs-CZ-Standard-A",
                    rate="0.9"
                )
            elif average_score >= 60:
                response.say(
                    "Dobře! Máte solidní znalosti, ale je prostor pro zlepšení.",
                    language=language,
                    voice="Google.cs-CZ-Standard-A",
                    rate="0.9"
                )
            else:
                response.say(
                    "Doporučuji si téma zopakovat. Můžete mi znovu zavolat pro další pokus.",
                    language=language,
                    voice="Google.cs-CZ-Standard-A",
                    rate="0.9"
                )
        else:
            response.say(
                "Zkoušení bylo ukončeno bez odpovědí.",
                language=language,
                voice="Google.cs-CZ-Standard-A",
                rate="0.9"
            )
        
        response.pause(length=1)
        response.say(
            "Děkujeme za volání! Na shledanou.",
            language=language,
            voice="Google.cs-CZ-Standard-A",
            rate="0.9"
        )
        response.hangup()
        
        return str(response) 