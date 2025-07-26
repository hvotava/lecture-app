#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Admin dashboard s pokročilými statistikami a vizualizacemi
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any
from sqlalchemy import func, desc
from app.database import SessionLocal
from app.models import User, TestSession, Badge, UserBadge, Lesson
import logging

logger = logging.getLogger(__name__)

class DashboardStats:
    """Generování statistik pro admin dashboard."""
    
    def __init__(self):
        self.session = SessionLocal()
    
    def __del__(self):
        if hasattr(self, 'session'):
            self.session.close()
    
    def get_overview_stats(self) -> Dict[str, Any]:
        """Vrací základní přehledové statistiky."""
        try:
            # Základní čísla
            total_users = self.session.query(User).count()
            total_tests = self.session.query(TestSession).filter(TestSession.is_completed == True).count()
            total_badges_awarded = self.session.query(UserBadge).count()
            
            # Průměrné skóre za posledních 30 dní
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            recent_sessions = self.session.query(TestSession).filter(
                TestSession.is_completed == True,
                TestSession.completed_at >= thirty_days_ago,
                TestSession.current_score.isnot(None)
            ).all()
            
            avg_score = sum(s.current_score for s in recent_sessions) / len(recent_sessions) if recent_sessions else 0
            
            # Úspěšnost (90%+)
            successful_tests = len([s for s in recent_sessions if s.current_score >= 90])
            success_rate = (successful_tests / len(recent_sessions) * 100) if recent_sessions else 0
            
            return {
                'total_users': total_users,
                'total_tests': total_tests,
                'total_badges_awarded': total_badges_awarded,
                'avg_score_30d': round(avg_score, 1),
                'success_rate_30d': round(success_rate, 1),
                'tests_this_month': len(recent_sessions)
            }
            
        except Exception as e:
            logger.error(f"❌ Chyba při získávání přehledových statistik: {e}")
            return {}
    
    def get_question_analytics(self) -> List[Dict[str, Any]]:
        """Analyzuje výkon jednotlivých otázek."""
        try:
            # Získej všechny dokončené test sessions
            completed_sessions = self.session.query(TestSession).filter(
                TestSession.is_completed == True,
                TestSession.answers.isnot(None)
            ).all()
            
            question_stats = {}
            
            for session in completed_sessions:
                for answer in session.answers or []:
                    question_text = answer.get('question', 'Neznámá otázka')
                    score = answer.get('score', 0)
                    
                    if question_text not in question_stats:
                        question_stats[question_text] = {
                            'question': question_text,
                            'total_attempts': 0,
                            'total_score': 0,
                            'correct_answers': 0,
                            'categories': set()
                        }
                    
                    stats = question_stats[question_text]
                    stats['total_attempts'] += 1
                    stats['total_score'] += score
                    
                    if score >= 80:
                        stats['correct_answers'] += 1
                    
                    # Přidej kategorii, pokud existuje
                    if 'category' in answer:
                        stats['categories'].add(answer['category'])
            
            # Převeď na seznam a spočítej průměry
            result = []
            for question, stats in question_stats.items():
                if stats['total_attempts'] > 0:
                    avg_score = stats['total_score'] / stats['total_attempts']
                    success_rate = (stats['correct_answers'] / stats['total_attempts']) * 100
                    
                    result.append({
                        'question': stats['question'][:100] + '...' if len(stats['question']) > 100 else stats['question'],
                        'attempts': stats['total_attempts'],
                        'avg_score': round(avg_score, 1),
                        'success_rate': round(success_rate, 1),
                        'categories': list(stats['categories']),
                        'difficulty_rating': self._calculate_difficulty_rating(avg_score, success_rate)
                    })
            
            # Seřaď podle obtížnosti (nejtěžší první)
            result.sort(key=lambda x: x['avg_score'])
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Chyba při analýze otázek: {e}")
            return []
    
    def get_user_performance_trends(self) -> Dict[str, Any]:
        """Analyzuje trendy výkonu uživatelů."""
        try:
            # Získej data za posledních 90 dní
            ninety_days_ago = datetime.utcnow() - timedelta(days=90)
            
            sessions = self.session.query(TestSession).filter(
                TestSession.is_completed == True,
                TestSession.completed_at >= ninety_days_ago,
                TestSession.current_score.isnot(None)
            ).order_by(TestSession.completed_at).all()
            
            # Seskup podle týdnů
            weekly_data = {}
            for session in sessions:
                week_start = session.completed_at.date() - timedelta(days=session.completed_at.weekday())
                week_key = week_start.strftime('%Y-%W')
                
                if week_key not in weekly_data:
                    weekly_data[week_key] = {
                        'week': week_start.strftime('%d.%m'),
                        'total_tests': 0,
                        'total_score': 0,
                        'successful_tests': 0
                    }
                
                data = weekly_data[week_key]
                data['total_tests'] += 1
                data['total_score'] += session.current_score
                
                if session.current_score >= 90:
                    data['successful_tests'] += 1
            
            # Převeď na seznam a spočítaj průměry
            trend_data = []
            for week_key in sorted(weekly_data.keys()):
                data = weekly_data[week_key]
                avg_score = data['total_score'] / data['total_tests'] if data['total_tests'] > 0 else 0
                success_rate = (data['successful_tests'] / data['total_tests'] * 100) if data['total_tests'] > 0 else 0
                
                trend_data.append({
                    'week': data['week'],
                    'tests': data['total_tests'],
                    'avg_score': round(avg_score, 1),
                    'success_rate': round(success_rate, 1)
                })
            
            return {
                'weekly_trends': trend_data,
                'total_weeks': len(trend_data),
                'improvement_trend': self._calculate_improvement_trend(trend_data)
            }
            
        except Exception as e:
            logger.error(f"❌ Chyba při analýze trendů: {e}")
            return {}
    
    def get_category_performance(self) -> List[Dict[str, Any]]:
        """Analyzuje výkon podle kategorií otázek."""
        try:
            completed_sessions = self.session.query(TestSession).filter(
                TestSession.is_completed == True,
                TestSession.answers.isnot(None)
            ).all()
            
            category_stats = {}
            
            for session in completed_sessions:
                for answer in session.answers or []:
                    # Zkus získat kategorii z odpovědi nebo z otázky
                    category = 'Neznámá'
                    if isinstance(answer, dict):
                        category = answer.get('category', 'Neznámá')
                        # Pokud není v odpovědi, zkus najít v questions_data
                        if category == 'Neznámá' and hasattr(session, 'questions_data'):
                            question_index = answer.get('question_index', -1)
                            if 0 <= question_index < len(session.questions_data):
                                category = session.questions_data[question_index].get('category', 'Neznámá')
                    
                    score = answer.get('score', 0) if isinstance(answer, dict) else 0
                    
                    if category not in category_stats:
                        category_stats[category] = {
                            'category': category,
                            'total_attempts': 0,
                            'total_score': 0,
                            'correct_answers': 0
                        }
                    
                    stats = category_stats[category]
                    stats['total_attempts'] += 1
                    stats['total_score'] += score
                    
                    if score >= 80:
                        stats['correct_answers'] += 1
            
            # Převeď na seznam a spočítej průměry
            result = []
            for category, stats in category_stats.items():
                if stats['total_attempts'] > 0:
                    avg_score = stats['total_score'] / stats['total_attempts']
                    success_rate = (stats['correct_answers'] / stats['total_attempts']) * 100
                    
                    result.append({
                        'category': stats['category'],
                        'attempts': stats['total_attempts'],
                        'avg_score': round(avg_score, 1),
                        'success_rate': round(success_rate, 1),
                        'performance_level': self._get_performance_level(avg_score)
                    })
            
            # Seřaď podle průměrného skóre (nejhorší první)
            result.sort(key=lambda x: x['avg_score'])
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Chyba při analýze kategorií: {e}")
            return []
    
    def get_badge_statistics(self) -> Dict[str, Any]:
        """Statistiky udělených odznaků."""
        try:
            # Celkové statistiky
            total_badges = self.session.query(Badge).count()
            total_awarded = self.session.query(UserBadge).count()
            
            # Statistiky podle odznaků
            badge_stats = self.session.query(
                Badge.name,
                Badge.category,
                func.count(UserBadge.id).label('awarded_count')
            ).outerjoin(UserBadge).group_by(Badge.id, Badge.name, Badge.category).all()
            
            badge_data = []
            for badge_name, category, count in badge_stats:
                badge_data.append({
                    'name': badge_name,
                    'category': category,
                    'awarded_count': count,
                    'popularity': round((count / total_awarded * 100) if total_awarded > 0 else 0, 1)
                })
            
            # Seřaď podle popularity
            badge_data.sort(key=lambda x: x['awarded_count'], reverse=True)
            
            return {
                'total_badges': total_badges,
                'total_awarded': total_awarded,
                'badge_details': badge_data,
                'most_popular': badge_data[0] if badge_data else None,
                'least_popular': badge_data[-1] if badge_data else None
            }
            
        except Exception as e:
            logger.error(f"❌ Chyba při statistikách odznaků: {e}")
            return {}
    
    def _calculate_difficulty_rating(self, avg_score: float, success_rate: float) -> str:
        """Vypočítá obtížnost otázky."""
        combined_score = (avg_score + success_rate) / 2
        
        if combined_score >= 80:
            return "Lehká"
        elif combined_score >= 60:
            return "Střední"
        elif combined_score >= 40:
            return "Těžká"
        else:
            return "Velmi těžká"
    
    def _calculate_improvement_trend(self, trend_data: List[Dict]) -> str:
        """Vypočítá trend zlepšování."""
        if len(trend_data) < 2:
            return "Nedostatek dat"
        
        first_half = trend_data[:len(trend_data)//2]
        second_half = trend_data[len(trend_data)//2:]
        
        avg_first = sum(d['avg_score'] for d in first_half) / len(first_half)
        avg_second = sum(d['avg_score'] for d in second_half) / len(second_half)
        
        diff = avg_second - avg_first
        
        if diff > 5:
            return "Výrazné zlepšení"
        elif diff > 2:
            return "Mírné zlepšení"
        elif diff > -2:
            return "Stabilní"
        elif diff > -5:
            return "Mírné zhoršení"
        else:
            return "Výrazné zhoršení"
    
    def _get_performance_level(self, avg_score: float) -> str:
        """Určí úroveň výkonu."""
        if avg_score >= 90:
            return "Výborná"
        elif avg_score >= 80:
            return "Dobrá"
        elif avg_score >= 70:
            return "Průměrná"
        elif avg_score >= 60:
            return "Podprůměrná"
        else:
            return "Slabá"

class ScenarioEngine:
    """Engine pro interaktivní scénáře."""
    
    def __init__(self):
        self.scenarios = self._load_scenarios()
    
    def _load_scenarios(self) -> Dict[str, Dict]:
        """Načte definice scénářů."""
        return {
            "maintenance_problem": {
                "title": "Problém s obráběcí kapalinou",
                "description": "Simulace řešení problému s kapalinou v provozu",
                "initial_situation": "Jste technik a operátor vás volá, že stroj silně pění a kapalina má podivný zápach. Co uděláte jako první?",
                "nodes": {
                    "start": {
                        "text": "Operátor hlásí pěnění a zápach. Vaše první akce?",
                        "options": {
                            "A": {"text": "Zkontroluju pH kapaliny", "next": "check_ph"},
                            "B": {"text": "Změním celou kapalinu", "next": "replace_fluid"},
                            "C": {"text": "Přidám biocid", "next": "add_biocid"}
                        }
                    },
                    "check_ph": {
                        "text": "Správně! pH je 7.2, což je nízké. Co teď?",
                        "options": {
                            "A": {"text": "Přidám hydroxid sodný", "next": "adjust_ph"},
                            "B": {"text": "Vyměním kapalinu", "next": "replace_fluid"},
                            "C": {"text": "Zkontroluju koncentraci", "next": "check_concentration"}
                        }
                    },
                    "adjust_ph": {
                        "text": "Výborně! pH upraveno na 8.8. Pěnění ustalo. Scénář dokončen s 95% úspěšností.",
                        "options": {},
                        "score": 95,
                        "end": True
                    },
                    "replace_fluid": {
                        "text": "Zbytečně drahé řešení. Mohli jste problém vyřešit úpravou pH. Scénář dokončen s 60% úspěšností.",
                        "options": {},
                        "score": 60,
                        "end": True
                    },
                    "add_biocid": {
                        "text": "Biocid nepomůže s pH problémem. Pěnění pokračuje. Co teď?",
                        "options": {
                            "A": {"text": "Zkontroluju pH", "next": "check_ph_late"},
                            "B": {"text": "Vyměním kapalinu", "next": "replace_fluid"}
                        }
                    },
                    "check_ph_late": {
                        "text": "pH je skutečně nízké. Měli jste to zkontrolovat dříve. Scénář dokončen s 75% úspěšností.",
                        "options": {},
                        "score": 75,
                        "end": True
                    }
                }
            }
        }
    
    def start_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Spustí scénář."""
        if scenario_id not in self.scenarios:
            return {"error": "Scénář nenalezen"}
        
        scenario = self.scenarios[scenario_id]
        return {
            "scenario_id": scenario_id,
            "title": scenario["title"],
            "description": scenario["description"],
            "current_node": "start",
            "node_data": scenario["nodes"]["start"],
            "score": 0
        }
    
    def process_choice(self, scenario_id: str, current_node: str, choice: str) -> Dict[str, Any]:
        """Zpracuje volbu uživatele."""
        if scenario_id not in self.scenarios:
            return {"error": "Scénář nenalezen"}
        
        scenario = self.scenarios[scenario_id]
        
        if current_node not in scenario["nodes"]:
            return {"error": "Neplatný uzel"}
        
        node = scenario["nodes"][current_node]
        
        if choice not in node["options"]:
            return {"error": "Neplatná volba"}
        
        next_node_id = node["options"][choice]["next"]
        next_node = scenario["nodes"][next_node_id]
        
        return {
            "scenario_id": scenario_id,
            "current_node": next_node_id,
            "node_data": next_node,
            "is_end": next_node.get("end", False),
            "final_score": next_node.get("score", 0) if next_node.get("end", False) else None
        }

if __name__ == "__main__":
    # Test dashboard stats
    stats = DashboardStats()
    overview = stats.get_overview_stats()
    print("📊 Dashboard Overview:", overview) 