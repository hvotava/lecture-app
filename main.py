import os
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging

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
async def voice(request: Request):
    # TODO: Převést logiku z Flasku (včetně TwiML generování)
    logger.info("Přijat Twilio webhook na /voice/")
    # Ukázková odpověď (nutno nahradit skutečnou TwiML logikou)
    twiml = """<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Say>Test FastAPI Twilio</Say></Response>"""
    return Response(content=twiml, media_type="text/xml")

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