from flask_sqlalchemy import SQLAlchemy
import logging
import os
import traceback

logger = logging.getLogger(__name__)

# Inicializace SQLAlchemy
db = SQLAlchemy()

def init_db(app):
    """Inicializuje databázi."""
    try:
        # Nastavení SQLAlchemy
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        
        # Inicializace databáze
        db.init_app(app)
        
        # Vytvoření tabulek pouze v případě, že neexistují
        with app.app_context():
            if not os.getenv('FLASK_ENV') == 'production':
                # V development prostředí vytvoříme tabulky
                db.create_all()
                logger.info("Tabulky byly vytvořeny v development prostředí")
            else:
                # V produkci pouze ověříme připojení
                db.engine.connect()
                logger.info("Databázové připojení bylo úspěšně ověřeno")
        
        logger.info("Databáze byla úspěšně inicializována")
        
    except Exception as e:
        logger.error(f"Chyba při inicializaci databáze: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise 