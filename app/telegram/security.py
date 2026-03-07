"""
Security helpers for Telegram integration.
- HMAC-SHA256 verification for the Login Widget
- Webhook secret token validation
"""
import hashlib
import hmac
import logging
import time

logger = logging.getLogger(__name__)


def verify_telegram_login(data: dict, bot_token: str) -> bool:
    """
    Verify data from Telegram Login Widget using HMAC-SHA256.
    https://core.telegram.org/widgets/login#checking-authorization
    """
    check_hash = data.pop('hash', None)
    if not check_hash:
        return False

    data_check_arr = sorted(f"{k}={v}" for k, v in data.items())
    data_check_string = "\n".join(data_check_arr)

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, check_hash):
        logger.warning("Telegram login HMAC mismatch")
        return False

    # Reject if auth_date is older than 24 hours
    auth_date = int(data.get('auth_date', 0))
    if time.time() - auth_date > 86400:
        logger.warning("Telegram login auth_date too old")
        return False

    return True


def make_webhook_secret(bot_token: str) -> str:
    """Derive a deterministic webhook secret from the bot token."""
    return hashlib.sha256(f"{bot_token}:webhook".encode()).hexdigest()[:32]


def verify_webhook_secret(header_value: str, bot_token: str) -> bool:
    """Check X-Telegram-Bot-Api-Secret-Token header."""
    expected = make_webhook_secret(bot_token)
    return hmac.compare_digest(header_value or '', expected)
