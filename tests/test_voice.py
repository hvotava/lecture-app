import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from app.models import User, Lesson, Attempt
from app.services.twilio_service import TwilioService
from app.services.openai_service import OpenAIService

@pytest.fixture
def mock_twilio():
    with patch("app.routes.voice.TwilioService") as mock:
        yield mock

@pytest.fixture
def mock_openai():
    with patch("app.routes.voice.OpenAIService") as mock:
        yield mock

@pytest.fixture
def test_user(db_session):
    user = User(
        name="Test User",
        phone="+420123456789",
        language="cs"
    )
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture
def test_lesson(db_session):
    lesson = Lesson(
        title="Test Lesson",
        language="cs",
        script="Test script",
        questions={
            "current": "Test question?",
            "answer": "Test answer"
        }
    )
    db_session.add(lesson)
    db_session.commit()
    return lesson

@pytest.fixture
def test_attempt(db_session, test_user, test_lesson):
    attempt = Attempt(
        user_id=test_user.id,
        lesson_id=test_lesson.id,
        next_due=datetime.utcnow() + timedelta(days=1)
    )
    db_session.add(attempt)
    db_session.commit()
    return attempt

def test_handle_voice_first_call(client, test_attempt, mock_twilio):
    """Test prvního hovoru - přehraje se úvod."""
    mock_twilio.return_value.create_voice_response.return_value = "<Response>"
    
    response = client.post(f"/voice?attempt_id={test_attempt.id}")
    
    assert response.status_code == 200
    mock_twilio.return_value.create_voice_response.assert_called_once_with(
        test_attempt.lesson.script,
        language=test_attempt.user.language
    )

def test_handle_voice_stop(client, test_attempt, mock_twilio):
    """Test přerušení hovoru."""
    mock_twilio.return_value.create_stop_response.return_value = "<Response>"
    
    response = client.post(
        f"/voice?attempt_id={test_attempt.id}",
        data={"SpeechResult": "stop"}
    )
    
    assert response.status_code == 200
    mock_twilio.return_value.create_stop_response.assert_called_once_with(
        test_attempt.user.language
    )

def test_handle_voice_answer(client, test_attempt, mock_twilio, mock_openai):
    """Test vyhodnocení odpovědi."""
    mock_twilio.return_value.create_voice_response.return_value = "<Response>"
    mock_openai.return_value.score_answer.return_value = (90, [])
    
    response = client.post(
        f"/voice?attempt_id={test_attempt.id}",
        data={"SpeechResult": "Test answer"}
    )
    
    assert response.status_code == 200
    mock_openai.return_value.score_answer.assert_called_once_with(
        test_attempt.lesson.questions["current"],
        test_attempt.lesson.questions["answer"],
        "Test answer"
    )
    
    # Zkontroluj aktualizaci pokusu
    attempt = client.application.db_session.get(Attempt, test_attempt.id)
    assert attempt.score == 90
    assert attempt.wrong_topics == [] 