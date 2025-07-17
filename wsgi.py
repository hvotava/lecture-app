import os
import logging
import sys

# Logování na stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

logger.info("=== WSGI.PY STARTUJE ===")
logger.info(f"Python verze: {sys.version}")
logger.info(f"Aktuální adresář: {os.getcwd()}")
logger.info(f"PORT proměnná: {os.environ.get('PORT', 'NENASTAVEN')}")

try:
    from app import create_app
    logger.info("✅ Importuji create_app z app")

    app = create_app()
    logger.info("✅ Aplikace byla úspěšně vytvořena")

    # Import socketio po vytvoření aplikace
    from app import socketio
    logger.info("✅ Importuji socketio z app")

    app.config["WEBSOCKET_ENABLED"] = True
    logger.info("✅ WebSocket podpora povolena")

    # Test health check endpoint
    try:
        with app.test_client() as client:
            response = client.get('/health')
            logger.info(f"✅ Health check test: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"❌ Health check returned {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Health check test failed: {e}")

except Exception as e:
    logger.error(f"❌ Chyba při vytváření aplikace: {str(e)}")
    import traceback
    logger.error(f"❌ Traceback: {traceback.format_exc()}")
    raise

logger.info("=== WSGI.PY ÚSPĚŠNĚ NAČTEN ===")

# Pro Railway deployment - gunicorn bude používat 'app' objekt
# Pro lokální vývoj můžeme použít socketio.run()
if __name__ == "__main__":
    # Railway automaticky nastaví PORT proměnnou
    port_env = os.environ.get("PORT", "8080")
    logger.info(f"🚀 PORT proměnná: {port_env}")
    
    try:
        # Zajistí, že port je číslo, i když někdo do env dá "$PORT" nebo prázdný string
        port = int(port_env)
        logger.info(f"🚀 Používám port: {port}")
    except (ValueError, TypeError):
        logger.warning(f"⚠️ Neplatná proměnná PORT ('{port_env}'), používám port 8080.")
        port = 8080
    
    logger.info(f"🚀 Spouštím aplikaci na portu {port}")
    socketio.run(app, debug=False, host="0.0.0.0", port=port)
