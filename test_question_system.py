#!/usr/bin/env python3
"""
Test script pro systém odpovídání na otázky uživatelů.
"""

import os
import sys
import logging

# Přidání cesty k aplikaci
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.app import create_app
from app.services.openai_service import OpenAIService
from app.models import Lesson, User, Attempt
from app.database import db

# Nastavení logování
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_question_system():
    """Test systému odpovídání na otázky."""
    
    # Vytvoření aplikace
    app = create_app()
    
    with app.app_context():
        # Inicializace OpenAI služby
        openai_service = OpenAIService()
        
        if not openai_service.enabled:
            print("❌ OpenAI služba není povolena - test nelze spustit")
            return
        
        print("✅ OpenAI služba je připravena")
        
        # Získání testovacích dat z databáze
        lessons = Lesson.query.limit(3).all()
        
        if not lessons:
            print("❌ Žádné lekce v databázi - vytvořím testovací data")
            
            # Vytvoření testovací lekce
            test_lesson = Lesson(
                title="Základy češtiny",
                language="cs",
                script="Dnes se naučíme základní fráze v češtině. Dobrý den znamená pozdrav. Děkuji znamená vyjádření vděčnosti.",
                questions='[{"question": "Co znamená dobrý den?", "correct_answer": "pozdrav", "topic": "pozdravu", "difficulty": 1}]',
                level="beginner"
            )
            
            db.session.add(test_lesson)
            db.session.commit()
            lessons = [test_lesson]
            print("✅ Testovací lekce vytvořena")
        
        # Příprava dat pro test
        current_lesson = {
            'title': lessons[0].title,
            'script': lessons[0].script
        }
        
        other_lessons = [
            {
                'title': lesson.title,
                'script': lesson.script
            }
            for lesson in lessons[1:]
        ]
        
        # Test otázek
        test_questions = [
            "Co znamená dobrý den?",  # Mělo by najít v aktuální lekci
            "Jak se řekne děkuji?",   # Mělo by najít v aktuální lekci
            "Jaké jsou základní barvy?",  # Mělo by použít obecné znalosti
            "Co je to umělá inteligence?"  # Obecné znalosti
        ]
        
        print("\n🧪 Testování systému odpovídání na otázky:")
        print("=" * 50)
        
        for i, question in enumerate(test_questions, 1):
            print(f"\n{i}. Otázka: {question}")
            
            try:
                response = openai_service.answer_user_question(
                    user_question=question,
                    current_lesson=current_lesson,
                    other_lessons=other_lessons,
                    language="cs"
                )
                
                if response:
                    print(f"   📝 Odpověď: {response.get('answer', 'Žádná odpověď')}")
                    print(f"   📍 Zdroj: {response.get('source', 'neznámý')}")
                    print(f"   🎯 Důvěra: {response.get('confidence', 0)}%")
                    
                    if response.get('related_lessons'):
                        print(f"   📚 Související lekce: {', '.join(response['related_lessons'])}")
                    
                    if response.get('explanation'):
                        print(f"   💡 Vysvětlení: {response['explanation']}")
                else:
                    print("   ❌ Žádná odpověď")
                    
            except Exception as e:
                print(f"   ❌ Chyba: {str(e)}")
        
        print("\n✅ Test dokončen!")

if __name__ == "__main__":
    test_question_system() 