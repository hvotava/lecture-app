#!/usr/bin/env python3
"""
Test script pro ověření Docker deploymentu
"""

import os
import sys
import requests
import time

def test_environment():
    """Testuje environment variables"""
    print("🔍 Kontrola environment variables:")
    
    required_vars = [
        'PORT',
        'FLASK_ENV',
        'SECRET_KEY',
        'DATABASE_URL'
    ]
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"   ✅ {var}: {value[:20]}..." if len(value) > 20 else f"   ✅ {var}: {value}")
        else:
            print(f"   ❌ {var}: CHYBÍ")
    
    print(f"   📍 Aktuální port: {os.getenv('PORT', 'NENASTAVEN')}")

def test_health_check():
    """Testuje health check endpoint"""
    port = os.getenv('PORT', '8080')
    base_url = f"http://localhost:{port}"
    
    print(f"\n🌐 Testuji health check na: {base_url}")
    
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        print(f"   ✅ Health check: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   📄 Response: {data}")
        return True
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return False

def test_app_startup():
    """Testuje, jestli se aplikace spustí"""
    print("\n🚀 Testuji spuštění aplikace:")
    
    try:
        from wsgi import app
        print("   ✅ Aplikace se úspěšně importovala")
        
        # Test vytvoření testovacího requestu
        with app.test_client() as client:
            response = client.get('/health')
            print(f"   ✅ Test client: {response.status_code}")
        
        return True
    except Exception as e:
        print(f"   ❌ Aplikace se nespustila: {e}")
        return False

def main():
    """Hlavní funkce"""
    print("🐳 Docker Deployment Test")
    print("=" * 40)
    
    # Test environment
    test_environment()
    
    # Test aplikace
    app_ok = test_app_startup()
    
    # Test health check (pokud aplikace běží)
    if app_ok:
        health_ok = test_health_check()
    else:
        health_ok = False
    
    print("\n📊 Výsledky:")
    print(f"   Aplikace: {'✅ OK' if app_ok else '❌ CHYBA'}")
    print(f"   Health check: {'✅ OK' if health_ok else '❌ CHYBA'}")
    
    if app_ok and health_ok:
        print("\n🎉 Všechny testy prošly!")
        return 0
    else:
        print("\n⚠️  Některé testy selhaly.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 