#!/usr/bin/env python3
"""
Test celého flow hlasové aplikace - od vytvoření pokusu po odpověď na otázku.
"""

import requests
import logging
import re
from urllib.parse import urlencode

# Nastavení logování
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_full_voice_flow():
    """Testuje celý flow hlasové aplikace."""
    
    base_url = "https://lecture-synqflows.lm.r.appspot.com"
    
    print("🧪 Testování celého flow hlasové aplikace:")
    print("=" * 60)
    
    # Krok 1: Získání CSRF tokenu
    print("\n1. Získávání CSRF tokenu...")
    try:
        response = requests.get(f"{base_url}/users")
        if response.status_code == 200:
            # Hledání CSRF tokenu v HTML
            csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
            if csrf_match:
                csrf_token = csrf_match.group(1)
                print(f"   ✅ CSRF token získán: {csrf_token[:20]}...")
            else:
                print("   ❌ CSRF token nenalezen")
                return
        else:
            print(f"   ❌ Chyba při získávání CSRF tokenu: {response.status_code}")
            return
    except Exception as e:
        print(f"   ❌ Chyba: {str(e)}")
        return
    
    # Krok 2: Vytvoření nového pokusu
    print("\n2. Vytváření nového pokusu...")
    try:
        data = {'csrf_token': csrf_token}
        response = requests.post(f"{base_url}/users/1/call", data=data, allow_redirects=False)
        
        if response.status_code == 302:
            print(f"   ✅ Pokus vytvořen, přesměrování na: {response.headers.get('Location', 'N/A')}")
            
            # Extrakce attempt_id z Location header
            location = response.headers.get('Location', '')
            attempt_match = re.search(r'attempt_id=(\d+)', location)
            if attempt_match:
                attempt_id = attempt_match.group(1)
                print(f"   📝 Attempt ID: {attempt_id}")
            else:
                print("   ❌ Attempt ID nenalezeno v přesměrování")
                return
        else:
            print(f"   ❌ Chyba při vytváření pokusu: {response.status_code}")
            print(f"   📝 Odpověď: {response.text[:200]}...")
            return
    except Exception as e:
        print(f"   ❌ Chyba: {str(e)}")
        return
    
    # Krok 3: Spuštění hlasového endpointu
    print(f"\n3. Spouštění hlasového endpointu s attempt_id {attempt_id}...")
    try:
        response = requests.post(f"{base_url}/voice/?attempt_id={attempt_id}")
        
        if response.status_code == 200:
            print(f"   ✅ Hlasový endpoint úspěšný")
            print(f"   📝 Odpověď: {response.text[:200]}...")
            
            # Kontrola, zda obsahuje přesměrování na otázky
            if "questions" in response.text:
                print("   🔄 Obsahuje přesměrování na otázky")
            else:
                print("   ⚠️  Nepřesměrovává na otázky")
        else:
            print(f"   ❌ Chyba: {response.status_code}")
            return
    except Exception as e:
        print(f"   ❌ Chyba: {str(e)}")
        return
    
    # Krok 4: Test otázek
    print(f"\n4. Testování otázek pro attempt_id {attempt_id}...")
    try:
        response = requests.get(f"{base_url}/voice/questions?attempt_id={attempt_id}&question_index=0")
        
        if response.status_code == 200:
            print(f"   ✅ Endpoint otázek úspěšný")
            print(f"   📝 Odpověď: {response.text[:200]}...")
            
            # Kontrola, zda obsahuje otázku
            if "Otázka číslo" in response.text or "question" in response.text.lower():
                print("   ❓ Obsahuje otázku")
                has_questions = True
            else:
                print("   ⚠️  Neobsahuje otázku")
                has_questions = False
        else:
            print(f"   ❌ Chyba: {response.status_code}")
            has_questions = False
    except Exception as e:
        print(f"   ❌ Chyba: {str(e)}")
        has_questions = False
    
    # Krok 5: Test odpovědi na otázku (pouze pokud jsou otázky)
    if has_questions:
        print(f"\n5. Testování odpovědi 'dobře' na otázku...")
        try:
            data = {'SpeechResult': 'dobře'}
            url = f"{base_url}/voice/handle_answer?attempt_id={attempt_id}&question_index=0"
            response = requests.post(url, data=data, timeout=30)
            
            if response.status_code == 200:
                print(f"   ✅ Status: {response.status_code}")
                print(f"   📝 Odpověď: {response.text[:300]}...")
                
                # Kontrola AI vyhodnocení
                if "Vyhodnocuji vaši odpověď pomocí AI" in response.text:
                    print("   🤖 AI vyhodnocení bylo spuštěno!")
                elif "Správně" in response.text or "Bohužel" in response.text:
                    print("   🎯 Obsahuje zpětnou vazbu od AI")
                else:
                    print("   ⚠️  AI vyhodnocení nebylo detekováno")
            else:
                print(f"   ❌ Chyba: {response.status_code}")
                print(f"   📝 Odpověď: {response.text}")
        except Exception as e:
            print(f"   ❌ Chyba při testu odpovědi: {str(e)}")
    else:
        print("\n5. ⏭️  Přeskakuji test odpovědi - nejsou dostupné otázky")
    
    print("\n✅ Test celého flow dokončen!")

if __name__ == "__main__":
    test_full_voice_flow() 