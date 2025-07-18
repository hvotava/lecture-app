#!/usr/bin/env python3
"""
Opraví pole questions ve všech lekcích na správný JSON formát.
"""

import os
import json
from app.models import Lesson
from app.database import SessionLocal

def fix_all_lessons():
    session = SessionLocal()
    lessons = session.query(Lesson).all()
    fixed = 0
    for lesson in lessons:
        q = lesson.questions
        changed = False
        # Pokud je to string, pokus se převést na dict
        if isinstance(q, str):
            try:
                q_json = json.loads(q)
                lesson.questions = q_json
                changed = True
            except Exception:
                # Pokud to není JSON, zabal do správné struktury
                lesson.questions = {
                    "all": [
                        {"question": q, "answer": "Správná odpověď na otázku: " + q}
                    ],
                    "current": q
                }
                changed = True
        # Pokud je to dict, ale chybí 'all', oprav
        elif isinstance(q, dict):
            if 'all' not in q or not isinstance(q['all'], list) or not q['all']:
                question_text = q.get('current', 'Kolik je hodin?')
                lesson.questions = {
                    "all": [
                        {"question": question_text, "answer": "Správná odpověď na otázku: " + question_text}
                    ],
                    "current": question_text
                }
                changed = True
        if changed:
            print(f"Opravuji lekci: {lesson.title}")
            fixed += 1
    session.commit()
    session.close()
    print(f"Opraveno {fixed} lekcí.")

if __name__ == "__main__":
    fix_all_lessons() 