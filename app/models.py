from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, Text, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(100), nullable=False)
    phone = mapped_column(String(20), nullable=False)
    email = mapped_column(String(120), nullable=True)
    level = mapped_column(String(20), nullable=True, default="beginner")
    language = mapped_column(String(2), nullable=True, default="cs")
    detail = mapped_column(Text, nullable=True)
    current_lesson_level = mapped_column(Integer, nullable=False, default=0)  # OBNOVENO
    created_at = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    attempts = relationship("Attempt", back_populates="user")
    badges = relationship("UserBadge", back_populates="user")

class Lesson(Base):
    __tablename__ = "lessons"
    id = mapped_column(Integer, primary_key=True)
    title = mapped_column(String(200), nullable=False)
    description = mapped_column(Text, nullable=True)  # Nový sloupec pro popis lekce
    language = mapped_column(String(2), nullable=False, default="cs")
    script = mapped_column(Text, nullable=False, default="")  # Změněno na nullable=False s default
    questions = mapped_column(JSON, nullable=False)
    level = mapped_column(String(20), nullable=False, default="beginner")
    base_difficulty = mapped_column(String(20), nullable=False, default="medium") # "easy", "medium", "hard"
    lesson_number = mapped_column(Integer, nullable=False, default=0)
    required_score = mapped_column(Float, nullable=False, default=90.0)
    lesson_type = mapped_column(String(20), nullable=False, default="test")  # "test", "teaching", "scenario"
    created_at = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    attempts = relationship("Attempt", back_populates="lesson")
    
    def get_next_question(self) -> Optional[dict]:
        if not self.questions.get("all"):
            return None
        current_index = next(
            (i for i, q in enumerate(self.questions["all"]) 
             if q["question"] == self.questions["current"]),
            -1
        )
        if current_index == -1 or current_index == len(self.questions["all"]) - 1:
            next_question = self.questions["all"][0]
        else:
            next_question = self.questions["all"][current_index + 1]
        return {
            "current": next_question["question"],
            "answer": next_question["answer"]
        }

class Badge(Base):
    __tablename__ = "badges"
    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(100), nullable=False, unique=True)
    description = mapped_column(Text, nullable=False)
    icon_svg = mapped_column(Text, nullable=True) # Ikonka jako SVG kód
    category = mapped_column(String(50), nullable=False) # Kategorie, za kterou se odznak uděluje

class UserBadge(Base):
    __tablename__ = "user_badges"
    id = mapped_column(Integer, primary_key=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    badge_id = mapped_column(Integer, ForeignKey("badges.id"), nullable=False)
    awarded_at = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="badges")
    badge = relationship("Badge")

class TestSession(Base):
    """Model pro sledování průběhu testování"""
    __tablename__ = "test_sessions" 
    
    id = mapped_column(Integer, primary_key=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    lesson_id = mapped_column(Integer, ForeignKey("lessons.id"), nullable=False)
    attempt_id = mapped_column(Integer, ForeignKey("attempts.id"), nullable=True)
    
    # Stav testování
    current_question_index = mapped_column(Integer, nullable=False, default=0)
    total_questions = mapped_column(Integer, nullable=False, default=0)
    questions_data = mapped_column(JSON, nullable=False)
    
    # Adaptivní obtížnost a sledování chyb
    difficulty_score = mapped_column(Float, nullable=False, default=50.0)
    failed_categories = mapped_column(JSON, nullable=False, default=list)
    
    # Výsledky
    answers = mapped_column(JSON, nullable=False, default=list)
    scores = mapped_column(JSON, nullable=False, default=list)
    current_score = mapped_column(Float, nullable=False, default=0.0)
    
    # Metadata
    started_at = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = mapped_column(DateTime, nullable=True)
    is_completed = mapped_column(Boolean, nullable=False, default=False)
    
    # Relationships
    user = relationship("User")
    lesson = relationship("Lesson")
    attempt = relationship("Attempt")

class Answer(Base):
    __tablename__ = "answers"
    id = mapped_column(Integer, primary_key=True)
    attempt_id = mapped_column(Integer, ForeignKey("attempts.id"), nullable=False)
    question_index = mapped_column(Integer, nullable=False)
    question_text = mapped_column(Text, nullable=False)
    correct_answer = mapped_column(Text, nullable=False)
    user_answer = mapped_column(Text, nullable=False)
    score = mapped_column(Float, nullable=False)
    is_correct = mapped_column(Boolean, nullable=False)
    feedback = mapped_column(Text)
    suggestions = mapped_column(Text)
    created_at = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    attempt = relationship("Attempt", back_populates="answers")

class Attempt(Base):
    __tablename__ = "attempts"
    id = mapped_column(Integer, primary_key=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    lesson_id = mapped_column(Integer, ForeignKey("lessons.id"), nullable=False)
    status = mapped_column(String(20), nullable=False, default="pending")
    score = mapped_column(Float)
    feedback = mapped_column(Text)
    created_at = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = mapped_column(DateTime)
    next_due = mapped_column(DateTime)
    user = relationship("User", back_populates="attempts")
    lesson = relationship("Lesson", back_populates="attempts")
    answers = relationship("Answer", back_populates="attempt")
    
    def calculate_next_due(self) -> None:
        if self.score is None:
            self.next_due = datetime.utcnow() + timedelta(days=1)
        elif self.score < 80:
            self.next_due = datetime.utcnow() + timedelta(days=3)
        elif self.score < 90:
            self.next_due = datetime.utcnow() + timedelta(days=7)
        else:
            self.next_due = datetime.utcnow() + timedelta(days=30) 
            
    def calculate_overall_score(self) -> float:
        if not self.answers:
            return 0.0
        total_score = sum(answer.score for answer in self.answers)
        return total_score / len(self.answers) 