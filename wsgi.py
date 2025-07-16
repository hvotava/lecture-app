import os
import logging
import sys

# Konfigurace logování na stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

try:
    from app import create_app, socketio
    logger.info("Importuji create_app a socketio z app")

    # Vytvoření aplikace
    app = create_app()
    logger.info("Aplikace byla úspěšně vytvořena")

    # Konfigurace pro WebSocket
    app.config['WEBSOCKET_ENABLED'] = True
    logger.info("WebSocket podpora povolena")

except Exception as e:
    logger.error(f"Chyba při vytváření aplikace: {str(e)}")
    import traceback
    logger.error(f"Traceback: {traceback.format_exc()}")
    raise

# Gunicorn bude hledat proměnnou "app" v tomto souboru
# SocketIO můžeš z Gunicornu spouštět s --worker-class gevent (viz Dockerfile)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # Railway nastavuje PORT automaticky
    socketio.run(app, debug=False, host="0.0.0.0", port=port)
