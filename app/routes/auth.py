from fastapi import APIRouter, HTTPException, status, Depends, Form
from datetime import timedelta
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from app.models import UserCreate, UserResponse, Token, TokenData, LoginRequest, LocationUpdate, AuthMethod, ActivityType, UserRole
from app.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    get_current_active_user,
)
from app.database import get_db_session
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import datetime
import uuid
from app.db_models import User as UserDB

router = APIRouter()

class PharmacyLoginRequest(BaseModel):
    email: str = Field(..., description="Pharmacy user email")
    password: str

# ---------------- Phone normalization helpers ----------------
def _normalize_phone(phone: str) -> str:
    """Return a canonical, comparison-friendly phone string."""
    if not phone:
        return ""
        
    # Remove all non-digit characters
    digits = ''.join(ch for ch in str(phone) if ch.isdigit())
    
    # Handle empty case
    if not digits:
        return ""
    
    # PK local format: 03XXXXXXXXX -> +92XXXXXXXXX
    if len(digits) == 11 and digits.startswith('0'):
        return f"+92{digits[1:]}"
        
    # PK international format without +: 923XXXXXXXXX -> +923XXXXXXXXX
    if len(digits) == 12 and digits.startswith('92'):
        return f"+{digits}"
        
    # PK local without leading 0: 3XXXXXXXXX -> +923XXXXXXXXX
    if len(digits) == 10 and digits.startswith('3'):
        return f"+92{digits}"
    
    # If it already starts with +, return as is
    if str(phone).strip().startswith('+'):
        return str(phone).strip()
    
    # For any other case, return the cleaned digits
    return digits

