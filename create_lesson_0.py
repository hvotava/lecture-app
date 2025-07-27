#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skript pro vytvoření Lekce 0: Vstupní test - Obráběcí kapaliny a servis
30 základních otázek z oboru
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models import Lesson, Badge
import json

def create_badges():
    """Vytvoří základní odznaky, pokud neexistují."""
    session = SessionLocal()
    try:
        badges_to_create = [
            {"name": "Mistr Filtrace", "category": "Filtrace a Čištění", "description": "Za vynikající znalosti v oblasti filtrace a čištění kapalin."},
            {"name": "pH Šampion", "category": "Chemické Vlastnosti", "description": "Za perfektní přehled o pH a jeho vlivu."},
            {"name": "Expert na Emulze", "category": "Typy Kapalin", "description": "Za hluboké porozumění emulzím a jejich přípravě."},
            {"name": "Bezpečnostní Profík", "category": "Bezpečnost a Ekologie", "description": "Za znalosti bezpečnostních postupů a ekologické likvidace."}
        ]
        
        for badge_data in badges_to_create:
            existing_badge = session.query(Badge).filter_by(name=badge_data["name"]).first()
            if not existing_badge:
                badge = Badge(**badge_data)
                session.add(badge)
                print(f"✅ Vytvořen odznak: {badge_data['name']}")
        
        session.commit()
    except Exception as e:
        print(f"❌ Chyba při vytváření odznaků: {e}")
        session.rollback()
    finally:
        session.close()

