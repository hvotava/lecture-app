from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

# Načti proměnné z .env souboru
load_dotenv()

# Vytvoř engine pro připojení k databázi
engine = create_engine(os.environ.get("DATABASE_URL", "sqlite:///voice_learning.db"))

# Přidej sloupec detail do tabulky users
with engine.connect() as conn:
    conn.execute(text("ALTER TABLE users ADD COLUMN detail TEXT"))
    conn.commit()

print("Migrace byla úspěšně provedena.") 