#!/usr/bin/env python3
"""
Test přístupu k OpenAI Realtime API
"""

import asyncio
import websockets
import json
import os
import ssl
from dotenv import load_dotenv

# Načtení environment variables
load_dotenv()

async def test_openai_realtime():
    """Test připojení k OpenAI Realtime API"""
    
    # Získání API klíče
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY není nastaven v .env souboru")
        return False
    
    # URL a headers podle oficiální dokumentace
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    print(f"🔗 Testuji připojení k OpenAI Realtime API...")
    print(f"URL: {url}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else 'krátký'}")
    
    try:
        # SSL context pro ignorování certifikátů (pouze pro test)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Připojení k OpenAI Realtime API
        async with websockets.connect(url, extra_headers=headers, ssl=ssl_context) as websocket:
            print("✅ Připojení k OpenAI Realtime API úspěšné!")
            
            # Čekáme na session.created event
            print("⏳ Čekám na session.created event...")
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                event = json.loads(message)
                print(f"📥 Přijat event: {event.get('type', 'unknown')}")
                
                if event.get('type') == 'session.created':
                    print("✅ Session vytvořena úspěšně!")
                    print(f"Session ID: {event.get('session', {}).get('id', 'N/A')}")
                    print(f"Model: {event.get('session', {}).get('model', 'N/A')}")
                    return True
                else:
                    print(f"⚠️  Neočekávaný event: {event}")
                    return False
                    
            except asyncio.TimeoutError:
                print("⚠️  Timeout - žádný event během 10 sekund")
                return False
                
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ HTTP chyba: {e}")
        if e.status_code == 401:
            print("   → Neplatný API klíč nebo nemáte přístup k Realtime API")
        elif e.status_code == 403:
            print("   → Nemáte oprávnění k Realtime API")
        elif e.status_code == 404:
            print("   → Neplatná URL nebo model")
        return False
        
    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket chyba: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Neočekávaná chyba: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

async def test_standard_openai():
    """Test standardního OpenAI API pro porovnání"""
    
    print("\n" + "="*50)
    print("🧪 Test standardního OpenAI API pro porovnání...")
    
    try:
        import openai
        
        api_key = os.getenv('OPENAI_API_KEY')
        client = openai.OpenAI(api_key=api_key)
        
        # Jednoduchý test
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        
        print("✅ Standardní OpenAI API funguje!")
        print(f"Model: {response.model}")
        print(f"Odpověď: {response.choices[0].message.content}")
        return True
        
    except Exception as e:
        print(f"❌ Standardní OpenAI API nefunguje: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Spouštím test OpenAI Realtime API...")
    
    async def main():
        realtime_ok = await test_openai_realtime()
        standard_ok = await test_standard_openai()
        
        print("\n" + "="*50)
        print("📊 Výsledky testů:")
        print(f"OpenAI Realtime API: {'✅ OK' if realtime_ok else '❌ FAIL'}")
        print(f"Standardní OpenAI API: {'✅ OK' if standard_ok else '❌ FAIL'}")
        
        if not realtime_ok and standard_ok:
            print("\n💡 Doporučení:")
            print("- Váš API klíč funguje, ale nemáte přístup k Realtime API")
            print("- Kontaktujte OpenAI pro aktivaci Realtime API přístupu")
            print("- Realtime API je v beta verzi a vyžaduje speciální přístup")
        
        return realtime_ok
    
    result = asyncio.run(main())
    exit(0 if result else 1) 