# ---------------- Login helpers ----------------
async def _authenticate_user(login_data: LoginRequest, db: Session):
    """Internal helper to authenticate user and return user object"""
    print(f"[DEBUG] Authentication attempt: {login_data.identifier}")
    
    # Find user by email or phone
    user = None
    if login_data.auth_method == AuthMethod.EMAIL:
        user = db.query(UserDB).filter(
            func.lower(UserDB.email) == login_data.identifier.lower()
        ).first()
    else:  # PHONE
        phone_norm = _normalize_phone(login_data.identifier)
        user = db.query(UserDB).filter(
            or_(
                UserDB.phone == login_data.identifier,
                UserDB.phone == phone_norm
            )
        ).first()
    
    if not user:
        print(f"[ERROR] User not found: {login_data.identifier}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Verify password
    try:
        password_valid = verify_password(login_data.password, user.password_hash)
    except Exception as pwd_error:
        print(f"[ERROR] Password verification error: {str(pwd_error)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    if not password_valid:
        print(f"[ERROR] Invalid password for user: {user.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    return user

def _create_token_response(user: UserDB):
    """Internal helper to create token response for a user"""
    # Convert role to string if it's an Enum
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    
    # Get hospital_id from user record
    user_hospital_id = getattr(user, 'hospital_id', None)
    
    # Create tokens with hospital_id in payload
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user_role, "hospital_id": user_hospital_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(data={"sub": str(user.id), "hospital_id": user_hospital_id})
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

def create_activity_log_sync(user_id: str, activity_type: str, description: str, meta_data: dict = None):
    """Helper function to create activity logs (synchronous version)"""
    try:
        db = get_db_session()
        from app.db_models import ActivityLog as ActivityLogModel
        activity = ActivityLogModel(
            id=str(uuid.uuid4()),
            user_id=user_id,
            activity_type=activity_type,
            description=description,
            meta_data=meta_data or {}
        )
        db.add(activity)
        db.commit()
        db.close()
    except Exception as e:
        print(f"[ERROR] Failed to create activity log: {e}")

@router.get("/check-phone/{phone}")
async def check_phone_exists(phone: str):
    """Check if phone number already exists in database"""
    try:
        db = get_db_session()
        norm = _normalize_phone(phone)
        
        # Check for existing phone (normalized or raw)
        user = db.query(UserDB).filter(
            or_(UserDB.phone == phone, UserDB.phone == norm)
        ).first()
        
        db.close()
        
        return {
            "phone": phone,
            "exists": user is not None,
            "user_id": user.id if user else None
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking phone: {str(e)}"
        )

@router.post("/register", response_model=UserResponse)
async def register_user(user: UserCreate):
    """Register a new user with phone or email authentication"""
    db = get_db_session()
    try:
        print(f"[DEBUG] Starting registration for: {user.email or user.phone}")
        
        # Validate required fields based on auth method
        if user.auth_method == AuthMethod.PHONE and not user.phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is required for phone authentication"
            )
        elif user.auth_method == AuthMethod.EMAIL and not user.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is required for email authentication"
            )
        
        # Check if user already exists
        # 1. Check Email
        if user.email:
            existing_email = db.query(UserDB).filter(
                func.lower(UserDB.email) == user.email.lower()
            ).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Email {user.email} is already registered"
                )
        
        # 2. Check Phone
        if user.phone:
            phone_norm = _normalize_phone(user.phone)
            if not phone_norm:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid phone number format"
                )
            
            existing_phone = db.query(UserDB).filter(
                or_(UserDB.phone == user.phone, UserDB.phone == phone_norm)
            ).first()
            if existing_phone:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Phone number {user.phone} is already registered"
                )
        
        # Create new user
        user_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        # Normalize profile fields
        date_of_birth = user.date_of_birth or getattr(user, 'birthday', None)
        address = user.address or getattr(user, 'location', None)
        
        # Hash password using SHA-256 + bcrypt (handles unlimited length)
        password_hash = get_password_hash(user.password)
        
        # Create user model
        new_user = UserDB(
            id=user_id,
            name=user.name or f"User-{int(now.timestamp())}",
            email=user.email.lower() if user.email else None,
            phone=_normalize_phone(user.phone) if user.phone else None,
            password_hash=password_hash,
            role=user.role.value if hasattr(user.role, 'value') else str(user.role),
            hospital_id=user.hospital_id, # Added support for hospital_id
            location_access=user.location_access,
            date_of_birth=date_of_birth,
            address=address,
            created_at=now,
            updated_at=now
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        print(f"[DEBUG] User created successfully: {user_id}")
        
        # Create activity log
        create_activity_log_sync(
            user_id,
            "PROFILE_UPDATED",
            f"User registered with {user.auth_method} authentication",
            {"auth_method": str(user.auth_method), "location_access": user.location_access}
        )
        
        # Normalize role for Pydantic (case-insensitive)
        role_val = str(new_user.role.value if hasattr(new_user.role, 'value') else new_user.role).lower()

        # Return user data (without password)
        return UserResponse(
            id=str(new_user.id),  # Ensure ID is string, not UUID object
            name=new_user.name,
            email=new_user.email,
            phone=new_user.phone,
            role=role_val,
            hospital_id=new_user.hospital_id, # Return hospital_id
            location_access=new_user.location_access,
            date_of_birth=new_user.date_of_birth,
            address=new_user.address,
            birthday=new_user.date_of_birth,
            location=new_user.address,
            created_at=new_user.created_at,
            updated_at=new_user.updated_at
        )
        
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as e:
        db.rollback()
        error_msg = str(e.orig)
        print(f"[ERROR] Registration IntegrityError: {error_msg}")
        
        # Handle common unique constraint violations
        if "users_phone_key" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This phone number is already registered"
            )
        elif "users_email_key" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email address is already registered"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this information already exists"
            )
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Registration failed: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )
    finally:
        db.close()

@router.post("/login", response_model=Token)
@router.post("/patient/login", response_model=Token)
async def login(login_data: LoginRequest):
    """Login for patients only - OPTIMIZED"""
    db = get_db_session()
    try:
        # OPTIMIZED: Use direct queries instead of helper function
        if login_data.auth_method == AuthMethod.EMAIL:
            user = db.query(UserDB).filter(
                UserDB.email == login_data.identifier.lower()
            ).first()
        else:  # PHONE
            phone_norm = _normalize_phone(login_data.identifier)
            user = db.query(UserDB).filter(
                or_(
                    UserDB.phone == login_data.identifier,
                    UserDB.phone == phone_norm
                )
            ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        user_role = str(user.role.value if hasattr(user.role, 'value') else user.role).lower()
        if user_role != "patient":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: This login is only for patients"
            )
        
        # Verify password
        password_valid = verify_password(login_data.password, user.password_hash)
        if not password_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        return _create_token_response(user)
    finally:
        db.close()

