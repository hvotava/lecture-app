#!/usr/bin/env python3
"""
Jednoduchý testovací skript pro WebSocket spojení bez externích závislostí.
Používá pouze standardní knihovny Pythonu.
"""

import socket
import ssl
import base64
import struct
import hashlib
import urllib.parse
import json

def create_websocket_handshake(host, path):
    """Vytvoří WebSocket handshake request."""
    key = base64.b64encode(b"test-key-123456789").decode()
    
    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    return handshake.encode()

def test_websocket_connection():
    """Testuje WebSocket spojení pomocí raw socket."""
    
    host = "lecture-app-production.up.railway.app"
    port = 443
    path = "/voice/media-stream?attempt_id=1"
    
    print(f"🔍 Testuji WebSocket spojení na {host}:{port}{path}")
    
    try:
        # Vytvoření SSL socketu s ignorováním certifikátu
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        sock = socket.create_connection((host, port))
        ssl_sock = context.wrap_socket(sock, server_hostname=host)
        
        print("✅ SSL spojení navázáno")
        
        # Odeslání handshake
        handshake = create_websocket_handshake(host, path)
        ssl_sock.send(handshake)
        
        print("📤 Handshake odeslán")
        
        # Čtení odpovědi
        response = ssl_sock.recv(1024).decode()
        print(f"📥 Odpověď serveru:")
        print(response[:200] + "..." if len(response) > 200 else response)
        
        if "101 Switching Protocols" in response:
            print("✅ WebSocket handshake úspěšný!")
            return True
        else:
            print("❌ WebSocket handshake selhal")
            return False
            
    except Exception as e:
        print(f"❌ Chyba při testování: {e}")
        return False
    finally:
        try:
            ssl_sock.close()
        except:
            pass

def test_http_endpoint():
    """Testuje HTTP endpoint pro ověření, že server běží."""
    
    import urllib.request
    import ssl
    
    url = "https://lecture-app-production.up.railway.app/health"
    
    print(f"🔍 Testuji HTTP endpoint: {url}")
    
    try:
        # Vytvoření context s ignorováním SSL certifikátu
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Vytvoření opener s custom context
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context)
        )
        urllib.request.install_opener(opener)
        
        response = urllib.request.urlopen(url, timeout=10)
        print(f"✅ HTTP endpoint odpovídá: {response.status}")
        return True
    except Exception as e:
        print(f"❌ HTTP endpoint neodpovídá: {e}")
        return False

def main():
    """Hlavní funkce."""
    
    print("🚀 Spouštím jednoduché testy...")
    print("=" * 50)
    
    # Test 1: HTTP endpoint
    print("Test 1: HTTP endpoint")
    http_ok = test_http_endpoint()
    print()
    
    # Test 2: WebSocket handshake
    print("Test 2: WebSocket handshake")
    ws_ok = test_websocket_connection()
    print()
    
    print("=" * 50)
    print("📊 Výsledky testů:")
    print(f"HTTP endpoint: {'✅ OK' if http_ok else '❌ FAIL'}")
    print(f"WebSocket handshake: {'✅ OK' if ws_ok else '❌ FAIL'}")
    
    if http_ok and ws_ok:
        print("🎉 Všechny testy prošly! WebSocket endpoint by měl fungovat.")
    elif http_ok and not ws_ok:
        print("⚠️ Server běží, ale WebSocket handshake selhal.")
        print("   Možná je problém s WebSocket implementací nebo konfigurací.")
    else:
        print("❌ Server neodpovídá nebo není dostupný.")

if __name__ == "__main__":
    main() 