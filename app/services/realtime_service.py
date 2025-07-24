import os
import json
import base64
import asyncio
import websockets
import logging
from typing import Dict, Any, Optional, Callable
import threading
from queue import Queue
import time
import traceback
from flask import current_app
from flask_socketio import emit
from app.models import Attempt

logger = logging.getLogger(__name__)

class OpenAIRealtimeService:
    """Služba pro OpenAI Realtime API s WebSocket podporou."""
    
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.ws_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"  # Správná URL pro OpenAI Realtime API
        self.openai_ws = None
        self.twilio_ws = None
        self.audio_queue = Queue()
        self.is_connected = False
        self.session_id = None
        
    async def connect_to_openai(self, lesson_context: str = ""):
        """Připojí se k OpenAI Realtime API."""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            logger.info("Připojuji se k OpenAI Realtime API...")
            self.openai_ws = await websockets.connect(
                self.ws_url,
                extra_headers=headers
            )
            
            # Konfigurace session
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": f"""Jsi užitečný AI asistent pro výuku jazyků. Komunikuješ v češtině.

{lesson_context}

Tvoje úkoly:
- Odpovídej na otázky studentů o lekci
- Pomáhej s vysvětlením obtížných částí
- Buď trpělivý a povzbuzující
- Mluv přirozeně a srozumitelně
- Pokud student odpoví na otázku, vyhodnoť ji a poskytni zpětnou vazbu
- Můžeš klást otázky k lekci pro ověření porozumění

