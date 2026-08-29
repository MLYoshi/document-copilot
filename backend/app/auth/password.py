import bcrypt
from starlette.concurrency import run_in_threadpool


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# bcrypt costs ~200-300ms of CPU; run it off the event loop.
async def hash_password(password: str) -> str:
    return await run_in_threadpool(_hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await run_in_threadpool(_verify, password, password_hash)
