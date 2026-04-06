from fastapi import APIRouter, HTTPException, status, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from typing import Annotated
from pydantic import BaseModel, Field
from app.models import UserCreate, UserResponse, Token, LoginRequest, LocationUpdate, AuthMethod, ActivityLogCreate, ActivityType
from app.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    get_current_active_user,
)
from app.database import get_db
from app.config import COLLECTIONS, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import datetime

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Custom OAuth2 form that doesn't require grant_type
class CustomOAuth2PasswordRequestForm(BaseModel):
    username: Annotated[str, Form()]
    password: Annotated[str, Form()]
    
    class Config:
        from_attributes = True

class PharmacyLoginRequest(BaseModel):
    email: str = Field(..., description="Pharmacy user email")
    password: str

# ---------------- Phone normalization helpers ----------------
def _normalize_phone(phone: str) -> str:
    """Return a canonical, comparison-friendly phone string.

    Rules:
    - Remove all non-digit characters first
    - If it starts with '0' and length 11 (PK local), convert to '+92' + last 10 digits
    - If it starts with '92' and length 12, prefix with '+'
    - If it starts with '3' and length 10, assume it's a PK number and prefix with '+92'
    - If already starts with '+', keep as is
    - Otherwise return the cleaned number as is
    """
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

async def create_activity_log(user_id: str, activity_type: ActivityType, description: str, metadata: dict = None):
    """Helper function to create activity logs"""
    db = get_db()
    activities_ref = db.collection("activities")
    
    activity_ref = activities_ref.document()
    activity_data = {
        "id": activity_ref.id,
        "user_id": user_id,
        "activity_type": activity_type,
        "description": description,
        "metadata": metadata or {},
        "created_at": datetime.utcnow()
    }
    
    activity_ref.set(activity_data)

@router.get("/check-phone/{phone}")
async def check_phone_exists(phone: str):
    """Check if phone number already exists in database"""
    try:
        db = get_db()
        users_ref = db.collection(COLLECTIONS["USERS"])
        # Try by normalized phone first, then raw as fallback (backward compatibility)
        norm = _normalize_phone(phone)
        users = list(users_ref.where("phone_norm", "==", norm).limit(1).stream())
        if not users:
            users = list(users_ref.where("phone", "==", phone).limit(1).stream())
        
        return {
            "phone": phone,
            "exists": len(users) > 0,
            "count": len(users),
            "users": [{"id": u.id, "name": u.to_dict().get("name", "Unknown")} for u in users] if users else []
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking phone: {str(e)}"
        )

