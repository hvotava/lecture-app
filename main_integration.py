#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrační soubor s novými funkcemi pro main.py
Tento soubor obsahuje všechny funkce, které je třeba integrovat do hlavního souboru.
"""

# Import nových modulů
from ai_prompts import get_advanced_evaluation_prompt, get_difficulty_adjustment_rules
from badge_system import BadgeSystem, VoiceCommandHandler, NotificationService
from admin_dashboard import DashboardStats
from sqlalchemy.orm.attributes import flag_modified
import logging

logger = logging.getLogger(__name__)

# ===== NOVÁ FUNKCE: Adaptivní výběr otázek =====
def get_next_adaptive_question(test_session) -> Optional[dict]:
    """
    Vybere další otázku na základě adaptivní obtížnosti.
    """
    if isinstance(test_session, dict):
        answered_indices = {a['question_index'] for a in test_session.get('answers', [])}
        all_questions = test_session.get('questions_data', [])
        difficulty_score = test_session.get('difficulty_score', 50.0)
    else: # Je to TestSession objekt
        answered_indices = {a['question_index'] for a in (test_session.answers or [])}
        all_questions = test_session.questions_data
        difficulty_score = getattr(test_session, 'difficulty_score', 50.0) or 50.0

    unanswered_questions = [
        (idx, q) for idx, q in enumerate(all_questions) if idx not in answered_indices
    ]

    if not unanswered_questions:
        return None

    difficulty_map = {"easy": 25, "medium": 50, "hard": 75}
    
    best_question = None
    min_diff = float('inf')

    for idx, q_data in unanswered_questions:
        q_difficulty = difficulty_map.get(q_data.get("difficulty", "medium"), 50)
        diff = abs(q_difficulty - difficulty_score)
        
        if diff < min_diff:
            min_diff = diff
            best_question = q_data.copy()
            best_question['original_index'] = idx 
            
    return best_question

# ===== NOVÁ FUNKCE: Pokročilé ukládání odpovědí =====
def save_answer_and_advance_v2(test_session_id: int, user_answer: str, score: float, 
                               feedback: str, question_index: int):
    """
    Pokročilá verze ukládání odpovědí s adaptivní logikou a sledováním chyb.
    """
    session = SessionLocal()
    try:
        test_session = session.query(TestSession).get(test_session_id)
        if not test_session:
            return None
        
        # Získání otázky podle indexu
        current_question = test_session.questions_data[question_index]
        
        # Aktualizace skóre obtížnosti podle nových pravidel
        rules = get_difficulty_adjustment_rules()
        q_difficulty = current_question.get("difficulty", "medium")
        
        if score >= 80:
            adjustment = rules["score_adjustments"][q_difficulty]["correct"]
            current_difficulty = getattr(test_session, 'difficulty_score', 50.0) or 50.0
            test_session.difficulty_score = current_difficulty + adjustment
        else:
            adjustment = rules["score_adjustments"][q_difficulty]["incorrect"]
            current_difficulty = getattr(test_session, 'difficulty_score', 50.0) or 50.0
            test_session.difficulty_score = current_difficulty - adjustment
            
            # Sledování chybných kategorií s váhami
            category = current_question.get("category", "Neznámá")
            category_weight = rules["category_weight"].get(category, rules["category_weight"]["default"])
            
            if not test_session.failed_categories:
                test_session.failed_categories = []
            
            # Přidej kategorii s váhou (důležitější kategorie se přidají vícekrát)
            for _ in range(int(category_weight)):
                if category not in test_session.failed_categories:
                    test_session.failed_categories.append(category)
                    
            flag_modified(test_session, "failed_categories")

        # Omezení skóre v rozmezí 0-100
        current_difficulty = getattr(test_session, 'difficulty_score', 50.0) or 50.0
        test_session.difficulty_score = max(0, min(100, current_difficulty))
        final_difficulty = getattr(test_session, 'difficulty_score', 50.0) or 50.0
        logger.info(f"🧠 Adaptivní skóre: {final_difficulty:.2f} (Δ{adjustment:+.2f})")

        # Uložení odpovědi s rozšířenými daty
        answer_data = {
            "question": current_question.get("question", ""),
            "correct_answer": current_question.get("correct_answer", ""),
            "user_answer": user_answer,
            "score": score,
            "feedback": feedback,
            "question_index": question_index,
            "category": current_question.get("category", "Neznámá"),
            "difficulty": current_question.get("difficulty", "medium"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Aktualizace seznamů
        if not test_session.answers:
            test_session.answers = []
        if not test_session.scores:
            test_session.scores = []
            
        test_session.answers.append(answer_data)
        test_session.scores.append(score)
        
        # Přepočet průměrného skóre
        test_session.current_score = sum(test_session.scores) / len(test_session.scores)
        
        # Kontrola dokončení
        if len(test_session.answers) >= test_session.total_questions:
            test_session.is_completed = True
            test_session.completed_at = datetime.utcnow()
            
            # Logování dokončení s pokročilými statistikami
            logger.info(f"""
