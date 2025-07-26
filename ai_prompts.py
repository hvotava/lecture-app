#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pokročilé AI prompty pro hlubší analýzu odpovědí a personalizovanou zpětnou vazbu
"""

def get_advanced_evaluation_prompt(question: str, correct_answer: str, user_answer: str, 
                                 question_category: str, question_difficulty: str,
                                 user_difficulty_score: float, failed_categories: list) -> str:
    """
    Generuje pokročilý prompt pro AI hodnocení s personalizovanou zpětnou vazbou.
    """
    
    # Přizpůsobení podle obtížnosti uživatele
    if user_difficulty_score < 30:
        focus_level = "základní pochopení konceptů"
        explanation_style = "velmi jednoduché vysvětlení s praktickými příklady"
    elif user_difficulty_score < 70:
        focus_level = "propojení konceptů a jejich aplikaci"
        explanation_style = "středně pokročilé vysvětlení s důrazem na souvislosti"
    else:
        focus_level = "hlubší analýzu a kritické myšlení"
        explanation_style = "pokročilé vysvětlení s technickými detaily"
    
    # Personalizace podle předchozích chyb
    personalization = ""
    if question_category in failed_categories:
        personalization = f"""
PERSONALIZACE: Student již chyboval v kategorii "{question_category}". 
Věnuj zvláštní pozornost vysvětlení základních principů této oblasti.
"""
    
    return f"""ÚKOL: Pokročilé vyhodnocení studentské odpovědi s personalizovanou zpětnou vazbou

KONTEXT OTÁZKY:
- Otázka: {question}
- Správná odpověď: {correct_answer}
- Kategorie: {question_category}
- Obtížnost: {question_difficulty}

STUDENTSKÁ ODPOVĚĎ: "{user_answer}"

PROFIL STUDENTA:
- Aktuální úroveň obtížnosti: {user_difficulty_score:.1f}/100
- Zaměření hodnocení: {focus_level}
- Styl vysvětlení: {explanation_style}
- Problémové oblasti: {', '.join(failed_categories) if failed_categories else 'žádné'}

{personalization}

KRITÉRIA HODNOCENÍ:

1. ÚROVNĚ POROZUMĚNÍ (hodnoť podle této škály):
   - MECHANICKÉ (0-39%): Student pouze opakuje bez porozumění
   - ZÁKLADNÍ (40-59%): Student rozumí "co", ale ne "proč"
   - FUNKČNÍ (60-79%): Student rozumí "co" i "proč", ale chybí mu aplikace
   - POKROČILÉ (80-89%): Student rozumí konceptu a umí ho aplikovat
   - EXPERTNÍ (90-100%): Student prokazuje hluboké porozumění a kritické myšlení

2. ANALÝZA CHYB ASR (rozpoznej možné chyby rozpoznávání řeči):
   - 'operátorem' = 'separátorem'
   - 'reparátor' = 'separátor'
   - 'chlazení' = 'hlazení'
   - 'mazání' = 'mazaní'

3. ROZPOZNÁVÁNÍ KOŘENŮ SLOV:
   - Akceptuj různé tvary stejného slova
   - Příklad: 'chlazení' = 'chlazen', 'chlazená', 'chlazený'

VÝSTUP:

1. SKÓRE (0-100%): Na základě úrovně porozumění výše

2. PERSONALIZOVANÁ ZPĚTNÁ VAZBA (2-3 věty):
   - Pokud je odpověď správná: Pochval konkrétní aspekty a rozšiř znalosti
   - Pokud chybí něco: Vysvětli PROČ je to důležité, ne jen CO chybí
   - Použij praktické příklady relevantní pro danou kategorii
   - Přizpůsob složitost vysvětlení úrovni studenta

PŘÍKLADY DOBRÉ ZPĚTNÉ VAZBY:
- Místo: "Chybí: separátor"
- Řekni: "Správně jste zmínil skimmer, který sbírá olej z povrchu. Pro hlubší čištění však potřebujeme separátor, který dokáže odstranit i jemnější nečistoty pomocí odstředivé síly."