@router.post("/doctor/login", response_model=Token)
async def doctor_login(login_data: LoginRequest):
    """Login specifically for doctors - OPTIMIZED"""
    db = get_db_session()
    try:
        # OPTIMIZED: Use direct queries
        if login_data.auth_method == AuthMethod.EMAIL:
            user = db.query(UserDB).filter(
                UserDB.email == login_data.identifier.lower()
            ).first()
        else:  # PHONE
            phone_norm = _normalize_phone(login_data.identifier)
            user = db.query(UserDB).filter(
                or_(
                    UserDB.phone == login_data.identifier,
                    UserDB.phone == phone_norm
                )
            ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        user_role = str(user.role.value if hasattr(user.role, 'value') else user.role).lower()
        if user_role != "doctor":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: This login is only for doctors"
            )
        
        # Verify password
        password_valid = verify_password(login_data.password, user.password_hash)
        if not password_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        return _create_token_response(user)
    finally:
        db.close()

@router.post("/receptionist/login", response_model=Token)
async def receptionist_login(login_data: LoginRequest):
    """Login specifically for receptionists"""
    db = get_db_session()
    try:
        user = await _authenticate_user(login_data, db)
        user_role = str(user.role.value if hasattr(user.role, 'value') else user.role).lower()
        if user_role != "receptionist":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: This login is only for receptionists"
            )
        return _create_token_response(user)
    finally:
        db.close()

@router.post("/admin/login", response_model=Token)
async def admin_login(login_data: LoginRequest):
    """Login specifically for admins"""
    db = get_db_session()
    try:
        user = await _authenticate_user(login_data, db)
        user_role = str(user.role.value if hasattr(user.role, 'value') else user.role).lower()
        if user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: This login is only for admins"
            )
        return _create_token_response(user)
    finally:
        db.close()

@router.post("/pharmacy/login", response_model=Token)
async def pharmacy_login(login_data: PharmacyLoginRequest):
    """Login specifically for pharmacy users - OPTIMIZED"""
    db = get_db_session()
    try:
        # OPTIMIZED: Direct query without func.lower() - use case-insensitive collation
        user = db.query(UserDB).filter(
            UserDB.email == login_data.email.lower()
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        user_role = str(user.role.value if hasattr(user.role, 'value') else user.role).lower()
        if user_role != "pharmacy" and user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: This login is only for pharmacy staff"
            )
        
        # Verify password
        try:
            password_valid = verify_password(login_data.password, user.password_hash)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        if not password_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        return _create_token_response(user)
    finally:
        db.close()

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: TokenData = Depends(get_current_active_user)):
    """Get current logged-in user details"""
    db = get_db_session()
    try:
        user = db.query(UserDB).filter(UserDB.id == current_user.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        
        # Normalize role to lowercase for Pydantic enum validation
        role_val = str(user.role.value if hasattr(user.role, 'value') else user.role).lower()

        # Extract attributes manually to avoid __dict__ internal fields
        # and ensure compatibility with UserResponse model
        return UserResponse(
            id=str(user.id),
            name=user.name,
            email=user.email,
            phone=user.phone,
            role=role_val,
            hospital_id=user.hospital_id, # Added hospital_id
            location_access=user.location_access or False,
            date_of_birth=user.date_of_birth,
            address=user.address,
            birthday=user.date_of_birth,
            location=user.address,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    finally:
        db.close()

@router.get("/location-access")
async def get_location_access(current_user = Depends(get_current_active_user)):
    """Get user's location access status"""
    return {"location_access": current_user.location_access}

@router.post("/location-access")
async def update_location_access(
    update: LocationUpdate,
    current_user = Depends(get_current_active_user)
):
    """Update user's location access"""
    db = get_db_session()
    try:
        user_id = getattr(current_user, "user_id", getattr(current_user, "id", None))
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if user:
            user.location_access = update.location_access
            user.updated_at = datetime.utcnow()
            db.commit()
        return {"location_access": update.location_access}
    finally:
        db.close()

@router.get("/check-availability")
async def check_availability(email: str = None, phone: str = None):
    """Check if email or phone is available"""
    db = get_db_session()
    try:
        result = {"email_available": True, "phone_available": True}
        
        if email:
            existing = db.query(UserDB).filter(
                func.lower(UserDB.email) == email.lower()
            ).first()
            result["email_available"] = existing is None
            result["email"] = email
        
        if phone:
            phone_norm = _normalize_phone(phone)
            existing = db.query(UserDB).filter(
                or_(UserDB.phone == phone, UserDB.phone == phone_norm)
            ).first()
            result["phone_available"] = existing is None
            result["phone"] = phone
        
        return result
    finally:
        db.close()
