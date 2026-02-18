

from flask import Blueprint, request, jsonify
from app.models import User
from app.extensions import db, bcrypt
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app.extensions import csrf

api_auth_bp = Blueprint('api_auth', __name__)

# --- РЕЄСТРАЦІЯ ---
@api_auth_bp.route('/register', methods=['POST'])
@csrf.exempt
def register():
    data = request.get_json()
    
    # Отримуємо дані згідно вашої моделі User
    username = data.get('username') # user_name в БД
    email = data.get('email')
    password = data.get('password')
    full_name = data.get('full_name')
    role = data.get('role')
    
    # Валідація (як у вашому auth.py)
    errors = []
    if not username or len(username) < 2:
        errors.append('Username must be at least 2 characters long')
    if not email or '@' not in email:
        errors.append('Invalid email address')
    if not password or len(password) < 6:
        errors.append('Password must be at least 6 characters long')
    if role not in ['client', 'nurse']:
        errors.append('Invalid role (must be client or nurse)')
        
    if User.query.filter_by(user_name=username).first():
        errors.append('User already exists')
    if User.query.filter_by(email=email).first():
        errors.append('Email already exists')

    if errors:
        return jsonify({"msg": "Validation error", "errors": errors}), 400

    # Створення юзера з усіма вашими полями
    new_user = User(
        user_name=username,
        email=email,
        full_name=full_name,
        role=role,
        online=True # Встановлюємо онлайн при реєстрації
        # phone_number, address - можна додати пізніше в профілі або тут
    )
    # Використовуємо ваш сетер password, який сам робить хеш через bcrypt
    new_user.password = password 
    
    try:
        db.session.add(new_user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Database error", "error": str(e)}), 500
    
    # Генеруємо токен
    access_token = create_access_token(identity=str(new_user.id))
    
    return jsonify({
        "msg": "Registration successful",
        "access_token": access_token,
        "user": {
            "id": new_user.id,
            "username": new_user.user_name,
            "role": new_user.role
        }
    }), 201

# --- ЛОГІН ---
@api_auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    login_input = data.get('username') # Може бути email або username
    password = data.get('password')

    if not login_input or not password:
        return jsonify({"msg": "Missing username or password"}), 400

    # Ваша логіка з auth.py: пошук по email АБО по user_name
    user = User.query.filter((User.email == login_input) | (User.user_name == login_input)).first()

    # Перевірка пароля через ваш метод verify_password
    if user and user.verify_password(password):
        access_token = create_access_token(identity=str(user.id))
        
        # Оновлюємо статус online
        user.online = True
        db.session.commit()
        
        return jsonify({
            "access_token": access_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.user_name, # Важливо: поле в БД user_name
                "full_name": user.full_name,
                "role": user.role,
                "photo": user.photo
            }
        }), 200

    return jsonify({"msg": "Invalid username or password"}), 401