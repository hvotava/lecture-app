#!/usr/bin/env python3
"""
Test hlasové aplikace s platným attempt_id.
"""

import requests
import logging

# Nastavení logování
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_with_valid_attempt():
    """Testuje hlasovou aplikaci s platným attempt_id."""
    
    base_url = "https://lecture-synqflows.lm.r.appspot.com"
    attempt_id = 2  # Platný attempt_id z databáze
    
    print("🧪 Test hlasové aplikace s platným attempt_id:")
    print("=" * 60)
    print(f"📝 Používám attempt_id: {attempt_id}")
    
    # Test 1: Endpoint otázek
    print(f"\n1. Testování endpointu otázek...")
    try:
        response = requests.get(f"{base_url}/voice/questions?attempt_id={attempt_id}&question_index=0")
        
        print(f"   Status: {response.status_code}")
        print(f"   Odpověď: {response.text[:300]}...")
        
        if response.status_code == 200:
            if "Otázka číslo" in response.text or "kolik je hodin" in response.text:
                print("   ✅ Endpoint otázek funguje správně")
                has_questions = True
            else:
                print("   ⚠️  Endpoint funguje, ale neobsahuje očekávanou otázku")
                has_questions = False
        else:
            print("   ❌ Endpoint otázek nefunguje")
            has_questions = False
    except Exception as e:
        print(f"   ❌ Chyba: {str(e)}")
        has_questions = False
    
    # Test 2: Odpověď na otázku (pouze pokud jsou otázky)
    if has_questions:
        print(f"\n2. Testování odpovědi 'dobře' na otázku...")
        try:
            data = {'SpeechResult': 'dobře'}
            url = f"{base_url}/voice/handle_answer?attempt_id={attempt_id}&question_index=0"
            response = requests.post(url, data=data, timeout=30)
            
            print(f"   Status: {response.status_code}")
            print(f"   Odpověď: {response.text[:400]}...")
            
            if response.status_code == 200:
                # Kontrola AI vyhodnocení
                if "Vyhodnocuji vaši odpověď pomocí AI" in response.text:
                    print("   🤖 AI vyhodnocení bylo spuštěno!")
                elif "Správně" in response.text or "Bohužel" in response.text:
                    print("   🎯 Obsahuje zpětnou vazbu od AI")
                elif "Děkuji za odpověď" in response.text:
                    print("   📝 Odpověď byla zpracována")
                else:
                    print("   ⚠️  AI vyhodnocení nebylo detekováno")
            else:
                print(f"   ❌ Chyba při zpracování odpovědi")
        except Exception as e:
            print(f"   ❌ Chyba při testu odpovědi: {str(e)}")
        
        # Test 3: Odpověď s klíčovým slovem "otázka"
        print(f"\n3. Testování klíčového slova 'otázka'...")
        try:
            data = {'SpeechResult': 'otázka'}
            url = f"{base_url}/voice/handle_answer?attempt_id={attempt_id}&question_index=0"
            response = requests.post(url, data=data, timeout=30)
            
            print(f"   Status: {response.status_code}")
            print(f"   Odpověď: {response.text[:300]}...")
            
            if response.status_code == 200:
                if "Jakou máte otázku" in response.text or "question" in response.text.lower():
                    print("   ✅ Klíčové slovo 'otázka' funguje správně")
                else:
                    print("   ⚠️  Klíčové slovo nebylo rozpoznáno")
            else:
                print(f"   ❌ Chyba při zpracování klíčového slova")
        except Exception as e:
            print(f"   ❌ Chyba při testu klíčového slova: {str(e)}")
    else:
        print("\n2-3. ⏭️  Přeskakuji testy odpovědí - nejsou dostupné otázky")
    
    print("\n✅ Test dokončen!")

if __name__ == "__main__":
    test_with_valid_attempt() 