import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create(session: AsyncSession, email: str, password_hash: str) -> User:
    """Insert a new user. Raises ``UserEmailTakenError`` on duplicate email."""
    user = User(email=email, password_hash=password_hash)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise UserEmailTakenError(email) from exc
    await session.refresh(user)
    return user


class UserEmailTakenError(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"email already registered: {email}")
        self.email = email
