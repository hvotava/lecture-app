#!/usr/bin/env python3
"""
Lokální test deploymentu
"""

import os
import sys
import subprocess
import time
import requests

def test_environment():
    """Testuje environment variables"""
    print("🔍 Testuji environment variables:")
    
    # Nastavíme testovací environment
    os.environ['FLASK_ENV'] = 'production'
    os.environ['SECRET_KEY'] = 'test-secret-key-for-local-testing'
    os.environ['DATABASE_URL'] = 'sqlite:///test.db'
    os.environ['PORT'] = '8080'
    
    print("   ✅ Testovací environment nastaven")

def test_app_import():
    """Testuje import aplikace"""
    print("\n🚀 Testuji import aplikace:")
    
    try:
        from wsgi import app
        print("   ✅ Aplikace se úspěšně importovala")
        return app
    except Exception as e:
        print(f"   ❌ Chyba při importu: {e}")
        return None

def test_health_endpoint(app):
    """Testuje health endpoint"""
    print("\n🏥 Testuji health endpoint:")
    
    try:
        with app.test_client() as client:
            response = client.get('/health')
            print(f"   ✅ Health check: {response.status_code}")
            if response.status_code == 200:
                data = response.get_json()
                print(f"   📄 Response: {data}")
            return response.status_code == 200
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return False

def test_gunicorn_start():
    """Testuje spuštění gunicorn"""
    print("\n🐳 Testuji spuštění gunicorn:")
    
    try:
        # Spustíme gunicorn na pozadí
        cmd = [
            'gunicorn',
            '--bind', '0.0.0.0:8080',
            '--workers', '1',
            '--worker-class', 'sync',
            '--timeout', '30',
            '--log-level', 'info',
            'wsgi:app'
        ]
        
        print(f"   Spouštím: {' '.join(cmd)}")
        
        # Spustíme proces na pozadí
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Počkáme chvíli
        time.sleep(5)
        
        # Zkusíme health check
        try:
            response = requests.get('http://localhost:8080/health', timeout=5)
            print(f"   ✅ Gunicorn běží: {response.status_code}")
            
            # Ukončíme proces
            process.terminate()
            process.wait(timeout=5)
            
            return True
        except requests.exceptions.RequestException:
            print("   ❌ Gunicorn nereaguje")
            process.terminate()
            return False
            
    except Exception as e:
        print(f"   ❌ Chyba při spuštění gunicorn: {e}")
        return False

def main():
    """Hlavní funkce"""
    print("🧪 Lokální Deployment Test")
    print("=" * 40)
    
    # Test environment
    test_environment()
    
    # Test import
    app = test_app_import()
    if not app:
        return 1
    
    # Test health endpoint
    health_ok = test_health_endpoint(app)
    
    # Test gunicorn
    gunicorn_ok = test_gunicorn_start()
    
    print("\n📊 Výsledky:")
    print(f"   Health endpoint: {'✅ OK' if health_ok else '❌ CHYBA'}")
    print(f"   Gunicorn: {'✅ OK' if gunicorn_ok else '❌ CHYBA'}")
    
    if health_ok and gunicorn_ok:
        print("\n🎉 Všechny testy prošly!")
        return 0
    else:
        print("\n⚠️  Některé testy selhaly.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 