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
    current_lesson_level = mapped_column(Integer, nullable=False, default=0)  # Nové: aktuální úroveň lekce
    created_at = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    attempts = relationship("Attempt", back_populates="user")
    progress = relationship("UserProgress", back_populates="user")

class Lesson(Base):
    __tablename__ = "lessons"
    id = mapped_column(Integer, primary_key=True)
    title = mapped_column(String(200), nullable=False)
    language = mapped_column(String(2), nullable=False, default="cs")
    script = mapped_column(Text, nullable=False)
    questions = mapped_column(JSON, nullable=False)
    level = mapped_column(String(20), nullable=False, default="beginner")
    lesson_number = mapped_column(Integer, nullable=False, default=0)  # Nové: číslo lekce (0, 1, 2, ...)
    required_score = mapped_column(Float, nullable=False, default=90.0)  # Nové: požadované skóre pro postup
    lesson_type = mapped_column(String(20), nullable=False, default="standard")  # Nové: "entry_test", "standard", "advanced"
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

class UserProgress(Base):
    """Nový model pro sledování pokroku uživatele"""
    __tablename__ = "user_progress"
    id = mapped_column(Integer, primary_key=True)
    user_id = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    lesson_number = mapped_column(Integer, nullable=False)
    is_completed = mapped_column(Boolean, nullable=False, default=False)
    best_score = mapped_column(Float, nullable=True)
    attempts_count = mapped_column(Integer, nullable=False, default=0)
    first_completed_at = mapped_column(DateTime, nullable=True)
    last_attempt_at = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    user = relationship("User", back_populates="progress")

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