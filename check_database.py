#!/usr/bin/env python3
"""
Script pro kontrolu databáze a nalezení platných attempt_id.
"""

import os
import sys
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Přidání cesty k aplikaci
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import modelů
from app.app import create_app
from app.models import Attempt, Answer, User, Lesson

# Nastavení logování
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_database():
    """Kontrola databáze a nalezení platných attempt_id."""
    
    print("🔍 Kontrola databáze:")
    print("=" * 50)
    
    try:
        # Vytvoření aplikace
        app = create_app()
        
        with app.app_context():
            # Kontrola uživatelů
            print("\n👥 Uživatelé:")
            users = User.query.all()
            for user in users:
                print(f"   ID: {user.id}, Jméno: {user.name}")
            
            # Kontrola lekcí
            print("\n📚 Lekce:")
            lessons = Lesson.query.all()
            for lesson in lessons:
                print(f"   ID: {lesson.id}, Název: {lesson.title}")
                # Kontrola otázek v lekci
                if hasattr(lesson, 'questions') and lesson.questions:
                    if isinstance(lesson.questions, dict) and 'all' in lesson.questions:
                        print(f"      Otázky: {len(lesson.questions['all'])}")
                    else:
                        print(f"      Otázky: {lesson.questions}")
            
            # Kontrola pokusů
            print("\n🎯 Pokusy:")
            attempts = Attempt.query.order_by(Attempt.id.desc()).limit(10).all()
            for attempt in attempts:
                print(f"   ID: {attempt.id}, Uživatel: {attempt.user_id}, Lekce: {attempt.lesson_id}, Status: {attempt.status}")
            
            # Kontrola odpovědí pro nejnovější pokusy
            print("\n💬 Odpovědi pro nejnovější pokusy:")
            for attempt in attempts[:5]:  # Kontrola prvních 5 pokusů
                answers = Answer.query.filter_by(attempt_id=attempt.id).all()
                print(f"   Pokus {attempt.id}: {len(answers)} odpovědí")
                if answers:
                    for i, answer in enumerate(answers[:2]):  # Zobrazit první 2 odpovědi
                        print(f"     {i+1}. Otázka: {answer.question_text[:50]}...")
                        print(f"        Odpověď: {answer.user_answer[:30]}...")
            
            # Najít pokus s lekcí, která má otázky
            print("\n🎯 Hledání pokusu s lekcí obsahující otázky:")
            for attempt in attempts:
                lesson = Lesson.query.get(attempt.lesson_id)
                if lesson and lesson.questions:
                    if isinstance(lesson.questions, dict) and 'all' in lesson.questions and lesson.questions['all']:
                        print(f"   ✅ Pokus {attempt.id} má lekci s {len(lesson.questions['all'])} otázkami")
                        print(f"      Uživatel: {attempt.user_id}, Lekce: {attempt.lesson_id}")
                        return attempt.id
            
            print("   ❌ Žádný pokus s lekcí obsahující otázky nenalezen")
            
            # Pokud nejsou otázky, zkusíme vytvořit nový pokus
            print("\n🆕 Vytváření nového pokusu:")
            if users and lessons:
                user = users[0]
                # Najdi lekci s otázkami
                lesson_with_questions = None
                for lesson in lessons:
                    if lesson.questions and isinstance(lesson.questions, dict) and 'all' in lesson.questions and lesson.questions['all']:
                        lesson_with_questions = lesson
                        break
                
                if lesson_with_questions:
                    new_attempt = Attempt(
                        user_id=user.id,
                        lesson_id=lesson_with_questions.id,
                        status='in_progress'
                    )
                    
                    from app import db
                    db.session.add(new_attempt)
                    db.session.commit()
                    
                    print(f"   ✅ Vytvořen nový pokus ID: {new_attempt.id}")
                    print(f"      S lekcí obsahující {len(lesson_with_questions.questions['all'])} otázek")
                    return new_attempt.id
                else:
                    print("   ❌ Žádná lekce neobsahuje otázky")
                    return None
            else:
                print("   ❌ Nejsou dostupní uživatelé nebo lekce")
                return None
                
    except Exception as e:
        print(f"❌ Chyba při kontrole databáze: {str(e)}")
        logger.exception("Chyba při kontrole databáze")
        return None

if __name__ == "__main__":
    attempt_id = check_database()
    if attempt_id:
        print(f"\n🎉 Doporučený attempt_id pro testování: {attempt_id}")
    else:
        print("\n❌ Nepodařilo se najít nebo vytvořit platný attempt_id") 