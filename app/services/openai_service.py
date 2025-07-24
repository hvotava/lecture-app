import os
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self):
        """Inicializuje OpenAI službu."""
        self.client = None
        self.enabled = False
        
        try:
            # Kontrola API klíče
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                logger.warning("OPENAI_API_KEY není nastaven - OpenAI služba bude vypnuta")
                return
            
            # Import OpenAI knihovny
            try:
                from openai import OpenAI
            except ImportError:
                logger.error("OpenAI knihovna není nainstalována")
                return
            
            # Inicializace klienta
            self.client = OpenAI(api_key=api_key)
            self.enabled = True
            logger.info("OpenAI služba byla úspěšně inicializována")
            
        except Exception as e:
            self.enabled = False
            logger.error(f"Chyba při inicializaci OpenAI služby: {str(e)}")
            # Neházeme výjimku, pouze logujeme chybu

    def generate_questions(self, text: str, language: str = "cs") -> List[Dict[str, Any]]:
        """Vygeneruje testovací otázky z textu."""
        if not self.enabled or not self.client:
            logger.warning("OpenAI služba není povolena - generování otázek nebude provedeno")
            return []
            
        try:
            logger.info(f"Generuji otázky pro text délky {len(text)} v jazyce {language}")
            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"Jsi učitel {language} jazyka. Vytvoř 3 testovací otázky z následujícího textu. Otázky by měly být v jazyce {language} a měly by testovat porozumění textu. Odpověď vrať ve formátu JSON pole objektů s klíči 'question' a 'answer'."
                    },
                    {
                        "role": "user",
                        "content": text
                    }
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            # Zpracování odpovědi
            content = response.choices[0].message.content
            logger.info(f"Obdržena odpověď od OpenAI: {content}")
            
            import json
            questions = json.loads(content)
            logger.info(f"Vygenerováno {len(questions)} otázek")
            return questions
            
        except Exception as e:
            logger.error(f"Chyba při generování otázek: {str(e)}")
            logger.error(f"Text pro generování: {text[:100]}...")
            return []
    
    def score_answer(
        self,
        question: str,
        correct_answer: str,
        user_answer: str
    ) -> Tuple[int, List[str]]:
        """
        Vyhodnotí odpověď uživatele pomocí GPT-4.
        
        Returns:
            Tuple[int, List[str]]: (skóre 0-100, seznam chybných témat)
        """
        if not self.enabled or not self.client:
            logger.warning("OpenAI služba není povolena - hodnocení odpovědi nebude provedeno")
            return 0, []
            
        try:
            logger.info(f"Hodnotím odpověď na otázku: {question[:50]}...")
            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Vyhodnoť odpověď na otázku z hlediska správnosti a úplnosti. Vrať JSON ve formátu {\"score\": 0-100, \"wrong_topics\": [\"téma1\", \"téma2\"]}"
                    },
                    {
                        "role": "user",
                        "content": f"Otázka: {question}\nSprávná odpověď: {correct_answer}\nOdpověď uživatele: {user_answer}"
                    }
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            # Zpracování odpovědi
            content = response.choices[0].message.content
            logger.info(f"Obdržena odpověď od OpenAI: {content}")
            
            import json
            result = json.loads(content)
            logger.info(f"Skóre: {result['score']}, Chybná témata: {result['wrong_topics']}")
            return result["score"], result["wrong_topics"]
            
        except Exception as e:
            logger.error(f"Chyba při hodnocení odpovědi: {str(e)}")
            return 0, []

    def generate_voice_questions(self, lesson_script: str, language: str = "cs", num_questions: int = 3) -> List[Dict[str, Any]]:
        """Vygeneruje otázky specificky pro hlasové lekce."""
        if not self.enabled or not self.client:
            logger.warning("OpenAI služba není povolena - generování hlasových otázek nebude provedeno")
            return []
            
        try:
            logger.info(f"Generuji {num_questions} hlasových otázek pro lekci v jazyce {language}")
            
            system_prompt = f"""Jsi zkušený učitel {language} jazyka. Vytvoř {num_questions} otázky pro hlasovou lekci.
            
Otázky by měly:
- Být jednoduché a srozumitelné pro hlasové rozhraní
- Testovat porozumění obsahu lekce
- Mít jasné a stručné správné odpovědi
- Být vhodné pro ústní odpověď (ne příliš složité)

Vrať odpověď ve formátu JSON pole objektů s klíči:
- "question": text otázky
- "correct_answer": správná odpověď
- "topic": hlavní téma otázky
- "difficulty": obtížnost (1-5)"""

            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Obsah lekce:\n{lesson_script}"}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            content = response.choices[0].message.content
            logger.info(f"Obdržena odpověď od OpenAI pro hlasové otázky")
            
            import json
            questions = json.loads(content)
            logger.info(f"Vygenerováno {len(questions)} hlasových otázek")
            return questions
            
        except Exception as e:
            logger.error(f"Chyba při generování hlasových otázek: {str(e)}")
            return []

    def speech_to_text(self, audio_data: bytes, language: str = "cs") -> str:
        """
        Převádí audio data na text pomocí OpenAI Whisper API.
        
        Args:
            audio_data: Raw audio data (např. WAV, MP3)
            language: Jazyk audia (např. "cs", "en")
            
        Returns:
            Přepsaný text nebo prázdný string při chybě
        """
        if not self.enabled or not self.client:
            logger.warning("OpenAI služba není povolena - speech-to-text nebude proveden")
            return ""
            
        try:
            logger.info(f"Převádím audio na text (jazyk: {language})")
            
            # Whisper API očekává audio soubor nebo base64 data
            # Pro Twilio Media Streams je audio v base64 formátu
            import base64
            
            # Pokud jsou data v base64, dekódujeme je
            if isinstance(audio_data, str):
                try:
                    audio_data = base64.b64decode(audio_data)
                except:
                    pass
            
            # Vytvoříme dočasný soubor pro audio data
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Volání Whisper API
                with open(temp_file_path, "rb") as audio_file:
                    response = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=language,
                        response_format="text"
                    )
                
                text = response.strip()
                logger.info(f"Přepsaný text: {text}")
                return text
                
            finally:
                # Smazání dočasného souboru
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"Chyba při převodu audia na text: {str(e)}")
            return ""
    
    def generate_questions_from_lesson(self, lesson_script: str, language: str = "cs", num_questions: int = 5) -> List[Dict[str, Any]]:
        """
        Vygeneruje otázky z obsahu lekce pomocí GPT-4.
        
        Args:
            lesson_script: Obsah lekce
            language: Jazyk otázek
            num_questions: Počet otázek k vygenerování
            
        Returns:
            Seznam otázek s odpověďmi
        """
        if not self.enabled or not self.client:
            logger.warning("OpenAI služba není povolena - generování otázek nebude provedeno")
            return []
            
        try:
            logger.info(f"Generuji {num_questions} otázek z lekce v jazyce {language}")
            
            system_prompt = f"""Jsi zkušený učitel {language} jazyka. Vytvoř {num_questions} testovacích otázek z následujícího obsahu lekce.

Otázky by měly:
- Testovat porozumění klíčových konceptů z lekce
- Být jasné a srozumitelné
- Mít jednoznačné správné odpovědi
- Pokrývat různé části obsahu lekce
- Být vhodné pro ústní odpověď (ne příliš složité)

Vrať odpověď ve formátu JSON pole objektů s klíči:
- "question": text otázky
- "correct_answer": správná odpověď
- "topic": hlavní téma otázky
- "difficulty": obtížnost (1-5, kde 1=snadná, 5=obtížná)"""

            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Obsah lekce:\n{lesson_script}"}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            logger.info(f"Obdržena odpověď od OpenAI pro generování otázek")
            
            import json
            questions = json.loads(content)
            logger.info(f"Vygenerováno {len(questions)} otázek")
            return questions
            
        except Exception as e:
            logger.error(f"Chyba při generování otázek z lekce: {str(e)}")
            return []
    
    def evaluate_voice_answer(self, question: str, correct_answer: str, user_answer: str, language: str = "cs") -> Dict[str, Any]:
        """
        Vyhodnotí hlasovou odpověď uživatele pomocí GPT-4.
        
        Returns:
            Dict obsahující: score, feedback, is_correct, suggestions
        """
        if not self.enabled or not self.client:
            logger.warning("OpenAI služba není povolena - hodnocení odpovědi nebude provedeno")
            return {
                "score": 0,
                "feedback": "Hodnocení není k dispozici",
                "is_correct": False,
                "suggestions": []
            }
            
        try:
            logger.info(f"Hodnotím hlasovou odpověď v jazyce {language}")
            
            system_prompt = f"""Jsi zkušený učitel {language} jazyka. Vyhodnoť odpověď studenta na otázku.

Zohledni:
- Správnost obsahu odpovědi
- Úplnost odpovědi
- Možné nepřesnosti při rozpoznávání řeči
- Buď povzbuzující a konstruktivní

Vrať JSON ve formátu:
{{
    "score": 0-100,
    "feedback": "stručná zpětná vazba v {language}",
    "is_correct": true/false,
    "suggestions": ["tip1", "tip2"]
}}"""

            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"""
Otázka: {question}
Správná odpověď: {correct_answer}
Odpověď studenta: {user_answer}

Vyhodnoť tuto odpověď."""}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            content = response.choices[0].message.content
            logger.info(f"Obdržena odpověď od OpenAI pro hodnocení")
            
            import json
            result = json.loads(content)
            logger.info(f"Hodnocení odpovědi: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Chyba při hodnocení odpovědi: {str(e)}")
            return {
                "score": 0,
                "feedback": "Hodnocení se nezdařilo",
                "is_correct": False,
                "suggestions": []
            }

    def answer_user_question(
        self,
        user_question: str,
        current_lesson: Optional[Dict[str, Any]] = None,
        other_lessons: Optional[List[Dict[str, Any]]] = None,
        language: str = "cs"
    ) -> Dict[str, Any]:
        """
        Odpovídá na otázku uživatele v kontextu lekce.
        
        Returns:
            Dict obsahující: answer, related_topics, follow_up_questions
        """
        if not self.enabled or not self.client:
            logger.warning("OpenAI služba není povolena - odpovídání na otázky nebude provedeno")
            return {
                "answer": "Omlouváme se, služba pro odpovídání na otázky není momentálně k dispozici.",
                "related_topics": [],
                "follow_up_questions": []
            }
            
        try:
            logger.info(f"Odpovídám na otázku uživatele v jazyce {language}")
            
            # Sestavení kontextu
            context = ""
            if current_lesson:
                context += f"Aktuální lekce: {current_lesson.get('title', '')}\n"
                context += f"Obsah: {current_lesson.get('script', '')}\n\n"
            
            if other_lessons:
                context += "Další dostupné lekce:\n"
                for lesson in other_lessons[:3]:  # Omezíme na 3 lekce
                    context += f"- {lesson.get('title', '')}: {lesson.get('script', '')[:100]}...\n"
            
            system_prompt = f"""Jsi AI asistent pro výuku {language} jazyka. Odpovídej na otázky studentů jasně a srozumitelně v jazyce {language}.

Pokud se otázka týká aktuální lekce, zaměř se na ni. Pokud ne, můžeš využít informace z dalších lekcí.

Vrať odpověď ve formátu JSON:
{{
    "answer": "odpověď na otázku",
    "related_topics": ["téma1", "téma2"], // související témata
    "follow_up_questions": ["otázka1", "otázka2"] // navazující otázky
}}"""

            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"""
Kontext:
{context}

Otázka studenta: {user_question}

Odpověz na tuto otázku."""}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content
            logger.info(f"Obdržena odpověď od OpenAI na otázku uživatele")
            
            import json
            result = json.loads(content)
            logger.info(f"Odpověď na otázku uživatele: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Chyba při odpovídání na otázku uživatele: {str(e)}")
            return {
                "answer": "Omlouváme se, došlo k chybě při zpracování vaší otázky.",
                "related_topics": [],
                "follow_up_questions": []
            }

# Globální instance služby
openai_service = OpenAIService() 