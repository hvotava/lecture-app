#!/usr/bin/env python3
"""
Jednoduchý test WebSocket připojení na /audio endpoint
"""

import asyncio
import websockets
import json
import ssl

async def test_websocket():
    """Test WebSocket připojení"""
    
    # URL WebSocket endpointu
    url = "wss://lecture-app-production.up.railway.app/audio"
    
    print(f"🔗 Připojuji se na: {url}")
    
    # SSL context pro ignorování certifikátů (pouze pro test)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        async with websockets.connect(url, ssl=ssl_context) as websocket:
            print("✅ WebSocket připojení úspěšné!")
            
            # Simulace Twilio start event
            start_message = {
                "event": "start",
                "streamSid": "test-stream-123",
                "start": {
                    "callSid": "test-call-456"
                }
            }
            
            print("📤 Odesílám start event...")
            await websocket.send(json.dumps(start_message))
            
            # Čekáme na odpověď
            print("⏳ Čekám na odpověď (5 sekund)...")
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"✅ Odpověď přijata: {response[:100]}...")
            except asyncio.TimeoutError:
                print("⚠️  Timeout - žádná odpověď během 5 sekund")
            
            # Test media event
            media_message = {
                "event": "media",
                "streamSid": "test-stream-123",
                "media": {
                    "payload": "dGVzdCBhdWRpbyBkYXRh",  # base64 "test audio data"
                    "track": "inbound"
                },
                "sequenceNumber": "1"
            }
            
            print("📤 Odesílám media event...")
            await websocket.send(json.dumps(media_message))
            
            # Čekáme na více odpovědí
            print("⏳ Čekám na další odpovědi (10 sekund)...")
            for i in range(10):
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    print(f"📥 Odpověď {i+1}: {response[:100]}...")
                except asyncio.TimeoutError:
                    print(f"⏰ Timeout {i+1}/10")
                    break
            
            # Stop event
            stop_message = {
                "event": "stop",
                "streamSid": "test-stream-123"
            }
            
            print("📤 Odesílám stop event...")
            await websocket.send(json.dumps(stop_message))
            
            print("✅ Test dokončen!")
            
    except Exception as e:
        print(f"❌ Chyba při připojení: {e}")

if __name__ == "__main__":
    print("🧪 Spouštím WebSocket test...")
    asyncio.run(test_websocket()) 