@router.post("/register", response_model=UserResponse)
async def register_user(user: UserCreate):
    """Register a new user with phone or email authentication"""
    try:
        print(f"\n[DEBUG] ===== Starting registration =====")
        print(f"[DEBUG] Input data: {user.dict()}")
        
        # Initialize database
        db = get_db()
        if not db:
            error_msg = "Failed to initialize database connection"
            print(f"[ERROR] {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg
            )
            
        print("[DEBUG] Database connection established")
        
        # Initialize Firestore reference
        users_ref = db.collection(COLLECTIONS["USERS"])
        print(f"[DEBUG] Using collection: {COLLECTIONS['USERS']}")
        
        # Validate required fields based on auth method
        if user.auth_method == AuthMethod.PHONE and not user.phone:
            error_msg = "Phone number is required for phone authentication"
            print(f"[ERROR] {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        elif user.auth_method == AuthMethod.EMAIL and not user.email:
            error_msg = "Email is required for email authentication"
            print(f"[ERROR] {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        print(f"[DEBUG] Using collection: {COLLECTIONS['USERS']}")
        
        # Check if user already exists based on auth method
        if user.auth_method == AuthMethod.EMAIL:
            if not user.email:
                error_msg = "Email is required for email authentication"
                print(f"[ERROR] {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg
                )
                
            print("[DEBUG] Checking for existing email user...")
            existing_user_query = users_ref.where("email", "==", user.email.lower()).limit(1)
            try:
                existing_users = list(existing_user_query.stream())
                if existing_users:
                    error_msg = f"Email {user.email} is already registered"
                    print(f"[ERROR] {error_msg}")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=error_msg
                    )
                print("[DEBUG] No existing user found with this email")
            except Exception as e:
                error_msg = f"Error checking for existing email: {str(e)}"
                print(f"[ERROR] {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error checking user existence"
                )
        else:  # PHONE
            if not user.phone:
                error_msg = "Phone number is required for phone authentication"
                print(f"[ERROR] {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg
                )
                
            # Normalize phone number
            phone_norm = _normalize_phone(user.phone)
            if not phone_norm:
                error_msg = "Invalid phone number format. Please use a valid Pakistani phone number"
                print(f"[ERROR] {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg
                )
                
            # Check if phone already exists
            try:
                existing_phone_query = users_ref.where("phone_norm", "==", phone_norm).limit(1)
                existing_phone_users = list(existing_phone_query.stream())
                if existing_phone_users:
                    error_msg = "This phone number is already registered"
                    print(f"[ERROR] {error_msg}")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=error_msg
                    )
                print("[DEBUG] No existing user found with this phone number")
            except Exception as e:
                error_msg = f"Error checking for existing phone: {str(e)}"
                print(f"[ERROR] {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error checking phone number availability"
                )
            
            # Normalize phone number
            original_phone = user.phone.strip()
            phone_norm = _normalize_phone(original_phone)
            print(f"[DEBUG] Phone number normalization: '{original_phone}' -> '{phone_norm}'")
            
            if not phone_norm:
                error_msg = "Invalid phone number format"
                print(f"[ERROR] {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg
                )
            
            # Check for existing users with this phone (normalized or original format)
            print("[DEBUG] Checking for existing users with this phone...")
            try:
                exists_norm = list(users_ref.where("phone_norm", "==", phone_norm).limit(1).stream())
                exists_raw = list(users_ref.where("phone", "==", original_phone).limit(1).stream())
                
                print(f"[DEBUG] Found {len(exists_norm)} users with phone_norm='{phone_norm}'")
                print(f"[DEBUG] Found {len(exists_raw)} users with phone='{original_phone}'")
                
                if exists_norm or exists_raw:
                    existing = (exists_norm or exists_raw)[0].to_dict()
                    stored_phone = existing.get('phone', '')
                    stored_norm = existing.get('phone_norm', '')
                    
                    error_msg = f"This phone number is already registered (as: {stored_phone})"
                    print(f"[ERROR] {error_msg}")
                    
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=error_msg
                    )
                    
            except Exception as e:
                error_msg = f"Error checking for existing users: {str(e)}"
                print(f"[ERROR] {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="An error occurred while checking user existence"
                )
        
        # Prepare user data with validation
        user_data = user.dict(exclude_unset=True)
        print("[DEBUG] Preparing user data...")
        
        # Normalize profile fields
        user_data["date_of_birth"] = user_data.get("date_of_birth") or user_data.get("birthday")
        user_data["address"] = user_data.get("address") or user_data.get("location")
        
        # Clean up data
        for field in ["birthday", "location"]:
            if field in user_data:
                del user_data[field]
        
        # Set default values for required fields
        if not user_data.get("name"):
            user_data["name"] = f"User-{int(datetime.utcnow().timestamp())}"
        
        # Handle email normalization
        if user_data.get("email"):
            user_data["email"] = user_data["email"].lower()
        
        # Handle phone number normalization (compute here to avoid undefined variable)
        if user.phone:
            original_phone = user.phone.strip()
            user_data["phone"] = original_phone
            user_data["phone_norm"] = _normalize_phone(original_phone)
        
        # Set timestamps
        now = datetime.utcnow()
        user_data.update({
            "created_at": now,
            "updated_at": now,
            "is_active": True,
            "is_verified": False
        })
        
        # Hash password
        user_data["password"] = get_password_hash(user.password)
        
        # Clean up data
        user_data = {k: v for k, v in user_data.items() if v is not None}
        
        # Create user document
        print("[DEBUG] Creating user document...")
        try:
            user_ref = users_ref.document()
            user_data["id"] = user_ref.id
            print(f"[DEBUG] User data to be saved: {user_data}")
        
            # Save user to Firestore
            user_ref.set(user_data)
            print(f"[DEBUG] Successfully created user: {user_ref.id}")
            
        except Exception as e:
            error_msg = f"Failed to create user document: {str(e)}"
            print(f"[ERROR] {error_msg}")
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account. Please try again."
            )
        
        # Create activity log for registration
        await create_activity_log(
            user_data["id"],
            ActivityType.PROFILE_UPDATED,
            f"User registered with {user.auth_method} authentication",
            {"auth_method": user.auth_method, "location_access": user.location_access}
        )
        
        # Return user data without password and with alias fields populated
        user_data.pop("password")
        if user_data.get("date_of_birth") and not user_data.get("birthday"):
            user_data["birthday"] = user_data.get("date_of_birth")
        if user_data.get("address") and not user_data.get("location"):
            user_data["location"] = user_data.get("address")
        return UserResponse(**user_data)
        
    except HTTPException as he:
        # Re-raise HTTP exceptions as-is
        print(f"[HTTP {he.status_code}] {he.detail}")
        raise
    except Exception as e:
        # Log the full error for debugging
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] Registration failed: {str(e)}\n{error_trace}")
        
        # Return a generic error message to the client
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during registration. Please try again."
        )

