from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import hashlib
import bcrypt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
from app.database import get_db
from app.models import TokenData
from app.db_models import User as UserDB

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# PASSWORDS - SHA-256 + bcrypt (handles unlimited password length)
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    Flow: plain password -> SHA-256 -> bcrypt verification
    """
    # Step 1: Pre-hash with SHA-256 (handles unlimited length, always 32 bytes)
    sha_hash = hashlib.sha256(plain_password.encode("utf-8")).digest()
    
    # Step 2: Verify with bcrypt
    return bcrypt.checkpw(sha_hash, hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """
    Hash a password using SHA-256 + bcrypt.
    Flow: plain password -> SHA-256 -> bcrypt hash
    """
    # Step 1: Pre-hash with SHA-256 (handles unlimited length, always 32 bytes)
    sha_hash = hashlib.sha256(password.encode("utf-8")).digest()
    
    # Step 2: Hash with bcrypt (32 bytes is well within 72-byte limit)
    bcrypt_hash = bcrypt.hashpw(sha_hash, bcrypt.gensalt())
    
    return bcrypt_hash.decode("utf-8")


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


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> TokenData:
    """
    Get current authenticated user from JWT token.
    Uses PostgreSQL database instead of Firebase Firestore.
    """
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = str(payload.get("sub") or "").strip()
    role = str(payload.get("role") or "").strip().lower() or None
    hospital_id = str(payload.get("hospital_id") or "").strip() or None
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Query user from PostgreSQL database
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Use role from database if not in token
    if not role:
        role = str(user.role.value if hasattr(user.role, 'value') else user.role).strip().lower()

    return TokenData(
        user_id=user_id,
        role=role,
        hospital_id=getattr(user, "hospital_id", None) or hospital_id
    )


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
            # DEBUG: Provide more detail to the user to resolve the 403 error
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Role '{role}' not in {allowed}",
            )
        return current

    return _checker


PORTAL_ROLES = {"patient", "doctor", "admin", "pharmacist", "pharmacy"}


def require_portal_user():
    return require_roles(*sorted(PORTAL_ROLES))