#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Systém odznaků a gamifikace pro hlasového asistenta
"""

from datetime import datetime
from typing import List, Dict, Optional
from app.database import SessionLocal
from app.models import Badge, UserBadge, User, TestSession
import logging

logger = logging.getLogger(__name__)

class BadgeSystem:
    """Správa odznaků a gamifikace."""
    
    def __init__(self):
        self.session = SessionLocal()
    
    def __del__(self):
        if hasattr(self, 'session'):
            self.session.close()
    
    def check_and_award_badges(self, user_id: int, test_session: dict) -> List[Dict]:
        """
        Zkontroluje a udělí odznaky na základě výkonu uživatele.
        Vrací seznam nově udělených odznaků.
        """
        awarded_badges = []
        
        try:
            user = self.session.query(User).get(user_id)
            if not user:
                return awarded_badges
            
            # Získej všechny dostupné odznaky
            all_badges = self.session.query(Badge).all()
            
            # Získej už udělené odznaky pro tohoto uživatele
            existing_badges = {ub.badge_id for ub in user.badges}
            
            for badge in all_badges:
                if badge.id in existing_badges:
                    continue  # Odznak už má
                
                if self._meets_badge_criteria(badge, user_id, test_session):
                    # Uděl odznak
                    user_badge = UserBadge(
                        user_id=user_id,
                        badge_id=badge.id,
                        awarded_at=datetime.utcnow()
                    )
                    self.session.add(user_badge)
                    
                    awarded_badges.append({
                        'name': badge.name,
                        'description': badge.description,
                        'category': badge.category,
                        'icon_svg': badge.icon_svg
                    })
                    
                    logger.info(f"🏅 Udělen odznak '{badge.name}' uživateli {user_id}")
            
            self.session.commit()
            return awarded_badges
            
        except Exception as e:
            logger.error(f"❌ Chyba při udělování odznaků: {e}")
            self.session.rollback()
            return []
    
    def _meets_badge_criteria(self, badge: Badge, user_id: int, test_session: dict) -> bool:
        """Zkontroluje, zda uživatel splňuje kritéria pro daný odznak."""
        
        category = badge.category
        answers = test_session.get('answers', [])
        
        if category == "Filtrace a Čištění":
            return self._check_category_mastery(answers, "Filtrace a Čištění", min_score=85, min_questions=2)
        
        elif category == "Chemické Vlastnosti":
            return self._check_category_mastery(answers, "Chemické Vlastnosti", min_score=90, min_questions=3)
        
        elif category == "Typy Kapalin":
            return self._check_category_mastery(answers, "Typy Kapalin", min_score=80, min_questions=2)
        
        elif category == "Bezpečnost a Ekologie":
            return self._check_category_mastery(answers, "Bezpečnost a Ekologie", min_score=95, min_questions=2)
        
        # Speciální odznaky
        elif badge.name == "Perfekcionista":
            return test_session.get('current_score', 0) >= 95
        
        elif badge.name == "Rychlá Ruka":
            # Pokud by měli časování odpovědí
            return len(answers) >= 5 and all(a.get('score', 0) >= 80 for a in answers)
        
        elif badge.name == "Analytik":
            # Pro studenty, kteří dávají podrobné odpovědi
            detailed_answers = [a for a in answers if len(a.get('user_answer', '').split()) >= 5]
            return len(detailed_answers) >= 3
        
        return False
    
    def _check_category_mastery(self, answers: List[dict], category: str, min_score: float, min_questions: int) -> bool:
        """Zkontroluje zvládnutí kategorie."""
        category_answers = [a for a in answers if a.get('question', {}).get('category') == category]
        
        if len(category_answers) < min_questions:
            return False
        
        avg_score = sum(a.get('score', 0) for a in category_answers) / len(category_answers)
        return avg_score >= min_score
    
    def get_user_progress(self, user_id: int) -> Dict:
        """Vrací přehled pokroku uživatele."""
        try:
            user = self.session.query(User).get(user_id)
            if not user:
                return {}
            
            # Statistiky odznaků
            total_badges = self.session.query(Badge).count()
            user_badges = len(user.badges)
            
            # Poslední test sessions pro statistiky
            recent_sessions = self.session.query(TestSession).filter(
                TestSession.user_id == user_id,
                TestSession.is_completed == True
            ).order_by(TestSession.completed_at.desc()).limit(5).all()
            
            recent_scores = [s.current_score for s in recent_sessions if s.current_score]
            
            return {
                'user_id': user_id,
                'badges_earned': user_badges,
                'total_badges': total_badges,
                'badge_completion': (user_badges / total_badges * 100) if total_badges > 0 else 0,
                'recent_average': sum(recent_scores) / len(recent_scores) if recent_scores else 0,
                'tests_completed': len(recent_sessions),
                'current_level': user.current_lesson_level,
                'badges': [
                    {
                        'name': ub.badge.name,
                        'description': ub.badge.description,
                        'awarded_at': ub.awarded_at,
                        'category': ub.badge.category
                    } for ub in user.badges
                ]
            }
            
        except Exception as e:
            logger.error(f"❌ Chyba při získávání pokroku: {e}")
            return {}

class VoiceCommandHandler:
    """Zpracování hlasových příkazů během testu."""
    
    HELP_COMMANDS = ['nápověda', 'pomoc', 'help', 'hint']
    SKIP_COMMANDS = ['přeskočit', 'skip', 'další', 'next']
    
    @staticmethod
    def detect_command(speech_text: str) -> Optional[str]:
        """Detekuje hlasový příkaz v odpovědi."""
        speech_lower = speech_text.lower().strip()
        
        for cmd in VoiceCommandHandler.HELP_COMMANDS:
            if cmd in speech_lower:
                return 'help'
        
        for cmd in VoiceCommandHandler.SKIP_COMMANDS:
            if cmd in speech_lower:
                return 'skip'
        
        return None
    
    @staticmethod
    def get_hint_for_question(question: dict) -> str:
        """Vrací nápovědu pro danou otázku."""
        hint = question.get('hint', '')
        if hint:
            return f"Nápověda: {hint}"
        
        # Fallback nápověda podle kategorie
        category = question.get('category', '')
        fallback_hints = {
            'Základy': 'Zamyslete se nad hlavními funkcemi obráběcích kapalin.',
            'Filtrace a Čištění': 'Pomůže vám rozlišit mezi metodami na povrchu a uvnitř kapaliny.',
            'Chemické Vlastnosti': 'Vzpomeňte si na optimální rozmezí hodnot.',
            'Bezpečnost a Ekologie': 'Myslete na ochranu zdraví a životního prostředí.',
            'Měření': 'Existují různé přístroje pro různé veličiny.',
        }
        
        return f"Nápověda: {fallback_hints.get(category, 'Zkuste se zamyslet nad praktickým použitím.')}"

class NotificationService:
    """Služba pro odesílání souhrnů testů."""
    
    def __init__(self):
        # V budoucnu zde bude integrace s Twilio SMS nebo email službou
        pass
    
    def send_test_summary(self, user: User, test_session: dict, awarded_badges: List[Dict]) -> bool:
        """Odešle souhrn testu uživateli."""
        try:
            summary = self._generate_summary(user, test_session, awarded_badges)
            
            # Pro nyní pouze logování, později SMS/Email
            logger.info(f"📧 Souhrn testu pro {user.name}:")
            logger.info(summary)
            
            # TODO: Implementovat skutečné odesílání
            # if user.phone:
            #     self._send_sms(user.phone, summary)
            # if user.email:
            #     self._send_email(user.email, summary)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Chyba při odesílání souhrnu: {e}")
            return False
    
    def _generate_summary(self, user: User, test_session: dict, awarded_badges: List[Dict]) -> str:
        """Generuje textový souhrn testu."""
        score = test_session.get('current_score', 0)
        total_questions = test_session.get('total_questions', 0)
        answered = len(test_session.get('answers', []))
        failed_categories = test_session.get('failed_categories', [])
        
        summary = f"""
