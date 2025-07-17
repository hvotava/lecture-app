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

logger = logging.getLogger(__name__)

# Nastavení podrobnějšího logování
logging.basicConfig(level=logging.DEBUG)
logger.setLevel(logging.DEBUG)

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
            logger.info("Kontroluji Twilio přihlašovací údaje:")
            
            # OpenAI služba se inicializuje lazy
            self._openai_service = None
            
            # Načtení proměnných z .env souboru
            env_path = os.path.join('/home/synqflows', 'lecture', '.env')
            logger.info(f"Hledám .env soubor na cestě: {env_path}")
            
            if os.path.exists(env_path):
                logger.info("Našel jsem .env soubor, načítám proměnné")
                load_dotenv(env_path, override=True)
                
                # Kontrola obsahu .env souboru (bez citlivých údajů)
                try:
                    with open(env_path, 'r') as f:
                        env_content = f.read()
                        logger.info("Obsah .env souboru (bez citlivých údajů):")
                        for line in env_content.splitlines():
                            if line.strip() and not line.startswith('#'):
                                key = line.split('=')[0].strip()
                                logger.info(f"Nalezena proměnná: {key}")
                except Exception as e:
                    logger.error(f"Chyba při čtení .env souboru: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
            else:
                logger.error(f".env soubor nebyl nalezen na cestě: {env_path}")
            
            # Kontrola načtených proměnných
            self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
            self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
            self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")
            
            logger.info("Kontrola načtených Twilio proměnných:")
            logger.info(f"TWILIO_ACCOUNT_SID je nastaven: {'Ano' if self.account_sid else 'Ne'}")
            if self.account_sid:
                logger.info(f"TWILIO_ACCOUNT_SID začíná na: {self.account_sid[:2]}...")
                logger.info(f"TWILIO_ACCOUNT_SID délka: {len(self.account_sid)} znaků")
            logger.info(f"TWILIO_AUTH_TOKEN je nastaven: {'Ano' if self.auth_token else 'Ne'}")
            if self.auth_token:
                logger.info(f"TWILIO_AUTH_TOKEN začíná na: {self.auth_token[:2]}...")
                logger.info(f"TWILIO_AUTH_TOKEN délka: {len(self.auth_token)} znaků")
            logger.info(f"TWILIO_PHONE_NUMBER je nastaven: {'Ano' if self.phone_number else 'Ne'}")
            if self.phone_number:
                logger.info(f"TWILIO_PHONE_NUMBER začíná na: {self.phone_number[:4]}...")
                logger.info(f"TWILIO_PHONE_NUMBER délka: {len(self.phone_number)} znaků")
            
            if not all([self.account_sid, self.auth_token, self.phone_number]):
                logger.error("Chybí některé Twilio proměnné v .env souboru!")
                raise ValueError("Chybí některé Twilio proměnné v .env souboru!")
            
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
            
            logger.info("Všechny Twilio přihlašovací údaje jsou nastaveny, inicializuji klienta")
            self.client = Client(self.account_sid, self.auth_token)
            self.enabled = True
            logger.info("Twilio služba byla úspěšně inicializována")
        except Exception as e:
            self.enabled = False
            logger.error(f"Chyba při inicializaci Twilio služby: {str(e)}")
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
                model="gpt-3.5-turbo",
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