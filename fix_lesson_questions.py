#!/usr/bin/env python3
"""
Script pro opravu struktury otázek v lekci.
"""

import os
import sys
import logging
import json

# Přidání cesty k aplikaci
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import modelů
from app.app import create_app
from app.models import Lesson

# Nastavení logování
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_lesson_questions():
    """Opraví strukturu otázek v lekci."""
    
    print("🔧 Oprava struktury otázek v lekci:")
    print("=" * 50)
    
    try:
        # Vytvoření aplikace
        app = create_app()
        
        with app.app_context():
            # Najdi lekci
            lesson = Lesson.query.first()
            if not lesson:
                print("❌ Žádná lekce nenalezena")
                return False
            
            print(f"📚 Lekce: {lesson.title}")
            print(f"📝 Aktuální otázky: {lesson.questions}")
            print(f"📝 Typ otázek: {type(lesson.questions)}")
            
            # Pokud jsou otázky string, převeď na správnou strukturu
            if isinstance(lesson.questions, str):
                print("🔄 Převádím string na JSON strukturu...")
                
                # Vytvoř správnou strukturu
                questions_structure = {
                    "all": [
                        {
                            "question": lesson.questions,
                            "answer": "Správná odpověď na otázku: " + lesson.questions
                        }
                    ],
                    "current": lesson.questions
                }
                
                lesson.questions = questions_structure
                
                from app import db
                db.session.commit()
                
                print("✅ Struktura otázek byla opravena")
                print(f"📝 Nová struktura: {json.dumps(lesson.questions, ensure_ascii=False, indent=2)}")
                return True
                
            elif isinstance(lesson.questions, dict):
                if 'all' not in lesson.questions or not lesson.questions['all']:
                    print("🔄 Opravuji prázdnou strukturu...")
                    
                    # Pokud existuje 'current', použij ji
                    if 'current' in lesson.questions and lesson.questions['current']:
                        question_text = lesson.questions['current']
                    else:
                        question_text = "Kolik je hodin?"
                    
                    lesson.questions = {
                        "all": [
                            {
                                "question": question_text,
                                "answer": "Správná odpověď na otázku: " + question_text
                            }
                        ],
                        "current": question_text
                    }
                    
                    from app import db
                    db.session.commit()
                    
                    print("✅ Prázdná struktura byla opravena")
                    print(f"📝 Nová struktura: {json.dumps(lesson.questions, ensure_ascii=False, indent=2)}")
                    return True
                else:
                    print("✅ Struktura otázek je již správná")
                    return True
            else:
                print(f"❌ Neznámý typ otázek: {type(lesson.questions)}")
                return False
                
    except Exception as e:
        print(f"❌ Chyba při opravě otázek: {str(e)}")
        logger.exception("Chyba při opravě otázek")
        return False

if __name__ == "__main__":
    success = fix_lesson_questions()
    if success:
        print("\n🎉 Oprava dokončena úspěšně!")
    else:
        print("\n❌ Oprava se nezdařila") 