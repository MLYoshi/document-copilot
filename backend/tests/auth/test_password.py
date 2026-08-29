import pytest

from app.auth.password import hash_password, verify_password

pytestmark = pytest.mark.asyncio


async def test_hash_and_verify_roundtrip():
    h = await hash_password("s3cret-password")
    assert h != "s3cret-password"
    assert await verify_password("s3cret-password", h)


async def test_wrong_password_rejected():
    h = await hash_password("s3cret-password")
    assert not await verify_password("wrong", h)


async def test_hashes_are_salted():
    assert await hash_password("same") != await hash_password("same")


async def test_multibyte_password_roundtrip():
    """72 bytes is bcrypt's hard limit; multibyte input below it must work."""
    password = "密" * 24  # 24 chars = 72 bytes exactly
    h = await hash_password(password)
    assert await verify_password(password, h)
