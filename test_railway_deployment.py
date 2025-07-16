#!/usr/bin/env python3
"""
Test script pro ověření Railway deploymentu
"""

import requests
import os
import sys
import json

def test_health_check(base_url):
    """Testuje health check endpoint"""
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        print(f"✅ Health check: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {data}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_voice_endpoint(base_url):
    """Testuje voice endpoint"""
    try:
        response = requests.get(f"{base_url}/voice", timeout=10)
        print(f"✅ Voice endpoint: {response.status_code}")
        return response.status_code in [200, 405]  # 405 je OK pro GET na POST endpoint
    except Exception as e:
        print(f"❌ Voice endpoint failed: {e}")
        return False

def test_environment_variables():
    """Testuje environment variables"""
    required_vars = [
        'SECRET_KEY',
        'TWILIO_ACCOUNT_SID',
        'TWILIO_AUTH_TOKEN',
        'TWILIO_PHONE_NUMBER',
        'OPENAI_API_KEY',
        'DATABASE_URL',
        'WEBHOOK_BASE_URL'
    ]
    
    print("🔍 Kontrola environment variables:")
    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"   ✅ {var}: {'*' * min(len(value), 10)}...")
        else:
            print(f"   ❌ {var}: CHYBÍ")
            missing.append(var)
    
    return len(missing) == 0

def main():
    """Hlavní funkce pro testování"""
    print("🚂 Railway Deployment Test")
    print("=" * 40)
    
    # Test environment variables
    env_ok = test_environment_variables()
    print()
    
    # Test endpoints
    base_url = os.getenv('WEBHOOK_BASE_URL', 'http://localhost:8080')
    print(f"🌐 Testuji endpoints na: {base_url}")
    print()
    
    health_ok = test_health_check(base_url)
    voice_ok = test_voice_endpoint(base_url)
    
    print()
    print("📊 Výsledky testů:")
    print(f"   Environment variables: {'✅ OK' if env_ok else '❌ CHYBA'}")
    print(f"   Health check: {'✅ OK' if health_ok else '❌ CHYBA'}")
    print(f"   Voice endpoint: {'✅ OK' if voice_ok else '❌ CHYBA'}")
    
    if env_ok and health_ok and voice_ok:
        print("\n🎉 Všechny testy prošly! Railway deployment je funkční.")
        return 0
    else:
        print("\n⚠️  Některé testy selhaly. Zkontrolujte konfiguraci.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 