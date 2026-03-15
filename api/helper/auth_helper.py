"""
Authentication helper functions for JWT-based auth
"""
import os
import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# JWT Configuration
JWT_SECRET = os.getenv('JWT_SECRET', 'your-super-secret-jwt-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_jwt_token(user_data: Dict[str, Any]) -> str:
    """Create JWT token for user"""
    payload = {
        'user_id': user_data['id'],
        'email': user_data['email'],
        'name': user_data.get('name'),
        'role': user_data.get('role', 'user'),
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token

def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify JWT token and return user data"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_token_from_header(authorization: str) -> Optional[str]:
    """Extract token from Authorization header"""
    if not authorization:
        return None
    
    if not authorization.startswith('Bearer '):
        return None
    
    return authorization.replace('Bearer ', '')