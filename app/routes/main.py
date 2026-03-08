from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import User, ProviderService, Appointment, Message, ServiceHistory, Feedback
from app.models.service import SERVICE_TAG_CATEGORIES
from app.extensions import db
from sqlalchemy import or_, func, and_, desc
from datetime import datetime, timedelta
import json
from difflib import SequenceMatcher
import openai


main_bp = Blueprint('main', __name__)
@main_bp.route('/')
def home():
    return render_template('home.html', service_tag_categories=SERVICE_TAG_CATEGORIES)


@main_bp.route('/search_providers_by_rating')
def search_providers_by_rating():
    # filters: minimum rating and/or part of the name
    min_rating = request.args.get('min_rating', type=float)
    q = request.args.get('q', '', type=str).strip()

    query = User.query.filter(User.role == 'provider')

    if q:
        query = query.filter(or_(
            User.user_name.ilike(f'%{q}%'),
            (User.full_name.isnot(None) & User.full_name.ilike(f'%{q}%'))
        ))

    providers = query.all()

    results = []
    for n in providers:
        avg = n.average_rating
        if min_rating is not None and (avg is None or avg < min_rating):
            continue
        results.append({
            'id': n.id,
            'user_name': n.user_name,
            'full_name': n.full_name,
            'average_rating': avg,
            'reviews_count': n.review_count
        })

    # Sort by rating (best first)
    results.sort(key=lambda x: (x['average_rating'] is None, -(x['average_rating'] or 0)))
    return jsonify(results[:50])


# ── Smart synonym groups (EN / UK / DE / PL) ────────────────────
# Each group contains words that mean the same concept.
# Matching ANY word triggers expansion to ALL words in that group.
_SYNONYMS = [
    # pets & dog walking
    ['dog', 'dogs', 'puppy', 'pet', 'pets', 'walk', 'walking', 'gassi', 'hund', 'hunde', 'haustier', 'tier',
     'собака', 'собаку', 'пес', 'пса', 'песик', 'цуценя', 'тварина', 'вигул', 'гуляти', 'прогулянка',
     'pies', 'spacer', 'zwierzę'],
    # cat care
    ['cat', 'cats', 'kitten', 'katze', 'katzen', 'кіт', 'кішка', 'котик', 'кота', 'kot', 'kotek'],
    # cleaning
    ['clean', 'cleaning', 'cleaner', 'tidy', 'wash', 'housekeeping', 'maid',
     'putzen', 'reinigung', 'sauber', 'saubermachen', 'reinigen', 'haushalt',
     'прибирання', 'прибрати', 'прибиральниця', 'уборка', 'помити', 'мити', 'чистка', 'чистити',
     'sprzątanie', 'sprzątać', 'mycie'],
    # elderly / senior care
    ['elder', 'elderly', 'senior', 'grandma', 'grandpa', 'grandmother', 'grandfather', 'old', 'aged', 'care',
     'oma', 'opa', 'pflege', 'altenpflege', 'seniorenpflege', 'betreuen', 'betreuung',
     'бабуся', 'бабусі', 'бабусю', 'дідусь', 'дідуся', 'літня', 'старший', 'догляд', 'доглядати', 'опіка',
     'babcia', 'dziadek', 'opieka', 'starszy'],
    # childcare / babysitting
    ['child', 'children', 'baby', 'kid', 'kids', 'nanny', 'babysit', 'babysitter', 'babysitting', 'toddler',
     'kinderbetreuung', 'babysitter', 'kinder', 'kind', 'kindermädchen', 'tagesmutter',
     'дитина', 'дитину', 'діти', 'дітей', 'няня', 'няню', 'малюк', 'малюка', 'дитячий',
     'dziecko', 'dzieci', 'niania', 'opiekunka'],
    # errands / shopping / delivery
    ['errand', 'errands', 'pharmacy', 'grocery', 'groceries', 'shop', 'shopping', 'deliver', 'delivery', 'buy', 'pick up', 'fetch',
     'einkaufen', 'apotheke', 'besorgung', 'lieferung', 'lebensmittel', 'supermarkt',
     'аптека', 'аптеку', 'магазин', 'продукти', 'доставка', 'купити', 'принести', 'забрати', 'закупи',
     'apteka', 'sklep', 'zakupy', 'dostawa'],
    # cooking / food
    ['cook', 'cooking', 'food', 'meal', 'meals', 'chef', 'kitchen', 'lunch', 'dinner', 'breakfast',
     'kochen', 'essen', 'mahlzeit', 'küche',
     'готувати', 'їжа', 'їсти', 'обід', 'вечеря', 'сніданок', 'кухня', 'приготувати', 'варити',
     'gotować', 'jedzenie', 'obiad', 'kolacja'],
    # repair / handyman
    ['repair', 'fix', 'handyman', 'plumber', 'electrician', 'broken', 'maintenance',
     'reparatur', 'reparieren', 'handwerker', 'klempner', 'elektriker',
     'ремонт', 'полагодити', 'лагодити', 'зламався', 'зламалось', 'майстер', 'сантехнік', 'електрик',
     'naprawa', 'naprawić', 'złoty rączka', 'hydraulik'],
    # moving / carrying
    ['move', 'moving', 'carry', 'furniture', 'heavy', 'lift', 'transport', 'relocate',
     'umzug', 'umziehen', 'möbel', 'tragen', 'schwer', 'transport',
     'переїзд', 'нести', 'меблі', 'важкий', 'перенести', 'перевезти', 'вантажі',
     'przeprowadzka', 'meble', 'nosić', 'ciężki'],
    # garden / lawn
    ['garden', 'gardening', 'lawn', 'plant', 'plants', 'flowers', 'mow', 'trim', 'yard', 'hedge',
     'garten', 'gartenarbeit', 'rasen', 'pflanzen', 'blumen', 'mähen', 'hecke',
     'сад', 'город', 'газон', 'рослини', 'квіти', 'косити', 'садівник', 'грядки', 'клумба',
     'ogród', 'trawnik', 'rośliny', 'kwiaty'],
    # tutoring / lessons
    ['tutor', 'tutoring', 'lesson', 'lessons', 'teach', 'teacher', 'homework', 'study', 'math', 'english', 'language',
     'nachhilfe', 'unterricht', 'lehrer', 'hausaufgaben', 'lernen',
     'репетитор', 'уроки', 'вчити', 'вчитель', 'домашнє', 'навчання', 'математика', 'англійська', 'мова',
     'korepetycje', 'lekcje', 'nauczyciel'],
    # massage / wellness
    ['massage', 'masseuse', 'spa', 'relax', 'relaxation', 'wellness', 'therapy', 'therapeutic',
     'massage', 'wellness', 'entspannung', 'therapie',
     'масаж', 'масажист', 'розслабитись', 'терапія', 'спа',
     'masaż', 'relaks', 'terapia'],
    # medical / nurse / health
    ['nurse', 'nursing', 'medical', 'health', 'doctor', 'injection', 'blood pressure', 'iv', 'infusion', 'bandage', 'wound',
     'krankenschwester', 'pfleger', 'medizinisch', 'gesundheit', 'arzt', 'spritze', 'blutdruck', 'infusion', 'verband',
     'медсестра', 'медичний', 'здоров\'я', 'лікар', 'укол', 'тиск', 'крапельниця', 'перев\'язка', 'рана',
     'pielęgniarka', 'medyczny', 'zdrowie', 'lekarz', 'zastrzyk'],
    # laundry / ironing
    ['laundry', 'iron', 'ironing', 'wash clothes', 'dry cleaning',
     'wäsche', 'bügeln', 'waschen', 'reinigung',
     'прання', 'прати', 'прасувати', 'білизна', 'одяг', 'хімчистка',
     'pranie', 'prasowanie', 'ubrania'],
    # tech help / computer
    ['computer', 'laptop', 'phone', 'tech', 'technology', 'internet', 'wifi', 'printer', 'it', 'software',
     'computer', 'handy', 'technik', 'drucker',
     'комп\'ютер', 'ноутбук', 'телефон', 'технології', 'інтернет', 'принтер', 'техніка',
     'komputer', 'telefon', 'technologia', 'drukarka'],
    # driving / transport
    ['drive', 'driver', 'taxi', 'ride', 'airport', 'pick up', 'drop off', 'transport',
     'fahren', 'fahrer', 'taxi', 'flughafen', 'abholen',
     'водій', 'таксі', 'відвезти', 'привезти', 'аеропорт', 'підвезти', 'довезти',
     'kierowca', 'taksówka', 'lotnisko', 'podwieźć'],
    # general help
    ['help', 'helper', 'assist', 'assistance', 'support', 'favor', 'favour',
     'hilfe', 'helfen', 'unterstützung', 'assistenz',
     'допомога', 'допомогти', 'помічник', 'підмога', 'підтримка',
     'pomoc', 'pomagać', 'wsparcie'],
    # company / companion / loneliness
    ['companion', 'company', 'loneliness', 'lonely', 'talk', 'conversation', 'visit', 'friend',
     'gesellschaft', 'begleitung', 'einsam', 'einsamkeit', 'besuch', 'gespräch',
     'компанія', 'самотність', 'поговорити', 'провідати', 'друг', 'побалакати', 'спілкування',
     'towarzystwo', 'samotność', 'rozmowa', 'odwiedziny'],
]

