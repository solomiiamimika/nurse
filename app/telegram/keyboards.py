"""
Inline keyboard builders for the Telegram bot.
"""
import json


def to_json(keyboard):
    return json.dumps(keyboard)


def main_menu(role):
    if role == 'client':
        return client_menu()
    elif role == 'provider':
        return provider_menu()
    return unregistered_menu()


def unregistered_menu():
    return {
        'inline_keyboard': [
            [
                {'text': '\U0001f4dd Register', 'callback_data': 'cmd_register'},
                {'text': '\U0001f517 Link Account', 'callback_data': 'cmd_link'},
            ],
        ]
    }


def client_menu():
    return {
        'inline_keyboard': [
            [{'text': '\U0001f4cb My Appointments', 'callback_data': 'cmd_appointments'}],
            [{'text': '\u2795 Create Request', 'callback_data': 'cmd_create_request'}],
            [{'text': '\U0001f514 Notifications', 'callback_data': 'cmd_notifications'}],
            [{'text': '\U0001f504 Switch to Provider', 'callback_data': 'cmd_switch_role'}],
        ]
    }


def provider_menu():
    return {
        'inline_keyboard': [
            [{'text': '\U0001f4cb My Appointments', 'callback_data': 'cmd_appointments'}],
            [{'text': '\U0001f50d Open Requests', 'callback_data': 'cmd_open_requests'}],
            [{'text': '\U0001f4e8 My Offers', 'callback_data': 'cmd_my_offers'}],
            [{'text': '\U0001f514 Notifications', 'callback_data': 'cmd_notifications'}],
            [{'text': '\U0001f504 Switch to Client', 'callback_data': 'cmd_switch_role'}],
        ]
    }


def confirm_cancel():
    return {
        'inline_keyboard': [
            [
                {'text': 'Confirm', 'callback_data': 'conv_confirm'},
                {'text': 'Cancel', 'callback_data': 'conv_cancel'},
            ]
        ]
    }


def role_select():
    return {
        'inline_keyboard': [
            [
                {'text': 'Client', 'callback_data': 'role_client'},
                {'text': 'Provider', 'callback_data': 'role_provider'},
            ]
        ]
    }


def offer_button(request_id):
    return {
        'inline_keyboard': [
            [{'text': 'Send Offer', 'callback_data': f'offer_req_{request_id}'}],
        ]
    }


def notification_toggle(currently_on):
    label = 'Turn OFF' if currently_on else 'Turn ON'
    return {
        'inline_keyboard': [
            [{'text': label, 'callback_data': 'toggle_notifications'}],
        ]
    }


def counter_offer_response(offer_id):
    """Buttons for provider to respond to a client counter-offer."""
    return {
        'inline_keyboard': [
            [
                {'text': 'Accept Counter', 'callback_data': f'counter_accept_{offer_id}'},
                {'text': 'Revise Price', 'callback_data': f'counter_revise_{offer_id}'},
            ]
        ]
    }
