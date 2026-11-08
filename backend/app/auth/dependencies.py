from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from supabase_auth.types import User

from app.auth import service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    return await service.get_user(token)