🏁 === POKROČILÝ TEST DOKONČEN ===
🆔 Session ID: {test_session_id}
📊 Finální skóre: {test_session.current_score:.1f}%
🧠 Finální obtížnost: {test_session.difficulty_score:.1f}
❌ Problémové oblasti: {test_session.failed_categories}
📈 Rozložení skóre: {test_session.scores}
⏱️ Dokončeno: {test_session.completed_at}
======================================""")
        
        # Oznámení SQLAlchemy o změnách
        flag_modified(test_session, 'answers')
        flag_modified(test_session, 'scores')
        session.commit()
        
        # Vrácení dat
        return {
            'id': test_session.id,
            'current_question_index': test_session.current_question_index,
            'total_questions': test_session.total_questions,
            'questions_data': test_session.questions_data,
            'answers': test_session.answers,
            'scores': test_session.scores,
            'current_score': test_session.current_score,
            'is_completed': test_session.is_completed,
            'completed_at': test_session.completed_at,
            'failed_categories': test_session.failed_categories,
            'difficulty_score': getattr(test_session, 'difficulty_score', 50.0)
        }
            
    finally:
        session.close()
    
    return None

# ===== NOVÁ FUNKCE: Pokročilé zpracování vstupního testu =====
async def handle_entry_test_v2(session, current_user, speech_result, response, client, attempt_id, confidence_float):
    """
    Pokročilá verze zpracování vstupního testu s všemi novými funkcemi.
    """
    logger.info("🎯 Zpracovávám pokročilý vstupní test...")
    
    # Detekce hlasových příkazů
    if speech_result:
        command = VoiceCommandHandler.detect_command(speech_result)
        if command == 'help':
            # Získej aktuální otázku a vrať nápovědu
            test_session = get_or_create_test_session(current_user.id, target_lesson.id, attempt_id)
            current_question = test_session.questions_data[test_session.current_question_index]
            hint = VoiceCommandHandler.get_hint_for_question(current_question)
            response.say(hint, language="cs-CZ")
            return True
        elif command == 'skip':
            # Přeskoč otázku (uloží jako 0% skóre)
            # ... logika pro přeskočení
            pass
    
    # Najdi Lekci 0
    target_lesson = session.query(Lesson).filter(Lesson.lesson_number == 0).first()
    if not target_lesson:
        target_lesson = session.query(Lesson).filter(Lesson.title.contains("Lekce 0")).first()
    
    if not target_lesson:
        response.say("Vstupní test nebyl nalezen.", language="cs-CZ")
        return False
    
    # Získej nebo vytvoř test session
    test_session = get_or_create_test_session(current_user.id, target_lesson.id, attempt_id)
    
    # Pokud je test dokončen, zkontroluj odznaky
    if test_session.is_completed:
        badge_system = BadgeSystem()
        test_data = {
            'answers': test_session.answers,
            'current_score': test_session.current_score,
            'failed_categories': test_session.failed_categories
        }
        awarded_badges = badge_system.check_and_award_badges(current_user.id, test_data)
        
        if awarded_badges:
            badge_names = [b['name'] for b in awarded_badges]
            response.say(f"Test již dokončen. Navíc jste získali odznaky: {', '.join(badge_names)}!", language="cs-CZ")
        else:
            response.say("Test již dokončen.", language="cs-CZ")
        return False
    
    # Logika pro první otázku vs. zpracování odpovědi
    answered_indices = {a['question_index'] for a in (test_session.answers or [])}
    
    if not speech_result:
        # Pokládáme otázku
        next_question = get_next_adaptive_question(test_session)
        if next_question:
            test_session.current_question_index = next_question['original_index']
            session.commit()
            
            difficulty_indicator = {"easy": "⭐", "medium": "⭐⭐", "hard": "⭐⭐⭐"}.get(
                next_question.get('difficulty', 'medium'), "⭐⭐"
            )
            
            response.say(f"Otázka {difficulty_indicator}: {next_question.get('question', '')}", 
                        language="cs-CZ")
        else:
            response.say("Všechny otázky zodpovězeny.", language="cs-CZ")
        return True

    # Zpracování odpovědi s pokročilým AI promptem
    last_question_index = test_session.current_question_index
    current_question = test_session.questions_data[last_question_index]
    
    try:
        # Pokročilý AI prompt
        advanced_prompt = get_advanced_evaluation_prompt(
            question=current_question.get('question', ''),
            correct_answer=current_question.get('correct_answer', ''),
            user_answer=speech_result,
            question_category=current_question.get('category', 'Neznámá'),
            question_difficulty=current_question.get('difficulty', 'medium'),
            user_difficulty_score=getattr(test_session, 'difficulty_score', 50.0) or 50.0,
            failed_categories=test_session.failed_categories or []
        )
        
        # AI vyhodnocení
        gpt_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": advanced_prompt}],
            max_tokens=200,
            temperature=0.3
        )
        
        ai_answer = gpt_response.choices[0].message.content
        
        # Extrakce skóre
        import re
        score_match = re.search(r'\[SKÓRE:\s*(\d+)%?\]', ai_answer, re.IGNORECASE)
        current_score = int(score_match.group(1)) if score_match else 0
        
        clean_feedback = re.sub(r'\[SKÓRE:\s*\d+%?\]', '', ai_answer, flags=re.IGNORECASE).strip()
        
        logger.info(f"🤖 Pokročilé AI hodnocení: {current_score}% - {clean_feedback}")
        
        # Uložení s pokročilou logikou
        updated_session = save_answer_and_advance_v2(
            test_session.id,
            speech_result,
            float(current_score),
            clean_feedback,
            last_question_index
        )
        
        if updated_session and updated_session.get('is_completed'):
            # Test dokončen - zkontroluj odznaky a pošli souhrn
            badge_system = BadgeSystem()
            awarded_badges = badge_system.check_and_award_badges(current_user.id, updated_session)
            
            # Pošli souhrn
            notification_service = NotificationService()
            notification_service.send_test_summary(current_user, updated_session, awarded_badges)
            
            # Finální zpráva s odznaky
            final_score = updated_session.get('current_score', 0)
            failed_categories = updated_session.get('failed_categories', [])
            
            message_parts = [clean_feedback]
            message_parts.append(f"Test dokončen! Skóre: {final_score:.1f}%.")
            
            if awarded_badges:
                badge_names = [b['name'] for b in awarded_badges]
                message_parts.append(f"🏅 Získali jste odznaky: {', '.join(badge_names)}!")
            
            if failed_categories:
                unique_categories = list(set(failed_categories))
                message_parts.append(f"📚 Doporučujeme studium: {', '.join(unique_categories)}.")
            
            if final_score >= 90:
                current_user.current_lesson_level = 1
                session.commit()
                message_parts.append("Gratulujeme, postupujete do Lekce 1!")
            else:
                message_parts.append("Pro postup potřebujete 90%. Můžete zkusit znovu!")
            
            response.say(" ".join(message_parts), language="cs-CZ", rate="0.9")
            return False
        else:
            # Další adaptivní otázka
            next_question = get_next_adaptive_question(updated_session)
            if next_question:
                # Aktualizace indexu
                ts = session.query(TestSession).get(updated_session['id'])
                ts.current_question_index = next_question['original_index']
                session.commit()
                
                difficulty_indicator = {"easy": "⭐", "medium": "⭐⭐", "hard": "⭐⭐⭐"}.get(
                    next_question.get('difficulty', 'medium'), "⭐⭐"
                )
                
                next_text = f"{clean_feedback} Další otázka {difficulty_indicator}: {next_question.get('question', '')}"
                # Použij přirozenější pauzy - import funkce z main.py
                from main import create_natural_speech_response
                next_text_with_pauses = create_natural_speech_response(next_text)
                response.say(next_text_with_pauses, language="cs-CZ", rate="0.8")
                return True
            else:
                response.say("Všechny otázky zodpovězeny. Test končí.", language="cs-CZ")
                return False
                
    except Exception as e:
        logger.error(f"❌ Chyba v pokročilém testu: {e}")
        response.say("Chyba při vyhodnocování odpovědi.", language="cs-CZ")
        return False

# ===== POKROČILÉ ADMIN ENDPOINTY =====
@admin_router.get("/dashboard", response_class=HTMLResponse, name="admin_dashboard")
def admin_dashboard(request: Request):
    """Pokročilý admin dashboard s vizualizacemi."""
    try:
        stats = DashboardStats()
        
        context = {
            "request": request,
            "overview": stats.get_overview_stats(),
            "question_analytics": stats.get_question_analytics(),
            "performance_trends": stats.get_user_performance_trends(),
            "category_performance": stats.get_category_performance(),
            "badge_statistics": stats.get_badge_statistics()
        }
        
        return templates.TemplateResponse("admin/dashboard.html", context)
        
    except Exception as e:
        logger.error(f"❌ Chyba v admin dashboard: {e}")
        return templates.TemplateResponse("admin/error.html", {
            "request": request,
            "error": str(e)
        })

# Tento soubor slouží jako referenční implementace.
# Funkce z tohoto souboru je třeba integrovat do main.py. 