import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Základní konfigurace
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Twilio konfigurace
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
    
    # Webhook URL - dynamická podle prostředí
    # Na Railway se automaticky nastaví správná URL
    WEBHOOK_BASE_URL = os.getenv('WEBHOOK_BASE_URL', 'https://localhost:8080')
    VOICE_WEBHOOK_URL = f"{WEBHOOK_BASE_URL}/voice"
    MEDIA_STREAM_WEBHOOK_URL = f"{WEBHOOK_BASE_URL}/media-stream"
    
    # OpenAI konfigurace
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = 'gpt-4.1-turbo-preview'
    
    # Databázová konfigurace
    database_url = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    
    # Oprava pro Railway PostgreSQL URL
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Audio konfigurace
    AUDIO_SAMPLE_RATE = 8000
    AUDIO_CHANNELS = 1
    AUDIO_FORMAT = 'g711_ulaw'
    
    # Logování
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # CORS nastavení
    CORS_ORIGINS = [
        'https://lecture-app-production.up.railway.app',
        'https://lecture-synqflows.pythonanywhere.com',
        'https://localhost:8080',
        'https://*.up.railway.app',  # Railway domény
        'http://localhost:3000'      # Pro lokální vývoj
    ]
    
    # SSL/TLS nastavení není potřeba na PythonAnywhere
    # PythonAnywhere poskytuje SSL certifikát automaticky
    
    @classmethod
    def get_webhook_url(cls, endpoint):
        """Vrátí plnou URL pro webhook endpoint."""
        return f"{cls.WEBHOOK_BASE_URL}/{endpoint}"
    
    @classmethod
    def validate_config(cls):
        """Validuje konfiguraci a vrací chybějící proměnné."""
        required_vars = [
            'TWILIO_ACCOUNT_SID',
            'TWILIO_AUTH_TOKEN',
            'TWILIO_PHONE_NUMBER',
            'OPENAI_API_KEY'
        ]
        
        missing = []
        for var in required_vars:
            if not getattr(cls, var):
                missing.append(var)
        
        return missing 