- Místo: "Výborně, úplná odpověď!"
- Řekni: "Výborně! Správně jste propojil chlazení s mazáním. Toto pochopení je klíčové, protože obě funkce společně prodlužují životnost nástroje."

Formát odpovědi: [FEEDBACK] [SKÓRE: XX%]"""

def get_category_specific_hints() -> dict:
    """
    Vrací kategorie-specifické rady a vysvětlení.
    """
    return {
        "Základy": {
            "focus": "základní principy a funkce",
            "common_mistakes": ["záměna funkcí", "neúplné pochopení účelu"],
            "key_concepts": ["chlazení", "mazání", "odvod třísek"]
        },
        "Typy Kapalin": {
            "focus": "rozdíly mezi typy a jejich aplikace",
            "common_mistakes": ["záměna emulzí a olejů", "neznalost přípravy"],
            "key_concepts": ["emulze", "syntetické kapaliny", "řezné oleje"]
        },
        "Chemické Vlastnosti": {
            "focus": "pH, koncentrace a jejich vliv",
            "common_mistakes": ["neporozumění pH škále", "záměna koncentrace"],
            "key_concepts": ["pH", "koncentrace", "stabilita"]
        },
        "Filtrace a Čištění": {
            "focus": "metody čištění a údržby",
            "common_mistakes": ["záměna skimmeru a separátoru", "neznalost tramp oil"],
            "key_concepts": ["skimmer", "separátor", "tramp oil", "filtrace"]
        },
        "Řešení Problémů": {
            "focus": "diagnostika a řešení běžných problémů",
            "common_mistakes": ["nerozpoznání příčin", "nesprávné řešení"],
            "key_concepts": ["pěnění", "bakterie", "koroze", "zápach"]
        },
        "Bezpečnost a Ekologie": {
            "focus": "bezpečné zacházení a ekologická likvidace",
            "common_mistakes": ["nedostatečná ochrana", "nesprávná likvidace"],
            "key_concepts": ["ochranné pomůcky", "likvidace", "nebezpečný odpad"]
        },
        "Měření": {
            "focus": "měřicí přístroje a metody",
            "common_mistakes": ["záměna přístrojů", "nesprávná interpretace"],
            "key_concepts": ["refraktometr", "titrace", "testování kvality"]
        },
        "Údržba": {
            "focus": "pravidelná údržba a kontrola",
            "common_mistakes": ["nesprávná frekvence", "opomíjení kontrol"],
            "key_concepts": ["pravidelnost", "kontrola", "výměna"]
        },
        "Aditiva": {
            "focus": "účel a funkce přísad",
            "common_mistakes": ["neznalost účelu", "záměna typů"],
            "key_concepts": ["biocidy", "EP přísady", "stabilizátory"]
        },
        "Systémy": {
            "focus": "centrální vs. lokální systémy",
            "common_mistakes": ["neporozumění rozdílům", "nesprávná aplikace"],
            "key_concepts": ["centrální systém", "distribuce", "údržba"]
        }
    }

def get_difficulty_adjustment_rules() -> dict:
    """
    Pravidla pro úpravu obtížnosti na základě výkonu.
    """
    return {
        "score_adjustments": {
            "easy": {
                "correct": 2.5,  # Malý nárůst za správnou lehkou otázku
                "incorrect": 7.5  # Velký pokles za špatnou lehkou otázku
            },
            "medium": {
                "correct": 5.0,   # Střední nárůst
                "incorrect": 5.0  # Střední pokles
            },
            "hard": {
                "correct": 7.5,   # Velký nárůst za správnou těžkou otázku
                "incorrect": 2.5  # Malý pokles za špatnou těžkou otázku
            }
        },
        "category_weight": {
            # Váha kategorií při sledování chyb
            "Základy": 1.5,  # Chyby v základech jsou závažnější
            "Bezpečnost a Ekologie": 1.3,  # Bezpečnost je důležitá
            "Chemické Vlastnosti": 1.2,  # Chemie je složitější
            "default": 1.0
        }
    } 