@router.post("/login", response_model=Token)
async def login_user(login_data: LoginRequest):
    """Login user with phone or email and return access token"""
    db = get_db()
    users_ref = db.collection(COLLECTIONS["USERS"])

    user_docs = []
    
    # Find user based on auth method
    if login_data.auth_method == AuthMethod.EMAIL:
        if not login_data.identifier or "@" not in login_data.identifier:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Valid email address required for email authentication"
            )

        # Convert stream to list
        user_docs = list(
            users_ref.where("email", "==", login_data.identifier)
            .limit(1)
            .stream()
        )
    else:  # PHONE
        if not login_data.identifier or len(login_data.identifier) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Valid phone number required for phone authentication"
            )
        # Try normalized phone first, then raw
        norm = _normalize_phone(login_data.identifier)
        user_docs = list(users_ref.where("phone_norm", "==", norm).limit(1).stream())
        if not user_docs:
            user_docs = list(users_ref.where("phone", "==", login_data.identifier).limit(1).stream())
    
    # user_docs is already a list at this point
    
    if not user_docs:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_doc = user_docs[0]
    user_data = user_doc.to_dict()
    
    # Verify password
    if not verify_password(login_data.password, user_data["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update location access if provided
    if login_data.location_access != user_data.get("location_access", False):
        user_ref = users_ref.document(user_data["id"])
        user_ref.update({
            "location_access": login_data.location_access,
            "updated_at": datetime.utcnow()
        })
        user_data["location_access"] = login_data.location_access
    
    # Create activity log for login
    await create_activity_log(
        user_data["id"],
        ActivityType.LOGIN,
        f"User logged in via {login_data.auth_method}",
        {"auth_method": login_data.auth_method, "location_access": login_data.location_access}
    )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_data["id"]}, expires_delta=access_token_expires
    )

    user_id = user_data["id"]
    role = str(user_data.get("role") or "patient").strip().lower()

    return {
        "access_token": access_token,
        "refresh_token": create_refresh_token({
            "sub": user_id,
            "role": role,
        }),
        "token_type": "bearer",
    }

