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

# Pro Railway deployment - gunicorn bude používat 'app' objekt
# Pro lokální vývoj můžeme použít socketio.run()
if __name__ == "__main__":
    port_env = os.environ.get("PORT", "8080")
    try:
        # Zajistí, že port je číslo, i když někdo do env dá "$PORT" nebo prázdný string
        port = int(port_env)
    except Exception:
        logger.warning(f"Neplatná proměnná PORT ('{port_env}'), používám port 8080.")
        port = 8080
    socketio.run(app, debug=False, host="0.0.0.0", port=port)
