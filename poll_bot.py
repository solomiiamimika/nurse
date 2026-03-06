"""
Telegram bot polling for local development.

Run this alongside your Flask server:
    python poll_bot.py

This script polls Telegram's getUpdates API and feeds updates
to the bot handlers, since webhooks don't work on localhost.
"""
import requests
import time
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    print('ERROR: TELEGRAM_BOT_TOKEN not set in .env')
    sys.exit(1)

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Delete any existing webhook so polling works
print("Removing webhook (if any)...")
requests.post(f"{API}/deleteWebhook", timeout=5)

# Create Flask app context for database access
from app import create_app
app = create_app()

offset = 0

print(f"Polling bot @{os.getenv('TELEGRAM_BOT_NAME', 'bot')}...")
print("Press Ctrl+C to stop.\n")

while True:
    try:
        resp = requests.get(f"{API}/getUpdates", params={
            'offset': offset,
            'timeout': 30,
        }, timeout=35)

        if not resp.ok:
            print(f"API error: {resp.status_code}")
            time.sleep(3)
            continue

        data = resp.json()
        updates = data.get('result', [])

        for update in updates:
            offset = update['update_id'] + 1

            # Log the update
            msg = update.get('message', {})
            cb = update.get('callback_query', {})
            if msg:
                user = msg.get('from', {})
                text = msg.get('text', '')
                print(f"[MSG] {user.get('first_name', '')} ({user.get('id', '')}): {text}")
            elif cb:
                user = cb.get('from', {})
                print(f"[CB]  {user.get('first_name', '')} ({user.get('id', '')}): {cb.get('data', '')}")

            # Process inside Flask app context
            with app.app_context():
                from app.telegram.handlers import dispatch_update
                dispatch_update(update, BOT_TOKEN)

    except KeyboardInterrupt:
        print("\nStopped.")
        break
    except requests.exceptions.Timeout:
        continue
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(3)
