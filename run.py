import logging
from app import create_app
from app.extensions import db,socketio
from app.models import User,Message,Service,Appointment,Payment,MedicalRecord,Prescription,Review
#from pyngrok import ngrok
from flask_socketio import SocketIO
import os
import threading
import time

logger = logging.getLogger(__name__)

#ngrok.set_auth_token('30Y5lts3TU8tBYOQ5g0CAxupy09_5M8qwijjkLXatMoCjpjbT')
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = "1"
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = "1"
app = create_app()


def start_bot_polling(app):
    """Run Telegram bot polling in a background thread (for local development)."""
    import requests as req

    bot_token = app.config.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.warning("No TELEGRAM_BOT_TOKEN — bot polling disabled")
        return

    API = f"https://api.telegram.org/bot{bot_token}"

    # Remove webhook so polling works
    try:
        req.post(f"{API}/deleteWebhook", timeout=5)
    except Exception:
        logger.warning("Failed to delete webhook")

    # Set bot menu commands
    try:
        req.post(f"{API}/setMyCommands", json={'commands': [
            {'command': 'start', 'description': 'Start the bot'},
            {'command': 'help', 'description': 'Show available commands'},
            {'command': 'appointments', 'description': 'My appointments'},
            {'command': 'create_request', 'description': 'Post a new request'},
            {'command': 'open_requests', 'description': 'Browse open requests'},
            {'command': 'my_offers', 'description': 'View sent offers'},
            {'command': 'favorites', 'description': 'My favorite providers'},
            {'command': 'notifications', 'description': 'Toggle notifications'},
            {'command': 'switch_role', 'description': 'Switch Client/Provider'},
            {'command': 'cancel', 'description': 'Cancel current operation'},
        ]}, timeout=5)
    except Exception:
        logger.warning("Failed to set bot commands")

    bot_name = app.config.get('TELEGRAM_BOT_NAME', 'bot')
    logger.info("Polling @%s...", bot_name)

    # Clean up expired sessions on startup
    with app.app_context():
        try:
            from app.telegram.conversations import conversation_manager
            conversation_manager.cleanup_expired()
        except Exception:
            logger.exception("Failed to cleanup expired sessions on startup")

    offset = 0
    while True:
        try:
            resp = req.get(f"{API}/getUpdates", params={
                'offset': offset, 'timeout': 30,
            }, timeout=35)

            if not resp.ok:
                logger.error("Bot API error: %s", resp.status_code)
                time.sleep(3)
                continue

            for update in resp.json().get('result', []):
                offset = update['update_id'] + 1
                msg = update.get('message', {})
                cb = update.get('callback_query', {})
                if msg:
                    user = msg.get('from', {})
                    logger.info("MSG %s (%s): %s",
                                user.get('first_name', ''), user.get('id', ''), msg.get('text', ''))
                elif cb:
                    user = cb.get('from', {})
                    logger.info("CB  %s (%s): %s",
                                user.get('first_name', ''), user.get('id', ''), cb.get('data', ''))

                with app.app_context():
                    from app.telegram.handlers import dispatch_update
                    dispatch_update(update, bot_token)

        except req.exceptions.Timeout:
            continue
        except Exception:
            logger.exception("Bot polling error")
            time.sleep(3)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}"
    logger.info("SocketIO async_mode: %s", socketio.async_mode)
    logger.info("Server running at %s", url)

    # Start Telegram bot polling in background (local dev only)
    base_url = app.config.get('BASE_URL', '')
    if base_url.startswith('http://127') or base_url.startswith('http://localhost'):
        if not os.environ.get('WERKZEUG_RUN_MAIN') or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            bot_thread = threading.Thread(target=start_bot_polling, args=(app,), daemon=True)
            bot_thread.start()

    socketio.run(app, host="127.0.0.1", port=5000, debug=True)