Vždy zůstávaj v kontextu výuky a buď konstruktivní.""",
                    "voice": "alloy",
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 800
                    },
                    "tools": [],
                    "tool_choice": "auto",
                    "temperature": 0.8,
                    "max_response_output_tokens": 4096
                }
            }
            
            await self.openai_ws.send(json.dumps(session_config))
            self.is_connected = True
            logger.info("Úspěšně připojeno k OpenAI Realtime API")
            
        except Exception as e:
            logger.error(f"Chyba při připojování k OpenAI: {str(e)}")
            self.is_connected = False
            raise
    
    async def handle_openai_messages(self, audio_callback: Callable[[bytes], None]):
        """Zpracovává zprávy z OpenAI Realtime API."""
        try:
            async for message in self.openai_ws:
                data = json.loads(message)
                message_type = data.get('type', 'unknown')
                
                logger.debug(f"Zpráva z OpenAI: {message_type}")
                
                if message_type == 'speech.chunk':
                    # Audio data z OpenAI
                    audio_data = data.get('chunk', '')
                    if audio_data:
                        # Dekódování base64 audio dat
                        audio_bytes = base64.b64decode(audio_data)
                        # Odeslání audio dat zpět do Twilio ve správném formátu
                        if audio_callback:
                            # Twilio očekává event: "media" s media.payload
                            twilio_message = {
                                "event": "media",
                                "media": {
                                    "payload": audio_data  # Použijeme původní base64 data
                                }
                            }
                            audio_callback(json.dumps(twilio_message).encode())
                            logger.info("Audio chunk odeslán do Twilio")
                            
                elif message_type == 'speech.done':
                    logger.info("OpenAI dokončilo generování řeči")
                    
                elif message_type == 'transcription.chunk':
                    text = data.get('text', '')
                    if text:
                        logger.info(f"Transkripce: {text}")
                        
                elif message_type == 'transcription.done':
                    text = data.get('text', '')
                    logger.info(f"Kompletní transkripce: {text}")
                    
                    # Generování odpovědi
                    try:
                        response_message = {
                            "type": "speech.create",
                            "model": "tts-1",
                            "voice": "alloy",
                            "input": {
                                "text": f"Rozumím, že říkáte: {text}. Moment prosím, zpracovávám odpověď.",
                                "format": "g711_ulaw",
                                "sample_rate": 8000,
                                "channels": 1
                            }
                        }
                        await self.openai_ws.send(json.dumps(response_message))
                        logger.info("Odpověď odeslána k syntéze")
                    except Exception as e:
                        logger.error(f"Chyba při generování odpovědi: {e}")
                    
                elif message_type == 'error':
                    error_info = data.get('error', {})
                    logger.error(f"Chyba z OpenAI: {error_info}")
                    
        except Exception as e:
            logger.error(f"Chyba při zpracování zpráv z OpenAI: {str(e)}")
    
    async def send_audio_to_openai(self, audio_data: bytes):
        """Odešle audio data do OpenAI."""
        try:
            if not self.is_connected or not self.openai_ws:
                logger.warning("Není připojeno k OpenAI - audio data nebudou odeslána")
                return
                
            # Kódování audio dat do base64
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Vytvoření zprávy pro OpenAI ve správném formátu
            audio_message = {
                "type": "speech.create",
                "model": "tts-1",
                "voice": "alloy",
                "input": {
                    "audio": audio_base64,
                    "format": "g711_ulaw",
                    "sample_rate": 8000,
                    "channels": 1
                }
            }
            
            await self.openai_ws.send(json.dumps(audio_message))
            logger.debug("Audio data odeslána do OpenAI")
            
        except Exception as e:
            logger.error(f"Chyba při odesílání audio dat do OpenAI: {str(e)}")
    
    async def commit_audio_buffer(self):
        """Potvrdí audio buffer v OpenAI (ukončí vstup uživatele)."""
        try:
            if not self.is_connected or not self.openai_ws:
                return
                
            commit_message = {
                "type": "speech.done"
            }
            
            await self.openai_ws.send(json.dumps(commit_message))
            logger.debug("Audio buffer potvrzen v OpenAI")
            
        except Exception as e:
            logger.error(f"Chyba při potvrzování audio bufferu: {str(e)}")
    
    async def create_response(self):
        """Požádá OpenAI o vytvoření odpovědi."""
        try:
            if not self.is_connected or not self.openai_ws:
                return
                
            response_message = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Odpověz na to, co uživatel řekl. Buď užitečný a přátelský."
                }
            }
            
            await self.openai_ws.send(json.dumps(response_message))
            logger.debug("Požádáno o vytvoření odpovědi z OpenAI")
            
        except Exception as e:
            logger.error(f"Chyba při žádosti o odpověď: {str(e)}")
    
    async def disconnect(self):
        """Odpojí se od OpenAI."""
        try:
            if self.openai_ws:
                await self.openai_ws.close()
                self.is_connected = False
                logger.info("Odpojeno od OpenAI Realtime API")
        except Exception as e:
            logger.error(f"Chyba při odpojování od OpenAI: {str(e)}")

class TwilioMediaStreamHandler:
    """Handler pro Twilio Media Stream WebSocket."""
    
    def __init__(self, openai_service: OpenAIRealtimeService):
        self.openai_service = openai_service
        self.stream_sid = None
        self.call_sid = None
        
    async def handle_twilio_message(self, message: str):
        """Zpracuje zprávu z Twilio Media Stream."""
        try:
            data = json.loads(message)
            event_type = data.get('event', 'unknown')
            
            logger.debug(f"Zpráva z Twilio: {event_type}")
            
            if event_type == 'connected':
                logger.info("Twilio Media Stream připojen")
                
            elif event_type == 'start':
                self.stream_sid = data.get('streamSid')
                self.call_sid = data.get('start', {}).get('callSid')
                logger.info(f"Media Stream začal: {self.stream_sid}")
                
            elif event_type == 'media':
                # Audio data z Twilio
                payload = data.get('media', {}).get('payload', '')
                if payload:
                    # Dekódování audio dat z base64
                    audio_data = base64.b64decode(payload)
                    # Odeslání do OpenAI
                    await self.openai_service.send_audio_to_openai(audio_data)
                    
            elif event_type == 'stop':
                logger.info("Media Stream ukončen")
                await self.openai_service.disconnect()
                
            else:
                logger.debug(f"Neznámý event z Twilio: {event_type}")
                
        except Exception as e:
            logger.error(f"Chyba při zpracování zprávy z Twilio: {str(e)}")
    
    def send_audio_to_twilio(self, audio_data: bytes, websocket):
        """Odešle audio data zpět do Twilio."""
        try:
            # Kódování audio dat do base64
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Vytvoření zprávy pro Twilio
            media_message = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {
                    "payload": audio_base64
                }
            }
            
            # Odeslání přes WebSocket
            asyncio.create_task(websocket.send(json.dumps(media_message)))
            logger.debug("Audio data odeslána do Twilio")
            
        except Exception as e:
            logger.error(f"Chyba při odesílání audio dat do Twilio: {str(e)}")

def handle_media_stream_websocket(request, attempt_id: str = None):
    import websocket
    import threading
    import sys
    from queue import Queue
        logger.info(f"=== ZAČÁTEK MEDIA STREAM WEBSOCKET ===")
    logger.info(f"Request headers: {dict(request.headers)}")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request path: {request.path}")
    logger.info(f"Request args: {request.args}")
        logger.info(f"Attempt ID: {attempt_id}")
    try:
        # Získání kontextu lekce
        lesson_context = ""
        if attempt_id:
            try:
                attempt = Attempt.query.get(attempt_id)
                if attempt and attempt.lesson:
                    lesson = attempt.lesson
                    lesson_context = f"""
