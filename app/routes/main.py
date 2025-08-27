from flask import Blueprint, render_template, request, jsonify
from app.models import User
from sqlalchemy import or_


main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    return render_template('home.html')


@main_bp.route('/search_nurses')
def search_nurses():
    # фільтри: мінімальний рейтинг і/або частина імені
    min_rating = request.args.get('min_rating', type=float)
    q = request.args.get('q', '', type=str).strip()

    query = User.query.filter(User.role == 'nurse')

    if q:
        query = query.filter(or_(
            User.user_name.ilike(f'%{q}%'),
            (User.full_name.isnot(None) & User.full_name.ilike(f'%{q}%'))
        ))

    nurses = query.all()

    # застосуємо фільтр по середньому рейтингу на Python-рівні (через hybrid теж можна, але так простіше)
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

    # сортуємо за рейтингом (спершу кращі)
    results.sort(key=lambda x: (x['average_rating'] is None, -(x['average_rating'] or 0)))
    return jsonify(results[:50])


@main_bp.route('/patient_info/<int:user_id>')
def patient_info(user_id):
    user=User.query.get_or_404(user_id)
    if user.documents: 
        documents=user.documents.split(',')
    return render_template('client.html', user=user, documents=documents)    


