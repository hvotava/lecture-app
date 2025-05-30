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
        self.ws_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
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
                
                if message_type == 'session.created':
                    self.session_id = data.get('session', {}).get('id')
                    logger.info(f"OpenAI session vytvořena: {self.session_id}")
                    
                elif message_type == 'response.audio.delta':
                    # Audio data z OpenAI
                    audio_data = data.get('delta', '')
                    if audio_data:
                        # Dekódování base64 audio dat
                        audio_bytes = base64.b64decode(audio_data)
                        # Odeslání audio dat zpět do Twilio
                        if audio_callback:
                            audio_callback(audio_bytes)
                            
                elif message_type == 'response.audio.done':
                    logger.info("OpenAI dokončilo audio odpověď")
                    
                elif message_type == 'response.text.delta':
                    text_delta = data.get('delta', '')
                    if text_delta:
                        logger.info(f"Text z OpenAI: {text_delta}")
                        
                elif message_type == 'response.text.done':
                    text_content = data.get('text', '')
                    logger.info(f"Kompletní text odpověď: {text_content}")
                    
                elif message_type == 'input_audio_buffer.speech_started':
                    logger.info("OpenAI detekoval začátek řeči")
                    
                elif message_type == 'input_audio_buffer.speech_stopped':
                    logger.info("OpenAI detekoval konec řeči")
                    
                elif message_type == 'conversation.item.input_audio_transcription.completed':
                    transcript = data.get('transcript', '')
                    logger.info(f"Transkripce uživatele: {transcript}")
                    
                elif message_type == 'error':
                    error_info = data.get('error', {})
                    logger.error(f"Chyba z OpenAI: {error_info}")
                    
                else:
                    logger.debug(f"Neznámý typ zprávy z OpenAI: {message_type}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Připojení k OpenAI bylo ukončeno")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Chyba při zpracování zpráv z OpenAI: {str(e)}")
            self.is_connected = False
    
    async def send_audio_to_openai(self, audio_data: bytes):
        """Odešle audio data do OpenAI."""
        try:
            if not self.is_connected or not self.openai_ws:
                logger.warning("Není připojeno k OpenAI - audio data nebudou odeslána")
                return
                
            # Kódování audio dat do base64
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Vytvoření zprávy pro OpenAI
            audio_message = {
                "type": "input_audio_buffer.append",
                "audio": audio_base64
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
                "type": "input_audio_buffer.commit"
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
    """Zpracuje WebSocket připojení pro Media Stream s Flask."""
    import websocket
    import threading
    
    try:
        logger.info(f"=== ZAČÁTEK MEDIA STREAM WEBSOCKET ===")
        logger.info(f"Attempt ID: {attempt_id}")
        
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
            except Exception as e:
                logger.error(f"Chyba při načítání lekce: {str(e)}")
        
        # Konfigurace pro OpenAI Realtime API
        openai_config = {
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

Vždy zůstávej v kontextu výuky a buď konstruktivní.""",
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
        
        # WebSocket URL a headers pro OpenAI
        openai_ws_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        openai_api_key = os.getenv('OPENAI_API_KEY')
        
        if not openai_api_key:
            logger.error("OPENAI_API_KEY není nastavena")
            return "Missing OpenAI API Key", 500
        
        headers = [
            f"Authorization: Bearer {openai_api_key}",
            "OpenAI-Beta: realtime=v1"
        ]
        
        # Globální proměnné pro WebSocket
        openai_ws = None
        twilio_ws_queue = Queue()
        
        def on_openai_message(ws, message):
            """Zpracování zpráv z OpenAI."""
            try:
                data = json.loads(message)
                message_type = data.get('type', 'unknown')
                
                logger.debug(f"Zpráva z OpenAI: {message_type}")
                
                if message_type == 'session.created':
                    session_id = data.get('session', {}).get('id')
                    logger.info(f"OpenAI session vytvořena: {session_id}")
                    
                elif message_type == 'response.audio.delta':
                    # Audio data z OpenAI - přeposílání do Twilio
                    audio_data = data.get('delta', '')
                    if audio_data:
                        # Vytvoření zprávy pro Twilio Media Stream
                        twilio_message = {
                            "event": "media",
                            "streamSid": "stream_sid_placeholder",
                            "media": {
                                "payload": audio_data
                            }
                        }
                        twilio_ws_queue.put(json.dumps(twilio_message))
                        
                elif message_type == 'response.audio.done':
                    logger.info("OpenAI dokončilo audio odpověď")
                    
                elif message_type == 'input_audio_buffer.speech_started':
                    logger.info("OpenAI detekoval začátek řeči")
                    
                elif message_type == 'input_audio_buffer.speech_stopped':
                    logger.info("OpenAI detekoval konec řeči")
                    
                elif message_type == 'conversation.item.input_audio_transcription.completed':
                    transcript = data.get('transcript', '')
                    logger.info(f"Transkripce uživatele: {transcript}")
                    
                elif message_type == 'error':
                    error_info = data.get('error', {})
                    logger.error(f"Chyba z OpenAI: {error_info}")
                    
            except Exception as e:
                logger.error(f"Chyba při zpracování zprávy z OpenAI: {str(e)}")
        
        def on_openai_error(ws, error):
            logger.error(f"WebSocket chyba s OpenAI: {error}")
        
        def on_openai_close(ws, close_status_code, close_msg):
            logger.info("WebSocket připojení k OpenAI bylo ukončeno")
        
        def on_openai_open(ws):
            logger.info("WebSocket připojení k OpenAI bylo navázáno")
            # Odeslání konfigurace
            ws.send(json.dumps(openai_config))
        
        # Vytvoření WebSocket připojení k OpenAI
        try:
            openai_ws = websocket.WebSocketApp(
                openai_ws_url,
                header=headers,
                on_open=on_openai_open,
                on_message=on_openai_message,
                on_error=on_openai_error,
                on_close=on_openai_close
            )
            
            # Spuštění WebSocket v separátním vlákně
            def run_openai_ws():
                openai_ws.run_forever()
            
            openai_thread = threading.Thread(target=run_openai_ws)
            openai_thread.daemon = True
            openai_thread.start()
            
            logger.info("OpenAI WebSocket byl spuštěn")
            
        except Exception as e:
            logger.error(f"Chyba při vytváření OpenAI WebSocket: {str(e)}")
            return "Error creating OpenAI WebSocket", 500
        
        # Funkce pro zpracování Twilio Media Stream zpráv
        def handle_twilio_media_message(message_data):
            """Zpracuje zprávu z Twilio Media Stream."""
            try:
                event = message_data.get('event')
                
                if event == 'connected':
                    logger.info("Twilio Media Stream připojen")
                    
                elif event == 'start':
                    logger.info("Twilio Media Stream začal")
                    stream_sid = message_data.get('start', {}).get('streamSid')
                    logger.info(f"Stream SID: {stream_sid}")
                    
                elif event == 'media':
                    # Audio data z Twilio - přeposílání do OpenAI
                    media = message_data.get('media', {})
                    payload = media.get('payload', '')
                    
                    if payload and openai_ws:
                        # Vytvoření zprávy pro OpenAI
                        openai_message = {
                            "type": "input_audio_buffer.append",
                            "audio": payload
                        }
                        openai_ws.send(json.dumps(openai_message))
                        
                elif event == 'stop':
                    logger.info("Twilio Media Stream ukončen")
                    if openai_ws:
                        openai_ws.close()
                        
            except Exception as e:
                logger.error(f"Chyba při zpracování Twilio zprávy: {str(e)}")
        
        # Návrat informace o úspěšném nastavení
        return f"Media Stream WebSocket nastaven pro attempt_id: {attempt_id}"
        
    except Exception as e:
        logger.error(f"Chyba při nastavení Media Stream WebSocket: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return "Error setting up Media Stream WebSocket", 500 