Aktuální lekce: {lesson.title}
Obsah lekce: {lesson.script}

Instrukce pro AI asistenta:
- Pomáhej studentovi s touto konkrétní lekcí
- Odpovídej na otázky týkající se obsahu lekce
- Můžeš klást otázky pro ověření porozumění
- Poskytuj zpětnou vazbu na odpovědi studenta
- Buď trpělivý a povzbuzující
"""
                    logger.info(f"Načten kontext lekce: {lesson.title}")
                else:
                    logger.warning(f"Attempt nebo lesson nenalezen pro attempt_id: {attempt_id}")
            except Exception as e:
                logger.error(f"Chyba při načítání lekce: {str(e)}")
        else:
            logger.warning("Chybí attempt_id v requestu")
        # Kontrola OpenAI API klíče
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            logger.error("OPENAI_API_KEY není nastavena")
            return "Missing OpenAI API Key", 500
        logger.info("OPENAI_API_KEY je nastavena")
        # WebSocket URL a headers pro OpenAI
        openai_ws_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        headers = [
            f"Authorization: Bearer {openai_api_key}",
            "OpenAI-Beta: realtime=v1"
        ]
        logger.info(f"Připravuji WebSocket připojení k OpenAI: {openai_ws_url}")
        # Globální proměnné pro WebSocket
        openai_ws = None
        twilio_ws_queue = Queue()
        def on_openai_message(ws, message):
            logger.info(f"[OpenAI WS] Zpráva přijata: {message[:200]}")
            try:
                data = json.loads(message)
                message_type = data.get('type', 'unknown')
                logger.info(f"[OpenAI WS] Typ zprávy: {message_type}")
                if message_type == 'session.created':
                    session_id = data.get('session', {}).get('id')
                    logger.info(f"OpenAI session vytvořena: {session_id}")
                elif message_type == 'response.audio.delta':
                    audio_data = data.get('delta', '')
                    if audio_data:
                        twilio_message = {
                            "event": "media",
                            "streamSid": "stream_sid_placeholder",
                            "media": {"payload": audio_data}
                        }
                        twilio_ws_queue.put(json.dumps(twilio_message))
                        logger.info("Audio delta přeposlána do Twilio fronty")
                elif message_type == 'error':
                    error_info = data.get('error', {})
                    logger.error(f"Chyba z OpenAI: {error_info}")
            except Exception as e:
                logger.error(f"Chyba při zpracování zprávy z OpenAI: {str(e)}")
        def on_openai_error(ws, error):
            logger.error(f"WebSocket chyba s OpenAI: {error}")
        def on_openai_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket připojení k OpenAI bylo ukončeno: {close_status_code} {close_msg}")
        def on_openai_open(ws):
            logger.info("WebSocket připojení k OpenAI bylo navázáno")
            ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": lesson_context,
                    "voice": "alloy",
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 800},
                    "tools": [],
                    "tool_choice": "auto",
                    "temperature": 0.8,
                    "max_response_output_tokens": 4096
                }
            }))
        try:
            openai_ws = websocket.WebSocketApp(
                openai_ws_url,
                header=headers,
                on_open=on_openai_open,
                on_message=on_openai_message,
                on_error=on_openai_error,
                on_close=on_openai_close
            )
            def run_openai_ws():
                logger.info("Spouštím OpenAI WebSocket thread...")
                openai_ws.run_forever()
            openai_thread = threading.Thread(target=run_openai_ws)
            openai_thread.daemon = True
            openai_thread.start()
            logger.info("OpenAI WebSocket byl spuštěn ve vlákně")
        except Exception as e:
            logger.error(f"Chyba při vytváření OpenAI WebSocket: {str(e)}")
            return "Error creating OpenAI WebSocket", 500
        logger.info("handle_media_stream_websocket byl úspěšně inicializován až po spuštění OpenAI WS threadu")
        # Poznámka: Zde by měl být kód pro navázání Twilio WebSocketu, který zde chybí (proto není žádný log z Twilia)
        logger.warning("POZOR: V této implementaci není navázán WebSocket server pro Twilio Media Stream!")
        return f"Media Stream WebSocket nastaven pro attempt_id: {attempt_id} (ale Twilio WS není implementován)", 200
    except Exception as e:
        logger.error(f"Chyba při nastavení Media Stream WebSocket: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return "Error setting up Media Stream WebSocket", 500 