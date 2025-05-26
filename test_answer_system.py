#!/usr/bin/env python3
"""
Test systému odpovědí na otázky v hlasové aplikaci.
"""

import requests
import logging
from urllib.parse import urlencode

# Nastavení logování
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_answer_processing():
    """Testuje zpracování odpovědí na otázky."""
    
    base_url = "https://lecture-synqflows.lm.r.appspot.com"
    
    print("🧪 Testování systému odpovědí na otázky:")
    print("=" * 50)
    
    # Test 1: Simulace odpovědi "dobře" na otázku
    print("\n1. Test odpovědi 'dobře' na otázku:")
    try:
        # Simulujeme POST požadavek s odpovědí
        data = {
            'SpeechResult': 'dobře'
        }
        
        # Parametry v URL
        url = f"{base_url}/voice/handle_answer?attempt_id=11&question_index=0"
        response = requests.post(url, data=data, timeout=30)
        
        if response.status_code == 200:
            print(f"   ✅ Status: {response.status_code}")
            print(f"   📝 Odpověď: {response.text[:200]}...")
            
            # Kontrola, zda odpověď obsahuje AI vyhodnocení
            if "Vyhodnocuji vaši odpověď pomocí AI" in response.text:
                print("   🤖 AI vyhodnocení bylo spuštěno")
            else:
                print("   ⚠️  AI vyhodnocení nebylo detekováno")
                
        else:
            print(f"   ❌ Chyba: {response.status_code}")
            print(f"   📝 Odpověď: {response.text}")
            
    except Exception as e:
        print(f"   ❌ Chyba při testu: {str(e)}")
    
    # Test 2: Simulace odpovědi "špatně" na otázku
    print("\n2. Test odpovědi 'špatně' na otázku:")
    try:
        data = {
            'SpeechResult': 'špatně'
        }
        
        url = f"{base_url}/voice/handle_answer?attempt_id=11&question_index=0"
        response = requests.post(url, data=data, timeout=30)
        
        if response.status_code == 200:
            print(f"   ✅ Status: {response.status_code}")
            print(f"   📝 Odpověď: {response.text[:200]}...")
        else:
            print(f"   ❌ Chyba: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Chyba při testu: {str(e)}")
    
    # Test 3: Simulace klíčového slova "otázka"
    print("\n3. Test klíčového slova 'otázka':")
    try:
        data = {
            'SpeechResult': 'otázka'
        }
        
        url = f"{base_url}/voice/handle_answer?attempt_id=11&question_index=0"
        response = requests.post(url, data=data, timeout=30)
        
        if response.status_code == 200:
            print(f"   ✅ Status: {response.status_code}")
            print(f"   📝 Odpověď: {response.text[:200]}...")
            
            # Kontrola přesměrování na otázky
            if "Jaká je vaše otázka" in response.text:
                print("   🔄 Správně přesměrováno na kladení otázek")
            else:
                print("   ⚠️  Přesměrování na otázky nebylo detekováno")
                
        else:
            print(f"   ❌ Chyba: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Chyba při testu: {str(e)}")
    
    print("\n✅ Test dokončen!")

if __name__ == "__main__":
    test_answer_processing() 