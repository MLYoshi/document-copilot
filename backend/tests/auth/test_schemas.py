import pytest
from pydantic import ValidationError

from app.auth.schemas import LoginRequest, RegisterRequest


def test_register_accepts_valid_payload():
    body = RegisterRequest(email="Analyst@Example.COM", password="password123")
    # local part is case-insensitive for us; domain is normalized by EmailStr
    assert body.email == "analyst@example.com"


def test_register_rejects_short_password():
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@example.com", password="short")


def test_register_rejects_password_over_72_bytes():
    # 30 chars but 90 bytes in UTF-8: pydantic max_length alone would miss this.
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@example.com", password="密" * 30)


def test_register_accepts_exactly_72_bytes():
    body = RegisterRequest(email="a@example.com", password="密" * 24)
    assert len(body.password.encode("utf-8")) == 72


def test_login_normalizes_email_and_bounds_password():
    body = LoginRequest(email="User@Example.com", password="a" * 72)
    assert body.email == "user@example.com"
    with pytest.raises(ValidationError):
        LoginRequest(email="a@example.com", password="a" * 73)