def create_lesson_0():
    """Vytvoří Lekci 0 s 30 základními otázkami"""
    
    questions = [
        {
            "question": "K čemu slouží obráběcí kapaliny při obrábění kovů?",
            "correct_answer": "K chlazení, mazání a odvodu třísek",
            "keywords": ["chlazení", "mazání", "třísky", "odvod"],
            "difficulty": "easy",
            "category": "Základy",
            "hint": "Zamyslete se nad třemi hlavními funkcemi, které kapalina plní u řezného nástroje."
        },
        {
            "question": "Jaké jsou hlavní typy obráběcích kapalin?",
            "correct_answer": "Vodní roztoky, oleje a emulze",
            "keywords": ["vodní", "oleje", "emulze", "typy"],
            "difficulty": "easy",
            "category": "Typy Kapalin",
            "hint": "Existují tři základní skupiny podle složení."
        },
        {
            "question": "Proč je důležité pravidelně kontrolovat koncentraci emulze?",
            "correct_answer": "Pro zajištění správné funkce a předcházení bakteriálnímu růstu",
            "keywords": ["koncentrace", "funkce", "bakterie", "kontrola"],
            "difficulty": "medium",
            "category": "Údržba",
            "hint": "Správná koncentrace ovlivňuje jak výkon, tak životnost kapaliny."
        },
        {
            "question": "Jak se měří koncentrací obráběcí emulze?",
            "correct_answer": "Refraktometrem nebo titrací",
            "keywords": ["refraktometr", "titrace"],
            "difficulty": "easy",
            "category": "Měření",
            "hint": "Existují dva hlavní nástroje pro toto měření, jeden optický a druhý chemický."
        },
        {
            "question": "Jaká je optimální koncentrace pro většinu obráběcích emulzí?",
            "correct_answer": "3-8 procent",
            "keywords": ["3", "8", "procent", "koncentrace"],
            "difficulty": "medium",
            "category": "Chemické Vlastnosti",
            "hint": "Jedná se o nízké procentuální rozmezí."
        },
        {
            "question": "Co způsobuje pěnění obráběcích kapalin?",
            "correct_answer": "Vysoká rychlost oběhu, kontaminace nebo špatná koncentrace",
            "keywords": ["pěnění", "rychlost", "kontaminace", "koncentrace"],
            "difficulty": "medium",
            "category": "Řešení Problémů",
            "hint": "Příčiny mohou být mechanické i chemické."
        },
        {
            "question": "Jak často se má měnit obráběcí kapalina?",
            "correct_answer": "Podle stavu kapaliny, obvykle každé 2-6 měsíců",
            "keywords": ["měnit", "stav", "měsíc", "pravidelně"],
            "difficulty": "medium",
            "category": "Údržba",
            "hint": "Neexistuje pevný interval, záleží na opotřebení."
        },
        {
            "question": "Jaké jsou příznaky zkažené obráběcí kapaliny?",
            "correct_answer": "Zápach, změna barvy, pěnění nebo růst bakterií",
            "keywords": ["zápach", "barva", "pěnění", "bakterie"],
            "difficulty": "easy",
            "category": "Řešení Problémů",
            "hint": "Lze to poznat smysly - čichem a zrakem."
        },
        {
            "question": "Co je to pH obráběcí kapaliny a jaká má být hodnota?",
            "correct_answer": "Míra kyselosti, optimálně 8,5-9,5",
            "keywords": ["pH", "kyselost", "8,5", "9,5"],
            "difficulty": "medium",
            "category": "Chemické Vlastnosti",
            "hint": "Hodnota by měla být mírně zásaditá."
        },
        {
            "question": "Proč je důležité udržovat správné pH?",
            "correct_answer": "Zabraňuje korozi a růstu bakterií",
            "keywords": ["koroze", "bakterie", "ochrana"],
            "difficulty": "medium",
            "category": "Chemické Vlastnosti",
            "hint": "Správné pH chrání stroj i kapalinu samotnou."
        },
        {
            "question": "Jak se připravuje emulze z koncentrátu?",
            "correct_answer": "Koncentrát se přidává do vody, nikdy naopak",
            "keywords": ["koncentrát", "voda", "příprava", "pořadí"],
            "difficulty": "hard",
            "category": "Typy Kapalin",
            "hint": "Existuje zlaté pravidlo pro pořadí míchání."
        },
        {
            "question": "Jaká je funkce biocidů v obráběcích kapalinách?",
            "correct_answer": "Zabíjejí bakterie a houby",
            "keywords": ["biocidy", "bakterie", "houby", "dezinfekce"],
            "difficulty": "hard",
            "category": "Aditiva",
            "hint": "Název napovídá, co tyto látky ničí."
        },
        {
            "question": "Co způsobuje korozi na obráběcích strojích?",
            "correct_answer": "Nízké pH, kontaminace nebo stará kapalina",
            "keywords": ["koroze", "pH", "kontaminace", "stará"],
            "difficulty": "medium",
            "category": "Řešení Problémů",
            "hint": "Koroze souvisí s chemickým stavem kapaliny."
        },
        {
            "question": "Jak se testuje kvalita obráběcí kapaliny?",
            "correct_answer": "Měření pH, koncentrace, čistoty a mikrobiologie",
            "keywords": ["pH", "koncentrace", "čistota", "mikrobiologie"],
            "difficulty": "medium",
            "category": "Měření",
            "hint": "Sleduje se několik klíčových parametrů."
        },
        {
            "question": "Jaké jsou bezpečnostní opatření při práci s obráběcími kapalinami?",
            "correct_answer": "Ochranné rukavice, brýle a větrání",
            "keywords": ["rukavice", "brýle", "větrání", "ochrana"],
            "difficulty": "easy",
            "category": "Bezpečnost a Ekologie",
            "hint": "Myslete na ochranu kůže, očí a dýchacích cest."
        },
        {
            "question": "Co je filtrace obráběcích kapalin?",
            "correct_answer": "Odstranění nečistot a částic z kapaliny",
            "keywords": ["filtrace", "nečistoty", "částice", "čištění"],
            "difficulty": "easy",
            "category": "Filtrace a Čištění",
            "hint": "Cílem je udržet kapalinu co nejčistší."
        },
        {
            "question": "Proč se obráběcí kapaliny recyklují?",
            "correct_answer": "Kvůli úspoře nákladů a ochraně životního prostředí",
            "keywords": ["recyklace", "úspora", "prostředí", "náklady"],
            "difficulty": "medium",
            "category": "Bezpečnost a Ekologie",
            "hint": "Důvody jsou ekonomické i ekologické."
        },
        {
            "question": "Jaká je role aditiv v obráběcích kapalinách?",
            "correct_answer": "Zlepšují vlastnosti jako mazání, ochranu před korozí",
            "keywords": ["aditiva", "mazání", "koroze", "vlastnosti"],
            "difficulty": "medium",
            "category": "Aditiva",
            "hint": "Jsou to přísady, které vylepšují základní funkci."
        },
        {
            "question": "Co je to EP přísada?",
            "correct_answer": "Extreme Pressure - přísada pro vysoké tlaky",
            "keywords": ["EP", "extreme", "pressure", "tlak"],
            "difficulty": "hard",
            "category": "Aditiva",
            "hint": "Zkratka pochází z angličtiny."
        },
        {
            "question": "Jak se likvidují použité obráběcí kapaliny?",
            "correct_answer": "Jako nebezpečný odpad ve specializovaných firmách",
            "keywords": ["likvidace", "nebezpečný", "odpad", "specializované"],
            "difficulty": "medium",
            "category": "Bezpečnost a Ekologie",
            "hint": "Nelze je vylít do běžné kanalizace."
        },
        {
            "question": "Co způsobuje bakteriální růst v obráběcích kapalinách?",
            "correct_answer": "Vysoká teplota, nízké pH nebo kontaminace",
            "keywords": ["bakterie", "teplota", "pH", "kontaminace"],
            "difficulty": "medium",
            "category": "Řešení Problémů",
            "hint": "Jsou to podobné podmínky, které škodí i stroji."
        },
        {
            "question": "Jaké jsou výhody syntetických obráběcích kapalin?",
            "correct_answer": "Delší životnost, lepší čistota a stabilita",
            "keywords": ["syntetické", "životnost", "čistota", "stabilita"],
            "difficulty": "medium",
            "category": "Typy Kapalin",
            "hint": "Jsou modernější alternativou k emulzím."
        },
        {
            "question": "Co je to mazací film?",
            "correct_answer": "Tenká vrstva kapaliny mezi nástrojem a obrobkem",
            "keywords": ["mazací", "film", "vrstva", "nástroj"],
            "difficulty": "easy",
            "category": "Základy",
            "hint": "Je klíčový pro snížení tření."
        },
        {
            "question": "Proč je důležité chlazení při obrábění?",
            "correct_answer": "Zabraňuje přehřátí nástroje a obrobku",
            "keywords": ["chlazení", "přehřátí", "nástroj", "obrobek"],
            "difficulty": "easy",
            "category": "Základy",
            "hint": "Vysoké teploty mohou poškodit materiál i nástroj."
        },
        {
            "question": "Co je to tramp oil?",
            "correct_answer": "Cizí olej kontaminující obráběcí kapalinu",
            "keywords": ["tramp", "oil", "cizí", "kontaminace"],
            "difficulty": "easy",
            "category": "Filtrace a Čištění",
            "hint": "Je to 'zatoulaný' olej, který v kapalině nemá co dělat."
        },
        {
            "question": "Jak se odstraňuje tramp oil?",
            "correct_answer": "Skimmerem nebo separátorem oleje",
            "keywords": ["skimmer", "separátor", "odstranění"],
            "difficulty": "medium",
            "category": "Filtrace a Čištění",
            "hint": "Existují mechanická zařízení, která sbírají olej z hladiny."
        },
        {
            "question": "Jaká je optimální teplota obráběcích kapalin?",
            "correct_answer": "20-35 stupňů Celsia",
            "keywords": ["teplota", "20", "35", "Celsius"],
            "difficulty": "medium",
            "category": "Chemické Vlastnosti",
            "hint": "Teplota by měla být podobná pokojové teplotě."
        },
        {
            "question": "Co je to centrální systém obráběcích kapalin?",
            "correct_answer": "Systém zásobující více strojů z jednoho zdroje",
            "keywords": ["centrální", "systém", "více", "strojů"],
            "difficulty": "hard",
            "category": "Systémy",
            "hint": "Je to opak lokálního systému pro každý stroj."
        },
        {
            "question": "Proč se kontroluje tvrdost vody pro přípravu emulzí?",
            "correct_answer": "Tvrdá voda může způsobit nestabilitu emulze",
            "keywords": ["tvrdost", "voda", "nestabilita", "emulze"],
            "difficulty": "hard",
            "category": "Chemické Vlastnosti",
            "hint": "Souvisí to s minerály obsaženými ve vodě."
        },
        {
            "question": "Co jsou to MWF (Metalworking Fluids)?",
            "correct_answer": "Obecný název pro všechny obráběcí kapaliny",
            "keywords": ["MWF", "metalworking", "fluids", "obecný"],
            "difficulty": "easy",
            "category": "Základy",
            "hint": "Je to anglická zkratka pro celý obor."
        }
    ]
    
    # Vytvoření lekce
    lesson_data = {
        "title": "Lekce 0: Vstupní test - Obráběcí kapaliny a servis",
        "description": "Základní test znalostí z oboru obráběcích kapalin a jejich servisu. Nutné dosáhnout 90% úspěšnosti pro postup do Lekce 1.",
        "questions": questions,
        "level": "entry_test"
    }
    
    session = SessionLocal()
    try:
        # Zkontroluj, jestli už Lekce 0 neexistuje
        existing_lesson = session.query(Lesson).filter(Lesson.title.contains("Lekce 0")).first()
        if existing_lesson:
            print("❌ Lekce 0 již existuje!")
            print(f"   ID: {existing_lesson.id}")
            print(f"   Název: {existing_lesson.title}")
            return existing_lesson.id
        
        # Vytvoř novou lekci
        lesson = Lesson(
            title=lesson_data["title"],
            description=lesson_data["description"],
            questions=lesson_data["questions"],
            level=lesson_data["level"]
        )
        
        session.add(lesson)
        session.commit()
        
        print("✅ Lekce 0 úspěšně vytvořena!")
        print(f"   ID: {lesson.id}")
        print(f"   Název: {lesson.title}")
        print(f"   Počet otázek: {len(lesson_data['questions'])}")
        print(f"   Úroveň: {lesson.level}")
        
        return lesson.id
        
    except Exception as e:
        print(f"❌ Chyba při vytváření Lekce 0: {e}")
        session.rollback()
        return None
    finally:
        session.close()

if __name__ == "__main__":
    print("🚀 Vytváření Lekce 0 a Odznaků...")
    print("=" * 50)
    
    create_badges()
    lesson_id = create_lesson_0()
    
    if lesson_id:
        print("=" * 50)
        print("🎯 HOTOVO! Lekce 0 je připravena k použití.")
        print(f"📝 30 základních otázek z obráběcích kapalin")
        print(f"🎓 Úroveň: Vstupní test")
        print(f"✅ ID lekce: {lesson_id}")
    else:
        print("=" * 50)
        print("❌ CHYBA! Lekce 0 nebyla vytvořena.") 