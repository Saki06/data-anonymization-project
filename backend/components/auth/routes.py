"""
Authentication API Routes
Handles user registration, login, and profile retrieval.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from .database import get_db
from .dependencies import get_current_user
from .models import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from .security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest):
    """
    Register a new user account.
    Returns a JWT token so the user is immediately logged in after registration.
    """
    db = get_db()

    # Check if email already exists
    existing = await db.users.find_one({"email": payload.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Create user document
    user_doc = {
        "name": payload.name,
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)

    # Generate JWT
    token = create_access_token(data={"sub": user_id, "email": payload.email})

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user_id,
            name=payload.name,
            email=payload.email,
            created_at=user_doc["created_at"],
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    """
    Authenticate a user and return a JWT token.
    """
    db = get_db()

    user = await db.users.find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user_id = str(user["_id"])
    token = create_access_token(data={"sub": user_id, "email": user["email"]})

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user_id,
            name=user["name"],
            email=user["email"],
            created_at=user.get("created_at"),
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    """
    Get the currently authenticated user's profile.
    Validates the JWT token and returns user information.
    """
    return UserResponse(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        created_at=user.get("created_at"),
    )
