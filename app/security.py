from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, COLLECTIONS
from app.database import get_db
from app.models import TokenData

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# PASSWORDS
def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def get_password_hash(password):
    return pwd_context.hash(password)


# ACCESS TOKEN
def create_access_token(data: dict, expires_delta: timedelta = None):
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not configured")
    to_encode = data.copy()

    expire = datetime.utcnow() + (
        expires_delta if expires_delta
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# REFRESH TOKEN
def create_refresh_token(data: dict):
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not configured")
    expire = datetime.utcnow() + timedelta(days=int(REFRESH_TOKEN_EXPIRE_DAYS or 7))

    to_encode = data.copy()
    to_encode.update({
        "exp": expire,
        "type": "refresh"
    })

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# VERIFY TOKEN
def verify_token(token: str):
    if not SECRET_KEY:
        return None
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = str(payload.get("sub") or "").strip()
    role = str(payload.get("role") or "").strip().lower() or None
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    db = get_db()
    user_doc = db.collection(COLLECTIONS["USERS"]).document(user_id).get()
    if not getattr(user_doc, "exists", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    user_data = user_doc.to_dict() or {}
    if not role:
        role = str(user_data.get("role") or "").strip().lower() or None

    return TokenData(user_id=user_id, role=role)


def get_current_active_user(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    return current_user


def require_roles(*allowed_roles: str):
    allowed = {r.lower() for r in allowed_roles}

    async def _checker(current: TokenData = Depends(get_current_user)) -> TokenData:
        role = str(current.role or "").lower()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role missing in token",
            )
        if allowed and role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current

    return _checker


PORTAL_ROLES = {"patient", "doctor", "admin", "pharmacist", "pharmacy"}


def require_portal_user():
    return require_roles(*sorted(PORTAL_ROLES))