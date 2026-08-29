from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


def _validate_bcrypt_length(value: str) -> str:
    # bcrypt rejects input above 72 *bytes*; pydantic's max_length counts characters.
    if len(value.encode("utf-8")) > 72:
        raise ValueError("password must be at most 72 bytes")
    return value


def _normalize_email(value: str) -> str:
    # EmailStr only normalizes the domain part; keep the local part case-insensitive too.
    return value.strip().lower()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

    _normalize_email = field_validator("email")(_normalize_email)
    _bcrypt_length = field_validator("password")(_validate_bcrypt_length)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    _normalize_email = field_validator("email")(_normalize_email)
    _bcrypt_length = field_validator("password")(_validate_bcrypt_length)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=128)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    id: UUID
    email: str

    model_config = {"from_attributes": True}
