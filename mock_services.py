"""
Mock verze externích služeb pro lokální testování
"""
import json
from unittest.mock import Mock, patch
import sys

class MockTwilioClient:
    """Mock Twilio klienta"""
    
    def __init__(self, *args, **kwargs):
        self.calls = MockCalls()
        self.messages = MockMessages()
    
    class MockCalls:
        def create(self, **kwargs):
            print(f"🎭 Mock Twilio Call: {kwargs}")
            mock_call = Mock()
            mock_call.sid = "CA1234567890abcdef"
            return mock_call
    
    class MockMessages:
        def create(self, **kwargs):
            print(f"🎭 Mock Twilio Message: {kwargs}")
            mock_message = Mock()
            mock_message.sid = "SM1234567890abcdef"
            return mock_message

class MockOpenAIClient:
    """Mock OpenAI klienta"""
    
    def __init__(self, *args, **kwargs):
        self.chat = MockChat()
    
    class MockChat:
        class MockCompletions:
            def create(self, **kwargs):
                print(f"🎭 Mock OpenAI Chat: {kwargs}")
                mock_response = Mock()
                mock_response.choices = [Mock()]
                mock_response.choices[0].message = Mock()
                mock_response.choices[0].message.content = "Toto je mock odpověď od OpenAI."
                return mock_response
        
        def __init__(self):
            self.completions = self.MockCompletions()

def setup_mocks():
    """Nastaví mock objekty pro všechny externí služby"""
    print("🎭 Nastavuji mock služby pro lokální testování...")
    
    # Mock Twilio
    sys.modules['twilio'] = Mock()
    sys.modules['twilio.rest'] = Mock()
    sys.modules['twilio.rest'].Client = MockTwilioClient
    
    # Mock OpenAI
    sys.modules['openai'] = Mock()
    sys.modules['openai'].OpenAI = MockOpenAIClient
    
    print("✅ Mock služby nastaveny!")

if __name__ == "__main__":
    setup_mocks() 