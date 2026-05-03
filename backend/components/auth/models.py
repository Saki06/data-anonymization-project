"""
Authentication Models
Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime



class RegisterRequest(BaseModel):
    """Schema for user registration."""
    name: str = Field(..., min_length=2, max_length=100, examples=["John Doe"])
    email: EmailStr = Field(..., examples=["john@example.com"])
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    """Schema for user login."""
    email: EmailStr = Field(..., examples=["john@example.com"])
    password: str = Field(...)


class UserResponse(BaseModel):
    """Public user information returned in responses."""
    id: str
    name: str
    email: str
    created_at: Optional[str] = None


class TokenResponse(BaseModel):
    """JWT token returned after login/register."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