# Build a flat lookup: word → index of its group (for fast matching)
_WORD_TO_GROUP = {}
for _gi, _group in enumerate(_SYNONYMS):
    for _w in _group:
        _WORD_TO_GROUP[_w.lower()] = _gi


def _expand_query(q):
    """Expand user query with synonyms + fuzzy matching for smarter results."""
    q_lower = q.lower()
    words = q_lower.split()
    expanded = set(words)

    matched_groups = set()

    # 1) Exact word match → add whole synonym group
    for w in words:
        gi = _WORD_TO_GROUP.get(w)
        if gi is not None:
            matched_groups.add(gi)

    # 2) Substring match: if user typed "соб" check if it's inside "собака"
    if not matched_groups:
        for w in words:
            if len(w) < 3:
                continue
            for syn_word, gi in _WORD_TO_GROUP.items():
                if w in syn_word or syn_word in w:
                    matched_groups.add(gi)

    # 3) Fuzzy match: catch typos and similar words (e.g. "clening" → "cleaning")
    if not matched_groups:
        for w in words:
            if len(w) < 3:
                continue
            best_ratio = 0
            best_gi = None
            for syn_word, gi in _WORD_TO_GROUP.items():
                if abs(len(w) - len(syn_word)) > 3:
                    continue
                ratio = SequenceMatcher(None, w, syn_word).ratio()
                if ratio > best_ratio and ratio >= 0.7:
                    best_ratio = ratio
                    best_gi = gi
            if best_gi is not None:
                matched_groups.add(best_gi)

    # Add all words from matched groups
    for gi in matched_groups:
        expanded.update(w.lower() for w in _SYNONYMS[gi])

    return expanded


def _ai_expand_query(q):
    """Use Ollama (local AI) to extract search keywords from natural language."""
    ollama_url = current_app.config.get('OLLAMA_URL', 'http://localhost:11434/v1')
    ollama_model = current_app.config.get('OLLAMA_MODEL', 'llama3')
    client = openai.OpenAI(base_url=ollama_url, api_key='ollama', timeout=3.0)
    resp = client.chat.completions.create(
        model=ollama_model,
        messages=[
            {
                'role': 'system',
                'content': (
                    'You are a search keyword extractor for a service marketplace. '
                    'The user is looking for a helper/provider. '
                    'Extract relevant search keywords from their request. '
                    'Return ONLY a JSON object: {"keywords": [...]}. '
                    'Include synonyms in English, Ukrainian, and German. '
                    'Be generous — e.g. "собака" should also yield "пес", "dog", "hund", "вигул", "walk". '
                    'Return 8-15 keywords. ONLY JSON, no other text.'
                ),
            },
            {'role': 'user', 'content': q},
        ],
        max_tokens=200,
        temperature=0,
    )
    raw = resp.choices[0].message.content
    # Extract JSON even if model wraps it in markdown
    if '{' in raw:
        raw = raw[raw.index('{'):raw.rindex('}') + 1]
    data = json.loads(raw)
    keywords = data.get('keywords', [])
    result = set(w.lower() for w in keywords)
    result.update(q.lower().split())
    return result


def _serialize_provider(n):
    services = ProviderService.query.filter_by(
        provider_id=n.id, is_available=True
    ).limit(3).all()

    services_list = []
    for s in services:
        name = s.name or (s.base_service.name if s.base_service else 'Service')
        services_list.append({'name': name, 'price': s.price, 'duration': s.duration})

    vis = json.loads(n.profile_visibility or '{}')

    return {
        'id': n.id,
        'user_name': n.user_name,
        'full_name': (n.full_name or n.user_name) if vis.get('full_name', True) else n.user_name,
        'photo': n.photo if vis.get('photo', True) else None,
        'average_rating': n.average_rating,
        'review_count': n.review_count,
        'about_me': n.about_me if vis.get('about_me', True) else None,
        'services': services_list,
    }


