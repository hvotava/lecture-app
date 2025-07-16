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

try:
    from app import create_app, socketio
    logger.info("Importuji create_app a socketio z app")

    app = create_app()
    logger.info("Aplikace byla úspěšně vytvořena")

    app.config["WEBSOCKET_ENABLED"] = True
    logger.info("WebSocket podpora povolena")

except Exception as e:
    logger.error(f"Chyba při vytváření aplikace: {str(e)}")
    import traceback
    logger.error(f"Traceback: {traceback.format_exc()}")
    raise

# Pro Gunicorn/Nixpacks: stačí, že je tu `app`
# Pro lokální vývoj: použij socketio.run
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    socketio.run(app, debug=True, host="0.0.0.0", port=port)
