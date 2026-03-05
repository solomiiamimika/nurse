from . import client_bp
from flask import render_template, redirect, url_for, flash, request, abort, jsonify, current_app, Blueprint
from sqlalchemy.sql.sqltypes import DateTime
from app.extensions import db, bcrypt, socketio, db, mail
from app.models import Appointment, ProviderService, User, Message, Payment, ClientSelfCreatedAppointment, Review, RequestOfferResponse, ServiceHistory, CancellationPolicy
from app.utils import fuzz_coordinates, validate_coordinates
from app.supabase_storage import get_file_url, delete_from_supabase, upload_to_supabase, buckets
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
import json
from dotenv import load_dotenv
import stripe
import supabase
import base64
from flask_mail import Message as MailMessage
from threading import Thread
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db, User
from datetime import datetime
from app.supabase_storage import upload_to_supabase, supabase
from flask_cors import cross_origin
from flask_login import login_required, current_user
load_dotenv()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
stripe_public_key = os.getenv('STRIPE_PUBLIC_KEY')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)


def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Email sending error: {str(e)}")


def send_payment_confirmation_email(user_email, user_name, service_name, amount, currency, appointment_date, appointment_time,):
    app = current_app._get_current_object()
    msg = MailMessage(
        subject="Payment Confirmation",
        sender=os.getenv('MAIL_DEFAULT_SENDER'),
        recipients=[user_email]
    )
    msg.body = f"""\Hi {user_name},
    Your payment of {amount} {currency} for the service '{service_name}' scheduled on {appointment_date} at {appointment_time} has been successfully processed.
    Thank you for choosing our services!
    Best regards,
    The Team Human-me
    """
    Thread(target=send_async_email, args=(app, msg)).start()


