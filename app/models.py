from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, Text, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import db

class User(db.Model):
    """Model pro uživatele."""
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    level = db.Column(db.String(20), nullable=True, default="beginner")
    language = db.Column(db.String(2), nullable=True, default="cs")
    detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    attempts = db.relationship("Attempt", back_populates="user")

class Lesson(db.Model):
    """Model pro lekce."""
    __tablename__ = "lessons"
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    language = db.Column(db.String(2), nullable=False, default="cs")
    script = db.Column(db.Text, nullable=False)
    questions = db.Column(db.JSON, nullable=False)
    level = db.Column(db.String(20), nullable=False, default="beginner")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    attempts = db.relationship("Attempt", back_populates="lesson")
    
    def get_next_question(self) -> Optional[dict]:
        """Vrátí další otázku z dostupných otázek."""
        if not self.questions.get("all"):
            return None
            
        # Najdi aktuální otázku v seznamu
        current_index = next(
            (i for i, q in enumerate(self.questions["all"]) 
             if q["question"] == self.questions["current"]),
            -1
        )
        
        # Pokud není aktuální otázka v seznamu nebo je poslední, vrať první
        if current_index == -1 or current_index == len(self.questions["all"]) - 1:
            next_question = self.questions["all"][0]
        else:
            next_question = self.questions["all"][current_index + 1]
            
        return {
            "current": next_question["question"],
            "answer": next_question["answer"]
        }

class Answer(db.Model):
    """Model pro odpovědi na otázky."""
    __tablename__ = "answers"
    
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("attempts.id"), nullable=False)
    question_index = db.Column(db.Integer, nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.Text, nullable=False)
    user_answer = db.Column(db.Text, nullable=False)
    score = db.Column(db.Float, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    feedback = db.Column(db.Text)
    suggestions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    attempt = db.relationship("Attempt", back_populates="answers")

class Attempt(db.Model):
    """Model pro pokusy o lekci."""
    __tablename__ = "attempts"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    score = db.Column(db.Float)
    feedback = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    next_due = db.Column(db.DateTime)
    user = db.relationship("User", back_populates="attempts")
    lesson = db.relationship("Lesson", back_populates="attempts")
    answers = db.relationship("Answer", back_populates="attempt")
    
    def calculate_next_due(self) -> None:
        """Vypočítá další termín opakování na základě skóre."""
        if self.score is None:
            self.next_due = datetime.utcnow() + timedelta(days=1)
        elif self.score < 80:
            self.next_due = datetime.utcnow() + timedelta(days=3)
        elif self.score < 90:
            self.next_due = datetime.utcnow() + timedelta(days=7)
        else:
            self.next_due = datetime.utcnow() + timedelta(days=30) 
    
    def calculate_overall_score(self) -> float:
        """Vypočítá celkové skóre na základě odpovědí."""
        if not self.answers:
            return 0.0
        
        total_score = sum(answer.score for answer in self.answers)
        return total_score / len(self.answers) 