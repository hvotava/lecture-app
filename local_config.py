"""
Lokální konfigurace pro testování aplikace
"""
import os

# Nejprve nastavíme mock služby
import mock_services
mock_services.setup_mocks()

# Nastavení pro lokální vývoj
os.environ['FLASK_ENV'] = 'development'
os.environ['FLASK_DEBUG'] = 'True'

# Mock hodnoty pro lokální testování
os.environ['SECRET_KEY'] = 'local-development-secret-key-for-testing'
os.environ['OPENAI_API_KEY'] = 'sk-test-local-development-key'
os.environ['TWILIO_ACCOUNT_SID'] = 'ACtest123456789'
os.environ['TWILIO_AUTH_TOKEN'] = 'test123456789012345678901234567890'
os.environ['TWILIO_PHONE_NUMBER'] = '+420123456789'

# Lokální databáze (SQLite)
os.environ['DATABASE_URL'] = 'sqlite:///local_test.db'

# Lokální port
os.environ['PORT'] = '5000'

# Vypneme Google Cloud služby pro lokální testování
os.environ['DISABLE_CLOUD_LOGGING'] = 'True'

print("✅ Lokální konfigurace načtena pro testování") 