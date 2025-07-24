#!/usr/bin/env python3
"""
Skript pro vytvoření Lekce 0 - Vstupní test z obráběcích kapalin a servisu
30 otázek pro komplexní testování znalostí
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, engine
from app.models import Base, Lesson
import json

# Vytvoření databázových tabulek
Base.metadata.create_all(bind=engine)

# 30 otázek z obráběcích kapalin a servisu
ENTRY_TEST_QUESTIONS = [
    {
        "question": "Co je hlavní funkcí obráběcí kapaliny při soustružení?",
        "answer": "Chlazení nástroje a obrobku, mazání řezného procesu a odvod třísek",
        "category": "základy"
    },
    {
        "question": "Jaké jsou tři hlavní typy obráběcích kapalin?",
        "answer": "Řezné oleje, emulze a syntetické kapaliny",
        "category": "typy"
    },
    {
        "question": "Při jaké teplotě by měla pracovat obráběcí emulze?",
        "answer": "Optimálně mezi 18-25°C, maximálně do 35°C",
        "category": "provoz"
    },
    {
        "question": "Co způsobuje bakteriální kontaminace v obráběcí kapalině?",
        "answer": "Zápach, změnu barvy, snížení pH a korozi obrobků",
        "category": "kontaminace"
    },
    {
        "question": "Jak často se má kontrolovat koncentrace emulze?",
        "answer": "Denně pomocí refraktometru, optimální koncentrace 3-8%",
        "category": "kontrola"
    },
    {
        "question": "Jaké jsou příznaky opotřebení obráběcí kapaliny?",
        "answer": "Zápach, pěnění, změna barvy, snížení mazacích vlastností",
        "category": "diagnostika"
    },
    {
        "question": "Co je biocid a kdy se používá?",
        "answer": "Chemická látka proti bakteriím a plísním, používá se při kontaminaci",
        "category": "chemie"
    },
    {
        "question": "Jaká je optimální hodnota pH pro obráběcí emulzi?",
        "answer": "pH 8,5-9,5 pro zabránění koroze a bakteriálního růstu",
        "category": "chemie"
    },
    {
        "question": "Co způsobuje pěnění obráběcí kapaliny?",
        "answer": "Kontaminace oleji, vysoká rychlost cirkulace nebo špatné složení",
        "category": "problémy"
    },
    {
        "question": "Jak se správně připravuje emulze?",
        "answer": "Olej se přidává do vody (nikdy naopak) za stálého míchání",
        "category": "příprava"
    },
    {
        "question": "Jaké jsou bezpečnostní rizika při práci s obráběcími kapalinami?",
        "answer": "Dermatitida, alergické reakce, inhalace par a požární riziko",
        "category": "bezpečnost"
    },
    {
        "question": "Co je TDS a proč je důležité?",
        "answer": "Total Dissolved Solids - celkové rozpuštěné látky, indikátor kvality kapaliny",
        "category": "měření"
    },
    {
        "question": "Jak dlouho vydrží obráběcí kapalina při správné údržbě?",
        "answer": "Emulze 2-6 měsíců, řezné oleje až 2 roky při správné filtraci",
        "category": "životnost"
    },
    {
        "question": "Jaké filtrace se používají pro obráběcí kapaliny?",
        "answer": "Mechanická filtrace, magnetické separátory a centrifugy",
        "category": "filtrace"
    },
    {
        "question": "Co je koalescence při separaci oleje?",
        "answer": "Slučování malých kapek oleje ve větší pro lepší oddělení od vody",
        "category": "separace"
    },
    {
        "question": "Jaké jsou výhody syntetických obráběcích kapalin?",
        "answer": "Lepší chlazení, odolnost proti bakteriím, delší životnost",
        "category": "syntetické"
    },
    {
        "question": "Co způsobuje korozi na obráběcích strojích?",
        "answer": "Nízké pH, bakteriální kontaminace nebo vysoký obsah chloridů",
        "category": "koroze"
    },
    {
        "question": "Jak se měří koncentrace emulze refraktometrem?",
        "answer": "Kapka emulze na prizmu, odečtení hodnoty a přepočet podle faktoru",
        "category": "měření"
    },
    {
        "question": "Co je MWF a jaké má kategorie?",
        "answer": "Metalworking Fluids - dělí se na řezné, tvářecí a ochranné kapaliny",
        "category": "klasifikace"
    },
    {
        "question": "Jaké jsou environmentální aspekty likvidace obráběcích kapalin?",
        "answer": "Povinnost předúpravy, separace oleje a likvidace jako nebezpečný odpad",
        "category": "ekologie"
    },
    {
        "question": "Co je EP aditiva v obráběcích kapalinách?",
        "answer": "Extreme Pressure - přísady pro extrémní tlak při těžkém obrábění",
        "category": "aditiva"
    },
    {
        "question": "Jak se projevuje oxidace obráběcí kapaliny?",
        "answer": "Ztmavnutí, zvýšená viskozita, tvorba sedimentů a kyselý zápach",
        "category": "degradace"
    },
    {
        "question": "Jaké teploty způsobují degradaci obráběcích kapalin?",
        "answer": "Nad 60°C u emulzí, nad 80°C u řezných olejů",
        "category": "teplota"
    },
    {
        "question": "Co je demulgátor a k čemu slouží?",
        "answer": "Chemická látka pro rozrušení emulze při čištění odpadních vod",
        "category": "čištění"
    },
    {
        "question": "Jaké jsou příčiny rychlého úbytku obráběcí kapaliny?",
        "answer": "Odpařování, úniky, odnášení na třískách a nevhodné doplňování",
        "category": "úbytek"
    },
    {
        "question": "Co je důležité při skladování koncentrátů obráběcích kapalin?",
        "answer": "Teplota 5-40°C, ochrana před mrazem a přímým sluncem",
        "category": "skladování"
    },
    {
        "question": "Jaké jsou metody dezinfekce kontaminovaných systémů?",
        "answer": "Biocidy, UV záření, ozonizace nebo kompletní výměna kapaliny",
        "category": "dezinfekce"
    },
    {
        "question": "Co ovlivňuje výběr obráběcí kapaliny pro konkrétní operaci?",
        "answer": "Typ materiálu, druh obrábění, požadovaná kvalita povrchu a rychlost",
        "category": "výběr"
    },
    {
        "question": "Jaké jsou indikátory pro výměnu obráběcí kapaliny?",
        "answer": "Zápach, koroze, špatný povrch obrobků, nízké pH pod 8",
        "category": "výměna"
    },
    {
        "question": "Co je důležité při servisu obráběcích kapalin v létě?",
        "answer": "Častější kontrola teploty, bakteriální kontaminace a odpařování",
        "category": "servis"
    }
]

def create_entry_test():
    """Vytvoří Lekci 0 - vstupní test"""
    db = SessionLocal()
    try:
        # Zkontroluj, jestli už lekce 0 existuje
        existing_lesson = db.query(Lesson).filter_by(lesson_number=0).first()
        if existing_lesson:
            print("⚠️ Lekce 0 (vstupní test) už existuje!")
            return
        
        # Vytvoř novou lekci 0
        entry_test = Lesson(
            title="Lekce 0: Vstupní test - Obráběcí kapaliny a servis",
            language="cs",
            lesson_number=0,
            lesson_type="entry_test",
            required_score=90.0,
            script="""
Vítejte u vstupního testu z obráběcích kapalin a servisu!

Tento test obsahuje 30 komplexních otázek pokrývajících:
- Základy obráběcích kapalin
- Typy a vlastnosti kapalin  
- Kontrolu a údržbu
- Řešení problémů
- Bezpečnost a ekologii

Pro postup do Lekce 1 musíte dosáhnout alespoň 90% úspěšnosti.
Test můžete opakovat, pokud nedosáhnete požadovaného skóre.

Hodně štěstí!
            """,
            questions={
                "all": ENTRY_TEST_QUESTIONS,
                "current": ENTRY_TEST_QUESTIONS[0]["question"],
                "total_count": len(ENTRY_TEST_QUESTIONS)
            }
        )
        
        db.add(entry_test)
        db.commit()
        
        print("✅ Lekce 0 (vstupní test) byla úspěšně vytvořena!")
        print(f"📊 Počet otázek: {len(ENTRY_TEST_QUESTIONS)}")
        print(f"🎯 Požadované skóre: 90%")
        
    except Exception as e:
        print(f"❌ Chyba při vytváření lekce: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_entry_test() 