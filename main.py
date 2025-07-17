import os
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from app.models import Attempt, Lesson
from fastapi import Query

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
                url=f"wss://{request.client.host}/voice/media-stream?attempt_id={attempt_id}",
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
            url=f"wss://{request.client.host}/voice/media-stream",
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
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Přijato z Twilia: {data[:200]}")
            # TODO: Zpracovat audio data a předat do OpenAI
            # await websocket.send_text("Echo: " + data)
    except WebSocketDisconnect:
        logger.info("WebSocket odpojen Twiliem")
    except Exception as e:
        logger.error(f"Chyba ve WebSocket handleru: {e}")
        await websocket.close() 