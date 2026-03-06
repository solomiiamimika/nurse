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
            [{'text': 'Register', 'callback_data': 'cmd_register'}],
            [{'text': 'Link existing account', 'callback_data': 'cmd_link'}],
        ]
    }


def client_menu():
    return {
        'inline_keyboard': [
            [{'text': 'My Appointments', 'callback_data': 'cmd_appointments'}],
            [{'text': 'Create Request', 'callback_data': 'cmd_create_request'}],
            [{'text': 'Notifications', 'callback_data': 'cmd_notifications'}],
        ]
    }


def provider_menu():
    return {
        'inline_keyboard': [
            [{'text': 'My Appointments', 'callback_data': 'cmd_appointments'}],
            [{'text': 'Open Requests', 'callback_data': 'cmd_open_requests'}],
            [{'text': 'My Offers', 'callback_data': 'cmd_my_offers'}],
            [{'text': 'Notifications', 'callback_data': 'cmd_notifications'}],
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
