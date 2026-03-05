from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.models import User, ProviderService, Appointment, Message, ServiceHistory
from app.extensions import db
from sqlalchemy import or_, func, and_, desc
from datetime import datetime, timedelta
import json

main_bp = Blueprint('main', __name__)
@main_bp.route('/')
def home():
    return render_template('home.html')


@main_bp.route('/search_nurses')
def search_nurses():
    # filters: minimum rating and/or part of the name
    min_rating = request.args.get('min_rating', type=float)
    q = request.args.get('q', '', type=str).strip()

    query = User.query.filter(User.role == 'provider')

    if q:
        query = query.filter(or_(
            User.user_name.ilike(f'%{q}%'),
            (User.full_name.isnot(None) & User.full_name.ilike(f'%{q}%'))
        ))

    nurses = query.all()

    # We’ll apply the filter by average rating at the Python level (we could also do it via a hybrid property, but this is simpler).
    results = []
    for n in nurses:
        avg = n.average_rating
        if min_rating is not None and (avg is None or avg < min_rating):
            continue
        results.append({
            'id': n.id,
            'user_name': n.user_name,
            'full_name': n.full_name,
            'average_rating': avg,
            'reviews_count': n.reviews_count
        })

    # Sort by rating (best first)
    results.sort(key=lambda x: (x['average_rating'] is None, -(x['average_rating'] or 0)))
    return jsonify(results[:50])


@main_bp.route('/search_providers')
def search_providers():
    q = request.args.get('q', '', type=str).strip()

    query = User.query.filter(User.role == 'provider')

    if q:
        query = query.filter(or_(
            User.user_name.ilike(f'%{q}%'),
            User.full_name.ilike(f'%{q}%'),
            User.about_me.ilike(f'%{q}%'),
        ))

    nurses = query.limit(20).all()

    results = []
    for n in nurses:
        services = ProviderService.query.filter_by(
            provider_id=n.id, is_available=True
        ).limit(3).all()

        services_list = []
        for s in services:
            name = s.name or (s.base_service.name if s.base_service else 'Service')
            services_list.append({'name': name, 'price': s.price, 'duration': s.duration})

        vis = json.loads(n.profile_visibility or '{}')

        results.append({
            'id': n.id,
            'user_name': n.user_name,
            'full_name': (n.full_name or n.user_name) if vis.get('full_name', True) else n.user_name,
            'photo': n.photo if vis.get('photo', True) else None,
            'average_rating': n.average_rating,
            'review_count': n.review_count,
            'about_me': n.about_me if vis.get('about_me', True) else None,
            'services': services_list,
        })

    results.sort(key=lambda x: -(x['average_rating'] or 0))
    return jsonify(results)


@main_bp.route('/api/stats')
def platform_stats():
    providers = User.query.filter_by(role='provider').count()
    completed = Appointment.query.filter_by(status='completed').count()
    avg = db.session.query(func.avg(User.average_nurse_rating)).filter(
        User.role == 'provider',
        User.average_nurse_rating.isnot(None)
    ).scalar()
    return jsonify({
        'providers': providers,
        'tasks_completed': completed,
        'avg_rating': round(float(avg), 1) if avg else None
    })


@main_bp.route('/patient_info/<int:user_id>')
def patient_info(user_id):
    user=User.query.get_or_404(user_id)
    if user.documents:
        documents=user.documents.split(',')
    return render_template('client.html', user=user, documents=documents,now = datetime.now())


@main_bp.route('/api/unread_count')
@login_required
def unread_count():
    """Return total unread messages for current user."""
    count = Message.query.filter(
        Message.recipient_id == current_user.id,
        Message.is_read == False
    ).count()
    return jsonify({'count': count})


@main_bp.route('/chats')
@login_required
def chats():
    return render_template('chat/chats.html')


@main_bp.route('/chat/<int:user_id>')
@login_required
def chat_with(user_id):
    other_user = User.query.get_or_404(user_id)
    return render_template('chat/conversation.html', other_user=other_user)


