#!/usr/bin/env python3
"""
Debug script pro kontrolu otázek.
"""

import requests
import json

def debug_questions():
    """Debug otázek."""
    
    base_url = "https://lecture-synqflows.lm.r.appspot.com"
    attempt_id = 2
    
    print("🔍 Debug otázek:")
    print("=" * 50)
    
    # Test s verbose výstupem
    print(f"\n1. Testování endpointu s attempt_id {attempt_id}...")
    
    try:
        response = requests.get(f"{base_url}/voice/questions?attempt_id={attempt_id}&question_index=0")
        
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"Celá odpověď:")
        print(response.text)
        print("-" * 50)
        
        # Pokus o parsování XML
        if response.text.startswith('<?xml'):
            print("Odpověď je XML")
            if "Došlo k chybě" in response.text:
                print("❌ Obsahuje chybovou zprávu")
            elif "Otázka číslo" in response.text:
                print("✅ Obsahuje otázku")
            else:
                print("⚠️  Neznámý obsah XML")
        else:
            print("Odpověď není XML")
            
    except Exception as e:
        print(f"❌ Chyba při požadavku: {str(e)}")
    
    # Test s jiným attempt_id
    print(f"\n2. Testování s attempt_id 1...")
    
    try:
        response = requests.get(f"{base_url}/voice/questions?attempt_id=1&question_index=0")
        
        print(f"Status: {response.status_code}")
        print(f"Odpověď: {response.text[:200]}...")
        
    except Exception as e:
        print(f"❌ Chyba při požadavku: {str(e)}")
    
    # Test bez attempt_id
    print(f"\n3. Testování bez attempt_id...")
    
    try:
        response = requests.get(f"{base_url}/voice/questions?question_index=0")
        
        print(f"Status: {response.status_code}")
        print(f"Odpověď: {response.text[:200]}...")
        
    except Exception as e:
        print(f"❌ Chyba při požadavku: {str(e)}")

if __name__ == "__main__":
    debug_questions() 