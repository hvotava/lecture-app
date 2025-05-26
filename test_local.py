#!/usr/bin/env python3
"""
Lokální testovací script pro aplikaci
"""

# Nejprve načteme lokální konfiguraci
import local_config

# Pak importujeme aplikaci
from wsgi import app
import requests
import time
import threading

def test_basic_endpoints():
    """Test základních endpointů"""
    base_url = "http://localhost:5000"
    
    print("🧪 Testování základních endpointů...")
    
    # Test hlavní stránky
    try:
        response = requests.get(f"{base_url}/")
        print(f"✅ Hlavní stránka: {response.status_code}")
    except Exception as e:
        print(f"❌ Hlavní stránka: {e}")
    
    # Test voice webhook
    try:
        response = requests.get(f"{base_url}/voice/webhook")
        print(f"✅ Voice webhook: {response.status_code}")
    except Exception as e:
        print(f"❌ Voice webhook: {e}")
    
    # Test health check
    try:
        response = requests.get(f"{base_url}/health")
        print(f"✅ Health check: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check: {e}")

def run_server():
    """Spustí server v separátním vlákně"""
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    print("🚀 Spouštím lokální testování...")
    
    # Spustíme server v separátním vlákně
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Počkáme, až se server spustí
    print("⏳ Čekám na spuštění serveru...")
    time.sleep(3)
    
    # Spustíme testy
    test_basic_endpoints()
    
    print("\n✅ Lokální testování dokončeno!")
    print("💡 Pro ruční testování otevřete: http://localhost:5000")
    print("🛑 Pro ukončení stiskněte Ctrl+C")
    
    try:
        # Necháme server běžet
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Ukončuji server...") 