@main_bp.route('/api/conversations')
@login_required
def get_conversations():
    """Get list of all conversations for current user."""
    uid = current_user.id

    # Get all users who have exchanged messages with current user
    subq = db.session.query(
        func.least(Message.sender_id, Message.recipient_id).label('u1'),
        func.greatest(Message.sender_id, Message.recipient_id).label('u2'),
        func.max(Message.id).label('last_msg_id'),
        func.count(
            db.case(
                (and_(Message.recipient_id == uid, Message.is_read == False), 1),
            )
        ).label('unread_count')
    ).filter(
        or_(Message.sender_id == uid, Message.recipient_id == uid)
    ).group_by('u1', 'u2').subquery()

    rows = db.session.query(subq, Message).join(
        Message, Message.id == subq.c.last_msg_id
    ).order_by(desc(subq.c.last_msg_id)).all()

    conversations = []
    for row in rows:
        other_id = row.u2 if row.u1 == uid else row.u1
        other = User.query.get(other_id)
        if not other:
            continue
        conversations.append({
            'user_id': other.id,
            'name': other.full_name or other.user_name,
            'photo': other.photo,
            'last_message': row.Message.text or '',
            'last_message_type': row.Message.message_type or 'text',
            'timestamp': row.Message.timestamp.isoformat(),
            'unread': row.unread_count,
        })

    return jsonify(conversations)


@main_bp.route('/api/messages/<int:user_id>')
@login_required
def get_messages(user_id):
    """Get message history with a specific user."""
    uid = current_user.id
    page = request.args.get('page', 1, type=int)
    per_page = 50

    messages = Message.query.filter(
        or_(
            and_(Message.sender_id == uid, Message.recipient_id == user_id),
            and_(Message.sender_id == user_id, Message.recipient_id == uid)
        )
    ).order_by(desc(Message.timestamp)).paginate(page=page, per_page=per_page, error_out=False)

    # Mark messages as read
    Message.query.filter(
        Message.sender_id == user_id,
        Message.recipient_id == uid,
        Message.is_read == False
    ).update({'is_read': True}, synchronize_session=False)
    db.session.commit()

    result = []
    for msg in reversed(messages.items):
        result.append({
            'id': msg.id,
            'sender_id': msg.sender_id,
            'text': msg.text,
            'message_type': msg.message_type or 'text',
            'file_url': msg.supabase_file_path,
            'file_name': msg.file_name,
            'timestamp': msg.timestamp.isoformat(),
            'is_read': msg.is_read,
            'proposal_status': msg.proposal_status,
        })

    return jsonify({
        'messages': result,
        'has_more': messages.has_next,
    })


@main_bp.route('/api/proposal/<int:message_id>/accept', methods=['POST'])
@login_required
def accept_proposal(message_id):
    """Accept a chat proposal — creates Appointment + ServiceHistory."""
    msg = Message.query.get_or_404(message_id)

    if msg.message_type != 'proposal' or msg.proposal_status != 'pending':
        return jsonify({'success': False, 'message': 'Invalid proposal'}), 400

    # Only the recipient can accept
    if msg.recipient_id != current_user.id:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        proposal = json.loads(msg.text)
    except (json.JSONDecodeError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid proposal data'}), 400

    try:
        appo_time = datetime.fromisoformat(proposal.get('datetime', ''))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid date'}), 400

    duration = int(proposal.get('duration_minutes', 60))
    end_time = appo_time + timedelta(minutes=duration)
    price = float(proposal.get('price', 0))
    service_name = proposal.get('service_name', 'Service')

    # Determine who is provider and who is client
    if current_user.role == 'client':
        client_id = current_user.id
        provider_id = msg.sender_id
    else:
        client_id = msg.sender_id
        provider_id = current_user.id

    try:
        appointment = Appointment(
            client_id=client_id,
            provider_id=provider_id,
            appointment_time=appo_time,
            end_time=end_time,
            status='scheduled',
            notes=proposal.get('notes', '')
        )
        db.session.add(appointment)
        db.session.flush()

        service_history = ServiceHistory(
            provider_id=provider_id,
            client_id=client_id,
            service_name=service_name,
            service_description=proposal.get('notes', ''),
            price=price,
            appointment_time=appo_time,
            end_time=end_time,
            status='scheduled'
        )
        db.session.add(service_history)

        msg.proposal_status = 'accepted'
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Proposal accepted',
            'appointment_id': appointment.id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/api/proposal/<int:message_id>/decline', methods=['POST'])
@login_required
def decline_proposal(message_id):
    """Decline a chat proposal."""
    msg = Message.query.get_or_404(message_id)

    if msg.message_type != 'proposal' or msg.proposal_status != 'pending':
        return jsonify({'success': False, 'message': 'Invalid proposal'}), 400

    if msg.recipient_id != current_user.id:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    msg.proposal_status = 'declined'
    db.session.commit()

    return jsonify({'success': True, 'message': 'Proposal declined'})