@main_bp.route('/search_providers')
def search_providers():
    q = request.args.get('q', '', type=str).strip()

    all_providers = User.query.filter(User.role == 'provider').all()

    if not q:
        # No query — show everyone sorted by rating
        results = [_serialize_provider(p) for p in all_providers]
        results.sort(key=lambda x: -(x['average_rating'] or 0))
        return jsonify(results[:20])

    # Try Ollama AI first, fall back to local synonym matching
    try:
        if current_app.config.get('OLLAMA_ENABLED'):
            expanded = _ai_expand_query(q)
        else:
            expanded = _expand_query(q)
    except Exception:
        expanded = _expand_query(q)

    # Score each provider by how many keywords match
    scored = []
    for p in all_providers:
        score = 0
        # Check provider text fields
        haystack = ' '.join([
            p.user_name or '', p.full_name or '', p.about_me or ''
        ]).lower()

        # Check service names + descriptions
        services = ProviderService.query.filter_by(provider_id=p.id, is_available=True).all()
        for s in services:
            sname = s.name or (s.base_service.name if s.base_service else '')
            haystack += ' ' + (sname or '').lower() + ' ' + (s.description or '').lower() + ' ' + (s.tags or '').lower()

        for kw in expanded:
            if kw in haystack:
                score += 1

        scored.append((p, score))

    # Sort: matched providers first (by score desc), then the rest by rating
    scored.sort(key=lambda x: (-x[1], -(x[0].average_rating or 0)))

    results = [_serialize_provider(p) for p, score in scored[:20]]
    return jsonify(results)


@main_bp.route('/api/stats')
def platform_stats():
    providers = User.query.filter_by(role='provider').count()
    completed = Appointment.query.filter_by(status='completed').count()
    # average_rating is a Python property — compute in Python
    all_providers = User.query.filter_by(role='provider').all()
    ratings = [p.average_rating for p in all_providers if p.average_rating]
    avg = round(sum(ratings) / len(ratings), 1) if ratings else None
    return jsonify({
        'providers': providers,
        'tasks_completed': completed,
        'avg_rating': avg
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


@main_bp.route('/api/send_message', methods=['POST'])
@login_required
def api_send_message():
    """REST endpoint for sending a message (mobile app fallback for Socket.IO)."""
    data = request.get_json()
    recipient_id = data.get('recipient_id')
    text = data.get('text', '').strip()

    if not recipient_id or not text:
        return jsonify({'success': False, 'message': 'recipient_id and text required'}), 400

    recipient = User.query.get(recipient_id)
    if not recipient:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    msg = Message(
        sender_id=current_user.id,
        recipient_id=int(recipient_id),
        text=text,
        message_type='text',
        timestamp=datetime.utcnow(),
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': {
            'id': msg.id,
            'sender_id': msg.sender_id,
            'text': msg.text,
            'message_type': 'text',
            'timestamp': msg.timestamp.isoformat(),
            'is_read': False,
        }
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


@main_bp.route('/api/feedback', methods=['POST'])
@login_required
def submit_feedback():
    """Save user feedback and notify owner via Telegram."""
    data = request.get_json(silent=True) or {}
    category = data.get('category', '').strip()
    message_text = data.get('message', '').strip()
    page_url = data.get('page_url', '')

    if category not in ('bug', 'suggestion') or not message_text:
        return jsonify({'success': False, 'message': 'Invalid data'}), 400

    fb = Feedback(
        user_id=current_user.id,
        category=category,
        message=message_text,
        page_url=page_url,
    )
    db.session.add(fb)
    db.session.commit()

    # Telegram notification
    try:
        from app.utils.telegram import send_telegram
        emoji = '\U0001f41b' if category == 'bug' else '\U0001f4a1'
        tg_msg = (
            f"{emoji} <b>New feedback</b>\n"
            f"<b>Category:</b> {category}\n"
            f"<b>From:</b> @{current_user.user_name}\n"
            f"<b>Page:</b> {page_url}\n\n"
            f"{message_text}"
        )
        send_telegram(tg_msg)
    except Exception:
        pass

    return jsonify({'success': True, 'message': 'Thank you for your feedback!'})


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