🎓 SOUHRN TESTU - {user.name}

📊 VÝSLEDKY:
• Celkové skóre: {score:.1f}%
• Zodpovězeno: {answered}/{total_questions} otázek
• Úroveň: {'Pokročilá' if score >= 80 else 'Střední' if score >= 60 else 'Základní'}

"""
        
        if awarded_badges:
            summary += "🏅 NOVÉ ODZNAKY:\n"
            for badge in awarded_badges:
                summary += f"• {badge['name']}: {badge['description']}\n"
            summary += "\n"
        
        if failed_categories:
            summary += "📚 DOPORUČENÍ K STUDIU:\n"
            for category in failed_categories:
                summary += f"• {category}\n"
            summary += "\n"
        
        summary += "Děkujeme za účast! 🚀"
        
        return summary.strip()

def create_default_badges():
    """Vytvoří výchozí sadu odznaků, pokud neexistují."""
    session = SessionLocal()
    try:
        badges_to_create = [
            {
                "name": "Mistr Filtrace",
                "category": "Filtrace a Čištění",
                "description": "Za vynikající znalosti v oblasti filtrace a čištění kapalin.",
                "icon_svg": "🔧"
            },
            {
                "name": "pH Šampion",
                "category": "Chemické Vlastnosti",
                "description": "Za perfektní přehled o pH a jeho vlivu na obráběcí kapaliny.",
                "icon_svg": "⚗️"
            },
            {
                "name": "Expert na Emulze",
                "category": "Typy Kapalin",
                "description": "Za hluboké porozumění emulzím a jejich přípravě.",
                "icon_svg": "🧪"
            },
            {
                "name": "Bezpečnostní Profík",
                "category": "Bezpečnost a Ekologie",
                "description": "Za znalosti bezpečnostních postupů a ekologické likvidace.",
                "icon_svg": "🛡️"
            },
            {
                "name": "Perfekcionista",
                "category": "Výkon",
                "description": "Za dosažení 95% a více v testu.",
                "icon_svg": "⭐"
            },
            {
                "name": "Analytik",
                "category": "Styl",
                "description": "Za podrobné a promyšlené odpovědi.",
                "icon_svg": "🔍"
            }
        ]
        
        for badge_data in badges_to_create:
            existing = session.query(Badge).filter_by(name=badge_data['name']).first()
            if not existing:
                badge = Badge(**badge_data)
                session.add(badge)
                logger.info(f"✅ Vytvořen odznak: {badge_data['name']}")
        
        session.commit()
        logger.info("🏅 Výchozí odznaky vytvořeny")
        
    except Exception as e:
        logger.error(f"❌ Chyba při vytváření odznaků: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    # Test vytvoření odznaků
    create_default_badges() 