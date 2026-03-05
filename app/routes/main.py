from flask import Blueprint, render_template, request, jsonify
from app.models import User, ProviderService
from sqlalchemy import or_
from datetime import datetime

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

        results.append({
            'id': n.id,
            'user_name': n.user_name,
            'full_name': n.full_name or n.user_name,
            'photo': n.photo,
            'average_rating': n.average_rating,
            'review_count': n.review_count,
            'about_me': n.about_me,
            'services': services_list,
        })

    results.sort(key=lambda x: -(x['average_rating'] or 0))
    return jsonify(results)


@main_bp.route('/patient_info/<int:user_id>')
def patient_info(user_id):
    user=User.query.get_or_404(user_id)
    if user.documents: 
        documents=user.documents.split(',')
    return render_template('client.html', user=user, documents=documents,now = datetime.now())    


