#!/usr/bin/env python3
"""
Jednoduchý test pro ověření funkčnosti aplikace
"""

import os
import sys
import logging

# Nastavení testovacího režimu
os.environ['TESTING'] = 'true'

# Nastavení logování
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test importů všech klíčových komponent."""
    try:
        logger.info("Testuji importy...")
        
        # Test základních importů
        from app.app import create_app
        logger.info("✓ Import create_app úspěšný")
        
        from app.database import db
        logger.info("✓ Import databáze úspěšný")
        
        from app.models import User, Lesson, Attempt
        logger.info("✓ Import modelů úspěšný")
        
        from app.services.twilio_service import TwilioService
        logger.info("✓ Import Twilio služby úspěšný")
        
        from app.services.openai_service import OpenAIService
        logger.info("✓ Import OpenAI služby úspěšný")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Chyba při importu: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def test_app_creation():
    """Test vytvoření Flask aplikace."""
    try:
        logger.info("Testuji vytvoření aplikace...")
        
        from app.app import create_app
        app = create_app()
        
        logger.info("✓ Aplikace byla úspěšně vytvořena")
        
        # Test health endpointu
        with app.test_client() as client:
            response = client.get('/health')
            if response.status_code == 200:
                logger.info("✓ Health endpoint funguje")
                return True
            else:
                logger.error(f"✗ Health endpoint vrátil status {response.status_code}")
                return False
                
    except Exception as e:
        logger.error(f"✗ Chyba při vytváření aplikace: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def test_services():
    """Test inicializace služeb."""
    try:
        logger.info("Testuji služby...")
        
        # Test OpenAI služby
        from app.services.openai_service import OpenAIService
        openai_service = OpenAIService()
        logger.info(f"✓ OpenAI služba inicializována (enabled: {openai_service.enabled})")
        
        # Test Twilio služby (může selhat kvůli chybějícím credentials)
        try:
            from app.services.twilio_service import TwilioService
            twilio_service = TwilioService()
            logger.info(f"✓ Twilio služba inicializována (enabled: {twilio_service.enabled})")
        except Exception as e:
            logger.warning(f"⚠ Twilio služba selhala (očekávané): {str(e)}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Chyba při testování služeb: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def main():
    """Hlavní testovací funkce."""
    logger.info("Spouštím testy aplikace...")
    
    tests = [
        ("Import testů", test_imports),
        ("Vytvoření aplikace", test_app_creation),
        ("Testování služeb", test_services)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n--- {test_name} ---")
        if test_func():
            passed += 1
            logger.info(f"✓ {test_name} PROŠEL")
        else:
            logger.error(f"✗ {test_name} SELHAL")
    
    logger.info(f"\n=== VÝSLEDKY ===")
    logger.info(f"Prošlo: {passed}/{total} testů")
    
    if passed == total:
        logger.info("🎉 Všechny testy prošly!")
        return 0
    else:
        logger.error("❌ Některé testy selhaly!")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 