@router.post("/pharmacy/login", response_model=Token)
async def pharmacy_login(login_data: PharmacyLoginRequest):
    """Login endpoint for Pharmacy Portal (email/password, role-gated)."""
    db = get_db()
    users_ref = db.collection(COLLECTIONS["USERS"])

    email = (login_data.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please enter a valid email address",
        )

    user_docs = list(users_ref.where("email", "==", email).limit(1).stream())
    if not user_docs:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_doc = user_docs[0]
    user_data = user_doc.to_dict() or {}

    if not user_data.get("password") or not verify_password(login_data.password, user_data["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role = str(user_data.get("role") or "patient").strip().lower()
    if role not in {"pharmacy", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account doesn’t have access to the Pharmacy Portal",
        )

    await create_activity_log(
        user_data.get("id") or user_doc.id,
        ActivityType.LOGIN,
        "User logged in via pharmacy portal",
        {"auth_method": "email", "portal": "pharmacy"},
    )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_data.get("id") or user_doc.id},
        expires_delta=access_token_expires,
    )

    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login-form", response_model=Token)
async def login_user_form(form_data: CustomOAuth2PasswordRequestForm = Depends()):
    """Alternative login endpoint for form-based authentication (backward compatibility)"""
    # Try to determine if it's email or phone
    identifier = form_data.username
    auth_method = AuthMethod.EMAIL if "@" in identifier else AuthMethod.PHONE
    
    login_data = LoginRequest(
        identifier=identifier,
        password=form_data.password,
        auth_method=auth_method,
        location_access=False
    )
    
    return await login_user(login_data)

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user = Depends(get_current_active_user)):
    """Get current user information"""
    db = get_db()
    user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
    user_doc = user_ref.get()
    
    if user_doc.exists:
        user_data = user_doc.to_dict()
        user_data.pop("password", None)  # Remove password from response
        # Populate alias fields for frontend compatibility
        if user_data.get("date_of_birth") and not user_data.get("birthday"):
            user_data["birthday"] = user_data.get("date_of_birth")
        if user_data.get("address") and not user_data.get("location"):
            user_data["location"] = user_data.get("address")
        return UserResponse(**user_data)
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found"
    )

@router.get("/location-access")
async def get_location_access_status():
    """Get location access information (public endpoint)"""
    return {
        "message": "Location access helps us find nearby hospitals and doctors",
        "benefits": [
            "Find nearest hospitals",
            "Get location-based doctor recommendations", 
            "Estimate travel time to appointments",
            "Emergency services location"
        ],
        "privacy": "Location data is only used for service improvement and is not shared with third parties"
    }

@router.put("/location-access", response_model=UserResponse)
async def update_location_access(
    location_update: LocationUpdate,
    current_user = Depends(get_current_active_user)
):
    """Update user's location access preference"""
    db = get_db()
    user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
    
    user_ref.update({
        "location_access": location_update.location_access,
        "updated_at": datetime.utcnow()
    })
    
    # Create activity log for location access update
    await create_activity_log(
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        f"Location access preference updated to {location_update.location_access}",
        {"location_access": location_update.location_access}
    )
    
    # Return updated user data
    user_doc = user_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        user_data.pop("password", None)
        return UserResponse(**user_data)
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found"
    )

@router.get("/check-availability")
async def check_user_availability(identifier: str, auth_method: AuthMethod):
    """Check if a phone number or email is available for registration"""
    db = get_db()
    users_ref = db.collection(COLLECTIONS["USERS"])
    
    if auth_method == AuthMethod.EMAIL:
        if "@" not in identifier:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )
        query = users_ref.where("email", "==", identifier)
    else:  # PHONE
        if len(identifier) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid phone number format"
            )
        norm = _normalize_phone(identifier)
        # Prefer normalized check; fallback to raw for legacy rows
        existing_users = list(users_ref.where("phone_norm", "==", norm).limit(1).stream())
        if not existing_users:
            existing_users = list(users_ref.where("phone", "==", identifier).limit(1).stream())
    
    return {
        "available": len(existing_users) == 0,
        "message": "Available for registration" if len(existing_users) == 0 else "Already taken"
    } 