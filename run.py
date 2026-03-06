from app import create_app
from app.extensions import db,socketio
from app.models import User,Message,Service,Appointment,Payment,MedicalRecord,Prescription,Review
#from pyngrok import ngrok
from flask_socketio import SocketIO
import os
import threading
import time

#ngrok.set_auth_token('30Y5lts3TU8tBYOQ5g0CAxupy09_5M8qwijjkLXatMoCjpjbT')
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = "1"
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = "1"
app = create_app()


def start_bot_polling(app):
    """Run Telegram bot polling in a background thread (for local development)."""
    import requests as req

    bot_token = app.config.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("[BOT] No TELEGRAM_BOT_TOKEN — bot polling disabled")
        return

    API = f"https://api.telegram.org/bot{bot_token}"

    # Remove webhook so polling works
    try:
        req.post(f"{API}/deleteWebhook", timeout=5)
    except Exception:
        pass

    bot_name = app.config.get('TELEGRAM_BOT_NAME', 'bot')
    print(f"[BOT] Polling @{bot_name}...")

    offset = 0
    while True:
        try:
            resp = req.get(f"{API}/getUpdates", params={
                'offset': offset, 'timeout': 30,
            }, timeout=35)

            if not resp.ok:
                print(f"[BOT] API error: {resp.status_code}")
                time.sleep(3)
                continue

            for update in resp.json().get('result', []):
                offset = update['update_id'] + 1
                msg = update.get('message', {})
                cb = update.get('callback_query', {})
                if msg:
                    user = msg.get('from', {})
                    print(f"[BOT] MSG {user.get('first_name', '')} ({user.get('id', '')}): {msg.get('text', '')}")
                elif cb:
                    user = cb.get('from', {})
                    print(f"[BOT] CB  {user.get('first_name', '')} ({user.get('id', '')}): {cb.get('data', '')}")

                with app.app_context():
                    from app.telegram.handlers import dispatch_update
                    dispatch_update(update, bot_token)

        except req.exceptions.Timeout:
            continue
        except Exception as e:
            print(f"[BOT] Error: {e}")
            time.sleep(3)


if __name__ == '__main__':
    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}"
    print(">>> SocketIO async_mode:", socketio.async_mode)
    print(f"Server running at {url}")
    print("Press CTRL+C to quit")

    # Start Telegram bot polling in background (local dev only)
    base_url = app.config.get('BASE_URL', '')
    if base_url.startswith('http://127') or base_url.startswith('http://localhost'):
        if not os.environ.get('WERKZEUG_RUN_MAIN') or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            bot_thread = threading.Thread(target=start_bot_polling, args=(app,), daemon=True)
            bot_thread.start()

    socketio.run(app, host="127.0.0.1", port=5000, debug=True)


