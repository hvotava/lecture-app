# Tento soubor je potřeba pouze pro inicializaci SQLAlchemy v rámci FastAPI projektu.

try:
    from app.database import db
    from app.models import User, Lesson, Attempt, Answer
except ImportError as e:
    # Pokud není potřeba, může být soubor prázdný
    pass

__all__ = ['db', 'User', 'Lesson', 'Attempt', 'Answer']