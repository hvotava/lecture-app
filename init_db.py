#!/usr/bin/env python3
"""
Skript pro inicializaci databáze
"""

import os
import sys
from app import create_app, db
from app.models import User, Lesson, Attempt, Answer

def init_database():
    """Inicializuje databázi a vytvoří tabulky."""
    print("🗄️  Inicializuji databázi...")
    
    try:
        # Vytvoření aplikace
        app = create_app()
        
        with app.app_context():
            # Vytvoření všech tabulek
            print("📋 Vytvářím tabulky...")
            db.create_all()
            print("✅ Tabulky byly úspěšně vytvořeny")
            
            # Kontrola, zda tabulky existují
            print("🔍 Kontroluji tabulky...")
            
            # Test User tabulky
            try:
                user_count = User.query.count()
                print(f"✅ Tabulka 'users' existuje - {user_count} uživatelů")
            except Exception as e:
                print(f"❌ Chyba při kontrole tabulky 'users': {e}")
            
            # Test Lesson tabulky
            try:
                lesson_count = Lesson.query.count()
                print(f"✅ Tabulka 'lessons' existuje - {lesson_count} lekcí")
            except Exception as e:
                print(f"❌ Chyba při kontrole tabulky 'lessons': {e}")
            
            # Test Attempt tabulky
            try:
                attempt_count = Attempt.query.count()
                print(f"✅ Tabulka 'attempts' existuje - {attempt_count} pokusů")
            except Exception as e:
                print(f"❌ Chyba při kontrole tabulky 'attempts': {e}")
            
            # Test Answer tabulky
            try:
                answer_count = Answer.query.count()
                print(f"✅ Tabulka 'answers' existuje - {answer_count} odpovědí")
            except Exception as e:
                print(f"❌ Chyba při kontrole tabulky 'answers': {e}")
            
            print("🎉 Inicializace databáze dokončena!")
            
    except Exception as e:
        print(f"❌ Chyba při inicializaci databáze: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False
    
    return True

def create_sample_data():
    """Vytvoří ukázková data pro testování."""
    print("📝 Vytvářím ukázková data...")
    
    try:
        app = create_app()
        
        with app.app_context():
            # Vytvoření ukázkového uživatele
            if User.query.count() == 0:
                user = User(
                    name="Test Uživatel",
                    phone="+420 123 456 789",
                    language="cs",
                    detail="Ukázkový uživatel pro testování"
                )
                db.session.add(user)
                print("✅ Vytvořen ukázkový uživatel")
            
            # Vytvoření ukázkové lekce
            if Lesson.query.count() == 0:
                lesson = Lesson(
                    title="Ukázková lekce češtiny",
                    language="cs",
                    script="Toto je ukázkový text lekce pro testování aplikace.",
                    questions={
                        "all": [
                            {
                                "question": "Jaký je hlavní jazyk této lekce?",
                                "answer": "čeština"
                            },
                            {
                                "question": "Co je cílem této lekce?",
                                "answer": "testování"
                            }
                        ],
                        "current": "Jaký je hlavní jazyk této lekce?"
                    }
                )
                db.session.add(lesson)
                print("✅ Vytvořena ukázková lekce")
            
            db.session.commit()
            print("🎉 Ukázková data byla vytvořena!")
            
    except Exception as e:
        print(f"❌ Chyba při vytváření ukázkových dat: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False
    
    return True

def main():
    """Hlavní funkce."""
    print("🚀 Inicializace databáze pro Lecture App")
    print("=" * 50)
    
    # Inicializace databáze
    if not init_database():
        print("❌ Inicializace databáze selhala")
        return 1
    
    # Vytvoření ukázkových dat
    if not create_sample_data():
        print("❌ Vytváření ukázkových dat selhalo")
        return 1
    
    print("\n🎉 Všechny operace byly úspěšně dokončeny!")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 