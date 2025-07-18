import sys
import os
import logging
import traceback
from flask import Flask, jsonify
from flask_wtf.csrf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_socketio import SocketIO
from dotenv import load_dotenv

# Načtení .env souboru
load_dotenv()

# Kontrola dostupnosti modulů
try:
    from flask_cors import CORS
    CORS_AVAILABLE = True
except ImportError:
    CORS_AVAILABLE = False

try:
    from flask_migrate import Migrate
    MIGRATE_AVAILABLE = True
except ImportError:
    MIGRATE_AVAILABLE = False

try:
    from flask_socketio import SocketIO
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False

# Nastavení základního loggingu
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import databázové instance
from app.database import db

logger.info("Úspěšně importovány databázové komponenty")

# Inicializace Google Cloud Logging pouze v produkčním prostředí
try:
    # Kontrola, zda běžíme v Google App Engine nebo máme nastaven Google Cloud projekt
    if (os.getenv('GAE_ENV') or 
        os.getenv('GOOGLE_CLOUD_PROJECT') or 
        os.path.exists('/opt/google-cloud-sdk')):
        import google.cloud.logging
        client = google.cloud.logging.Client()
        client.setup_logging()
        logger.info("Google Cloud Logging byl úspěšně inicializován")
    else:
        logger.info("Google Cloud Logging není dostupný - používám standardní logování")
except Exception as e:
    logger.warning(f"Google Cloud Logging není dostupný: {str(e)}")

# Nastavení úrovně logování pro třetí strany
logging.getLogger('twilio').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

def create_app() -> Flask:
    try:
        logger.info("Vytvářím Flask aplikaci")

        app = Flask(__name__)

        # Nastavení CORS
        if CORS_AVAILABLE:
            logger.info("Povoluji CORS")
            CORS(app, resources={
                r"/*": {
                    "origins": "*",
                    "methods": ["GET", "POST", "OPTIONS"],
                    "allow_headers": ["Content-Type", "Authorization"],
                    "expose_headers": ["Content-Type", "Authorization"],
                    "supports_credentials": True,
                    "max_age": 600
                }
            })

        # Nastavení SECRET_KEY
        app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-for-development')

        # Nastavení HTTPS pro URL generování
        app.config['PREFERRED_URL_SCHEME'] = 'https'

        # Nastavení webhook URL
        app.config['WEBHOOK_BASE_URL'] = os.getenv('WEBHOOK_BASE_URL', 'https://lecture-app-production.up.railway.app')
        logger.info(f"Nastavena WEBHOOK_BASE_URL: {app.config['WEBHOOK_BASE_URL']}")

        # Databázová konfigurace
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///voice_learning.db')
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        # Inicializace databáze
        logger.info("Inicializuji databázi")
        db.init_app(app)

        # Inicializace migrací
        if MIGRATE_AVAILABLE:
            logger.info("Inicializuji migrace")
            migrate = Migrate(app, db)

        # Nastavení CSRF ochrany
        logger.info("Inicializuji CSRF ochranu")
        csrf = CSRFProtect(app)

        # Inicializace SocketIO
        if SOCKETIO_AVAILABLE:
            logger.info("Inicializuji SocketIO")
            socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
            app.socketio = socketio
        else:
            logger.warning("SocketIO není dostupné")

        # Registrace blueprintů
        logger.info("Registruji blueprinty")
        from app.routes.admin import bp as admin_bp
        # from app.routes.voice import voice_bp

        app.register_blueprint(admin_bp, url_prefix='/')
        # app.register_blueprint(voice_bp)

        # CSRF konfigurace pro Twilio webhooky
        csrf.exempt(voice_bp)

        # Health check endpoint (/health)
        @app.route('/health')
        def health_check():
            return jsonify({"status": "healthy", "message": "Aplikace běží správně"}), 200

        # Druhý Health check endpoint (/api/health) pro Railway nebo jiný hosting
        @app.route('/api/health')
        def api_health_check():
            return jsonify({"status": "healthy", "message": "Aplikace běží správně"}), 200

        # Root endpoint
        @app.route('/')
        def index():
            return jsonify({
                "message": "Voice Learning API",
                "status": "running",
                "endpoints": {
                    "health": "/health",
                    "api_health": "/api/health",
                    "admin": "/",
                    "voice": "/voice"
                }
            }), 200

        # Error handlers
        @app.errorhandler(500)
        def internal_error(error):
            logger.error(f"Internal Server Error: {str(error)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({
                "error": "Internal Server Error",
                "message": "Došlo k neočekávané chybě. Zkontrolujte logy pro více informací."
            }), 500

        @app.errorhandler(404)
        def not_found_error(error):
            logger.warning(f"Not Found Error: {str(error)}")
            return jsonify({
                "error": "Not Found",
                "message": "Požadovaná stránka nebyla nalezena."
            }), 404

        @app.errorhandler(Exception)
        def handle_exception(e):
            logger.error(f"Unhandled Exception: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({
                "error": "Internal Server Error",
                "message": "Došlo k neočekávané chybě. Zkontrolujte logy pro více informací."
            }), 500

        # Vytvoření tabulek v databázi
        with app.app_context():
            try:
                logger.info("Vytvářím databázové tabulky")
                db.create_all()
                logger.info("Databázové tabulky byly úspěšně vytvořeny")
            except Exception as e:
                logger.error(f"Chyba při vytváření databázových tabulek: {str(e)}")

        logger.info("Aplikace byla úspěšně vytvořena")
        return app

    except Exception as e:
        logger.error(f"Chyba při vytváření aplikace: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
