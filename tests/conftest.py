import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.app import create_app
from app.models import Base
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

# Načti proměnné z .env souboru
load_dotenv()

@pytest.fixture(autouse=True)
def setup_test_env():
    """Nastaví testovací proměnné prostředí."""
    # Použij hodnoty z .env souboru
    os.environ["SECRET_KEY"] = os.getenv("SECRET_KEY", "test-secret-key")
    os.environ["TWILIO_ACCOUNT_SID"] = os.getenv("TWILIO_ACCOUNT_SID", "test-sid")
    os.environ["TWILIO_AUTH_TOKEN"] = os.getenv("TWILIO_AUTH_TOKEN", "test-token")
    os.environ["TWILIO_PHONE_NUMBER"] = os.getenv("TWILIO_PHONE_NUMBER", "+12179787746")
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "test-key")
    
    # Mock OpenAI klienta
    with patch("app.services.openai_service.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"score": 90, "wrong_topics": []}'
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_completion
        mock_openai.return_value = mock_client
        yield
    
    # Cleanup
    for key in ["SECRET_KEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", 
                "TWILIO_PHONE_NUMBER", "OPENAI_API_KEY"]:
        os.environ.pop(key, None)

@pytest.fixture
def app():
    """Vytvoří testovací Flask aplikaci."""
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    
    # Vytvoř testovací databázi
    engine = create_engine(app.config["SQLALCHEMY_DATABASE_URI"])
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    app.db_session = Session()
    
    return app

@pytest.fixture
def client(app):
    """Vytvoří testovací klient."""
    return app.test_client()

@pytest.fixture
def db_session(app):
    """Vytvoří testovací databázovou session."""
    return app.db_session 