@client_bp.route('/create_payment_session', methods=['POST'])
@login_required
def create_payment_session():
    data = request.get_json()
    appointment_id = data.get('appointment_id')
    appointment = Appointment.query.get_or_404(appointment_id)

    if appointment.client_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    if appointment.status == 'confirmed_paid':
        return jsonify({'error': 'Appointment already paid'}), 400

    amount_cents = int(round(appointment.nurse_service.price * 100))
    transfer_group = f"appt_{appointment_id}"

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],  # Apple Pay включиться як wallet для card
        line_items=[{
            'price_data': {
                'currency': 'eur',
                'product_data': {'name': appointment.nurse_service.name},
                'unit_amount': amount_cents,
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=url_for('client.payment_success', appointment_id=appointment_id, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=url_for('client.payment_cancel', _external=True),
        customer_email=current_user.email,

        # ВАЖЛИВО: це піде в PaymentIntent
        payment_intent_data={
            "capture_method": 'manual',
            "transfer_group": transfer_group,
            "metadata": {
                "appointment_id": str(appointment_id),
                "user_id": str(current_user.id),
            }
        },

        metadata={
            'appointment_id': appointment_id,
            'user_id': current_user.id
        }
    )

    return jsonify({'sessionId': session.id})


@client_bp.route('/create_apple_pay_session', methods=['POST'])
@login_required
def create_apple_pay_session():
    try:
        appointment_id = request.json.get('appointment_id')
        appointment = Appointment.query.get_or_404(appointment_id)

        if appointment.client_id != current_user.id:
            abort(403)

        # creating session for Stripe payment
        session = stripe.checkout.Session.create(
            payment_method_types=['card', 'apple_pay'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': appointment.nurse_service.name,
                    },
                    'unit_amount': int(appointment.nurse_service.price * 100),  # in cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('client.payment_success', appointment_id=appointment_id, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('client.payment_cancel', _external=True),
            customer_email=current_user.email,
            metadata={
                'appointment_id': appointment_id,
                'user_id': current_user.id
            }
        )
        return jsonify({'sessionId': session.id})

    except Exception as e:
        current_app.logger.error(f"Apple Pay error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@client_bp.route('/payment_success/<int:appointment_id>')
@login_required
def payment_success(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    session_id = request.args.get('session_id')

    try:
        if session_id:
            # Отримуємо сесію
            session = stripe.checkout.Session.retrieve(session_id)

            # --- ГОЛОВНА ЗМІНА ТУТ ---
            # Отримуємо деталі PaymentIntent, щоб перевірити статус холду
            payment_intent = stripe.PaymentIntent.retrieve(session.payment_intent)

            # Перевірка:
            # 1. session.payment_status == 'paid' (для звичайних оплат)
            # 2. payment_intent.status == 'requires_capture' (для Auth & Capture)
            is_success = (session.payment_status == 'paid') or (payment_intent.status == 'requires_capture')

            if is_success and session.metadata.get('appointment_id') == str(appointment_id):

                amount_cents = int(session.amount_total)
                platform_fee_cents = int(session.metadata.get('platform_fee_cents', 0))
                transfer_group = session.metadata.get('transfer_group') or f"appt_{appointment_id}"

                payment = Payment(
                    user_id=current_user.id,
                    appointment_id=appointment_id,
                    amount=float(amount_cents) / 100,

                    amount_cents=amount_cents,
                    platform_fee_cents=platform_fee_cents,
                    currency=session.currency,
                    transfer_group=transfer_group,

                    payment_date=datetime.utcnow(),
                    status='completed',  # Тут 'completed' означає "Успішно авторизовано"
                    transaction_id=session.payment_intent,  # Зберігаємо PaymentIntent ID (pi_...)
                    payment_method=session.payment_method_types[0] if session.payment_method_types else 'card'
                )

                db.session.add(payment)
                appointment.status = 'confirmed_paid'
                db.session.commit()

                # Відправка листа (код той самий)
                send_payment_confirmation_email(
                    user_email=current_user.email,
                    user_name=current_user.full_name or current_user.user_name,
                    service_name=appointment.nurse_service.name if appointment.nurse_service else "Service",
                    amount=payment.amount,
                    currency=payment.currency.upper(),
                    appointment_date=appointment.appointment_time.strftime('%Y-%m-%d'),
                    appointment_time=appointment.appointment_time.strftime('%H:%M')
                )

                flash('Payment successfully authorized!', 'success')
            else:
                current_app.logger.warning(f"Payment check failed. Status: {session.payment_status}, PI Status: {payment_intent.status}")
                flash('Payment not confirmed by bank', 'warning')
        else:
            flash('Payment information is missing', 'warning')

    except stripe.StripeError as e:
        current_app.logger.error(f"Stripe verification error: {str(e)}")
        flash('Error during payment verification', 'danger')
    except Exception as e:
        current_app.logger.error(f"Error in payment_success: {str(e)}")
        flash('Server error', 'danger')

    return redirect(url_for('client.appointments'))


@client_bp.route('/payment_cancel')
@login_required
def payment_cancel():
    try:
        session_id = request.args.get('session_id')

        if session_id:
            # getting Stripe session for logging
            session = stripe.checkout.Session.retrieve(session_id)

            # Log cancellation info
            current_app.logger.info(f"Payment canceled - Session ID: {session_id}, Status: {session.payment_status}")

            # If there is appointment_id in metadata, we can update the status
            if 'appointment_id' in session.metadata:
                appointment = Appointment.query.get(session.metadata['appointment_id'])
                if appointment and appointment.client_id == current_user.id:
                    appointment.status = 'payment_canceled'
                    db.session.commit()

        # Creating a record of the canceled payment
        payment_record = Payment(
            user_id=current_user.id,
            status='canceled',
            payment_date=datetime.utcnow(),
            payment_method='stripe',
            amount=0,
            transaction_id=session_id or 'manual_cancel'
        )
        db.session.add(payment_record)
        db.session.commit()

    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe error in payment_cancel: {str(e)}")
    except Exception as e:
        current_app.logger.error(f"Error in payment_cancel: {str(e)}")
        db.session.rollback()

    flash('Payment canceled. You can try again.', 'warning')
    return redirect(url_for('client.appointments'))


@client_bp.route('/appointments/<int:appointment_id>/payout', methods=['POST'])
@login_required
def payout_after_completion(appointment_id):
    appt = Appointment.query.get_or_404(appointment_id)

    # тут має бути перевірка прав: admin/провайдер/твоя логіка
    if appt.status != "completed":
        return jsonify({"error": "Appointment not completed"}), 400

    payment = Payment.query.filter_by(appointment_id=appointment_id, status="completed").first()
    if not payment:
        return jsonify({"error": "No paid payment found"}), 400

    provider = User.query.get_or_404(appt.nurse_id)  # адаптуй під свою модель
    if not provider.stripe_account_id:
        return jsonify({"error": "Provider not connected to Stripe"}), 400

    amount_cents = int(round(payment.amount * 100))
    platform_fee_cents = int(round(amount_cents * 0.10))  # приклад: 10% твоя комісія
    payout_cents = amount_cents - platform_fee_cents

    transfer_group = f"appt_{appointment_id}"

    tr = stripe.Transfer.create(
        amount=payout_cents,
        currency="eur",
        destination=provider.stripe_account_id,  # acct_...
        transfer_group=transfer_group,
        metadata={"appointment_id": str(appointment_id), "payment_intent": payment.transaction_id},
        idempotency_key=f"tr_{appointment_id}",
    )

    # payment.stripe_transfer_id = tr.id  (якщо додаси поле)
    # payment.status = "paid_out"
    # db.session.commit()

    return jsonify({"transferId": tr.id})


@client_bp.route('/stripe_webhook', methods=['POST'])
@cross_origin()
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, current_app.config['STRIPE_WEBHOOK_SECRET']
        )
    except ValueError as e:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        return jsonify({'error': 'Invalid signature'}), 400

    # Handling a successful payment event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session)

    return jsonify({'status': 'success'})


def handle_successful_payment(session):
    try:
        appointment_id = session['metadata'].get('appointment_id')
        user_id = session['metadata'].get('user_id')
        payment_intent_id = session.get('payment_intent')

        if not (appointment_id and user_id and payment_intent_id):
            return

        # 1) анти-дубль: якщо вже є платіж з таким PI — нічого не робимо
        existing = Payment.query.filter_by(transaction_id=payment_intent_id).first()
        if existing:
            return

        # 2) витягнути PI щоб взяти transfer_group + latest_charge (корисно)
        pi = stripe.PaymentIntent.retrieve(payment_intent_id)

        amount_cents = int(session['amount_total'])
        currency = session['currency']

        payment = Payment(
            user_id=int(user_id),
            appointment_id=int(appointment_id),
            amount=float(amount_cents) / 100,  # тимчасово, краще мати amount_cents в моделі
            payment_date=datetime.utcnow(),
            status='completed',
            transaction_id=payment_intent_id,
            payment_method=(session['payment_method_types'][0] if session.get('payment_method_types') else 'card'),
        )

        # якщо додаси ці поля в модель:
        payment.amount_cents = amount_cents
        payment.currency = currency
        payment.stripe_payment_intent_id = payment_intent_id
        payment.stripe_charge_id = pi.get("latest_charge")
        payment.transfer_group = pi.get("transfer_group")

        db.session.add(payment)

        appointment = Appointment.query.get(int(appointment_id))
        if appointment:
            appointment.status = 'confirmed_paid'

        db.session.commit()

        user = User.query.get(int(user_id))
        if user and user.email and appointment:
            send_payment_confirmation_email(
                user_email=user.email,
                user_name=user.full_name or user.user_name,
                service_name=appointment.nurse_service.name if appointment.nurse_service else "Service",
                amount=payment.amount,
                currency=currency.upper(),
                appointment_date=appointment.appointment_time.strftime('%Y-%m-%d'),
                appointment_time=appointment.appointment_time.strftime('%H:%M')
            )

    except Exception as e:
        current_app.logger.error(f"Webhook error: {str(e)}")
        db.session.rollback()
