# Tento soubor je potřeba pro správné fungování Python balíčku 

import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO
import os

# Nastavení základního logování
logger = logging.getLogger(__name__)

# Export hlavních komponent
try:
    from app.database import db
    from app.models import User, Lesson, Attempt, Answer
    logger.info("Úspěšně importovány databázové komponenty")
except ImportError as e:
    logger.error(f"Chyba při importu databázových komponent: {str(e)}")
    raise

__all__ = ['db', 'User', 'Lesson', 'Attempt', 'Answer', 'create_app', 'socketio']

# Inicializace rozšíření
db = SQLAlchemy()
csrf = CSRFProtect()
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')

def create_app():
    """Vytvoří a nakonfiguruje Flask aplikaci."""
    app = Flask(__name__)
    
    # Konfigurace
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///lecture.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = False  # Vypnuto pro API endpointy
    
    # Inicializace rozšíření
    db.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app)
    
    # CORS konfigurace
    CORS(app, origins=["https://lecture-synqflows.appspot.com", "http://localhost:3000"])
    
    # Registrace blueprintů
    from app.routes.voice import voice_bp
    from app.routes.admin import bp as admin_bp
    
    app.register_blueprint(voice_bp, url_prefix='/voice')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Root endpoint
    @app.route('/')
    def index():
        return {
            'message': 'Lecture App API',
            'version': '1.0.0',
            'endpoints': {
                'health': '/health',
                'api_health': '/api/health',
                'voice': '/voice',
                'admin': '/admin'
            }
        }, 200
    
    # Health check endpoint
    @app.route('/health')
    def health():
        try:
            # Jednoduchý health check bez závislostí
            return {'status': 'healthy', 'service': 'lecture-app', 'timestamp': '2024-01-01'}, 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {'status': 'unhealthy', 'error': str(e)}, 500
    
    # API health check endpoint pro Railway
    @app.route('/api/health')
    def api_health():
        try:
            # Jednoduchý health check bez závislostí
            return {'status': 'healthy', 'service': 'lecture-app', 'api': True, 'timestamp': '2024-01-01'}, 200
        except Exception as e:
            logger.error(f"API health check failed: {e}")
            return {'status': 'unhealthy', 'error': str(e)}, 500
    
    # Routes endpoint pro debugging
    @app.route('/routes')
    def routes():
        try:
            routes_list = []
            for rule in app.url_map.iter_rules():
                routes_list.append({
                    'endpoint': rule.endpoint,
                    'methods': list(rule.methods),
                    'rule': str(rule)
                })
            return {'routes': routes_list}, 200
        except Exception as e:
            logger.error(f"Routes endpoint failed: {e}")
            return {'error': str(e)}, 500
    
    # Konfigurace logování
    if not app.debug:
        logging.basicConfig(level=logging.INFO)
    
    return app 