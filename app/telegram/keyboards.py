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
            [{'text': '\u2764\ufe0f Favorites', 'callback_data': 'cmd_favorites'}],
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


def flexible_date_option():
    """Show 'Flexible date' button alongside the date prompt."""
    return {
        'inline_keyboard': [
            [{'text': '\U0001f4c5 Date is flexible — arrange later', 'callback_data': 'flexible_date'}],
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


# ── Appointment action buttons ──────────────────────────────────

def provider_appointment_actions(appt_id, appt_type, status, is_no_show_eligible=False):
    """Action buttons for a provider's appointment card.
    appt_type: 'appt' or 'req'
    """
    prefix = f'{appt_type}_{appt_id}'
    buttons = []

    if status == 'confirmed_paid':
        buttons.append([
            {'text': '\u2705 Confirm Arrival', 'callback_data': f'act_arrive_{prefix}'},
            {'text': '\u23f0 Running Late', 'callback_data': f'act_late_{prefix}'},
        ])
        if is_no_show_eligible:
            buttons.append([
                {'text': '\U0001f6ab Client No-Show', 'callback_data': f'act_client_noshow_{prefix}'},
            ])

    if status == 'in_progress':
        buttons.append([
            {'text': '\u2705 Mark Done', 'callback_data': f'act_done_{prefix}'},
        ])

    if not buttons:
        return None
    return {'inline_keyboard': buttons}


def faq_menu():
    """Main FAQ category buttons."""
    return {
        'inline_keyboard': [
            [
                {'text': '\U0001f4a1 How it works', 'callback_data': 'faq_how'},
                {'text': '\U0001f464 For Clients', 'callback_data': 'faq_client'},
            ],
            [
                {'text': '\U0001f4bc For Providers', 'callback_data': 'faq_provider'},
                {'text': '\U0001f4b3 Pricing', 'callback_data': 'faq_pricing'},
            ],
            [
                {'text': '\u2699\ufe0f Account', 'callback_data': 'faq_account'},
            ],
        ]
    }


def faq_questions(category, qa_list):
    """Buttons for individual questions in a FAQ category."""
    buttons = []
    for i, (question, _) in enumerate(qa_list):
        short = question[:40] + ('...' if len(question) > 40 else '')
        buttons.append([{'text': short, 'callback_data': f'faqq_{category}_{i}'}])
    buttons.append([{'text': '\u25c0 Back to FAQ', 'callback_data': 'faq_back'}])
    return {'inline_keyboard': buttons}


def client_appointment_actions(appt_id, appt_type, status, is_no_show_eligible=False):
    """Action buttons for a client's appointment card.
    appt_type: 'appt' or 'req'
    """
    prefix = f'{appt_type}_{appt_id}'
    buttons = []

    if status == 'confirmed_paid' and is_no_show_eligible:
        buttons.append([
            {'text': '\U0001f6ab Provider No-Show', 'callback_data': f'act_prov_noshow_{prefix}'},
        ])

    if status == 'work_submitted':
        buttons.append([
            {'text': '\u2705 Approve & Complete', 'callback_data': f'act_complete_{prefix}'},
            {'text': '\u26a0\ufe0f Report Issue', 'callback_data': f'act_dispute_{prefix}'},
        ])

    if not buttons:
        return None
    return {'inline_keyboard': buttons}
