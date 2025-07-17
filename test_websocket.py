#!/usr/bin/env python3
"""
Testovací WebSocket klient pro ověření spojení s Twilio Media Streams endpointem.
"""

import asyncio
import websockets
import json
import logging
from datetime import datetime

# Nastavení logování
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_websocket_connection():
    """Testuje připojení na WebSocket endpoint."""
    
    # URL WebSocket endpointu
    websocket_url = "wss://lecture-app-production.up.railway.app/voice/media-stream?attempt_id=1"
    
    logger.info(f"Připojuji se na WebSocket: {websocket_url}")
    
    try:
        async with websockets.connect(websocket_url) as websocket:
            logger.info("✅ WebSocket spojení úspěšně navázáno!")
            
            # Pošleme testovací zprávu (simulace Twilio Media Streams)
            test_message = {
                "event": "media",
                "streamSid": "test-stream-123",
                "media": {
                    "payload": "dGVzdCBhdWRpbyBkYXRh"  # base64 encoded "test audio data"
                }
            }
            
            logger.info(f"Odesílám testovací zprávu: {test_message}")
            await websocket.send(json.dumps(test_message))
            
            # Počkáme na odpověď
            logger.info("Čekám na odpověď...")
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                logger.info(f"✅ Obdržena odpověď: {response[:200]}...")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Timeout - žádná odpověď nebyla obdržena během 10 sekund")
            
            # Pošleme stop event
            stop_message = {
                "event": "stop",
                "streamSid": "test-stream-123"
            }
            
            logger.info("Odesílám stop event...")
            await websocket.send(json.dumps(stop_message))
            
            # Počkáme na další odpověď
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                logger.info(f"✅ Obdržena odpověď na stop: {response[:200]}...")
            except asyncio.TimeoutError:
                logger.info("ℹ️ Žádná odpověď na stop event (to je OK)")
            
            logger.info("✅ WebSocket test dokončen úspěšně!")
            
    except websockets.exceptions.InvalidURI:
        logger.error("❌ Neplatná WebSocket URL")
    except websockets.exceptions.ConnectionClosed:
        logger.error("❌ WebSocket spojení bylo uzavřeno")
    except websockets.exceptions.InvalidMessage:
        logger.error("❌ Neplatná WebSocket zpráva")
    except Exception as e:
        logger.error(f"❌ Chyba při připojení: {e}")

async def test_simple_connection():
    """Jednoduchý test pouze připojení bez odesílání dat."""
    
    websocket_url = "wss://lecture-app-production.up.railway.app/voice/media-stream"
    
    logger.info(f"Testuji jednoduché připojení na: {websocket_url}")
    
    try:
        async with websockets.connect(websocket_url) as websocket:
            logger.info("✅ Základní WebSocket spojení funguje!")
            return True
    except Exception as e:
        logger.error(f"❌ Základní WebSocket spojení selhalo: {e}")
        return False

async def test_with_attempt_id():
    """Test s attempt_id parametrem."""
    
    websocket_url = "wss://lecture-app-production.up.railway.app/voice/media-stream?attempt_id=1"
    
    logger.info(f"Testuji připojení s attempt_id: {websocket_url}")
    
    try:
        async with websockets.connect(websocket_url) as websocket:
            logger.info("✅ WebSocket spojení s attempt_id funguje!")
            
            # Počkáme chvíli, zda server pošle nějakou zprávu
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                logger.info(f"✅ Server poslal zprávu: {response[:200]}...")
            except asyncio.TimeoutError:
                logger.info("ℹ️ Server neposlal žádnou zprávu (to je OK)")
            
            return True
    except Exception as e:
        logger.error(f"❌ WebSocket spojení s attempt_id selhalo: {e}")
        return False

async def main():
    """Hlavní funkce pro spuštění všech testů."""
    
    logger.info("🚀 Spouštím WebSocket testy...")
    logger.info("=" * 50)
    
    # Test 1: Jednoduché připojení
    logger.info("Test 1: Jednoduché připojení")
    simple_ok = await test_simple_connection()
    logger.info("")
    
    # Test 2: Připojení s attempt_id
    logger.info("Test 2: Připojení s attempt_id")
    attempt_ok = await test_with_attempt_id()
    logger.info("")
    
    # Test 3: Kompletní test s Twilio simulací
    if simple_ok and attempt_ok:
        logger.info("Test 3: Kompletní test s Twilio simulací")
        await test_websocket_connection()
    else:
        logger.warning("⚠️ Přeskakuji kompletní test - základní připojení nefunguje")
    
    logger.info("=" * 50)
    logger.info("🏁 WebSocket testy dokončeny!")

if __name__ == "__main__":
    # Spuštění testů
    asyncio.run(main()) 