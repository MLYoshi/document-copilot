from supabase import AsyncClient

from app.core.config import settings


def get_supabase_client() -> AsyncClient:
    return AsyncClient(settings.supabase_url, settings.supabase_anon_key)


def get_supabase_admin_client() -> AsyncClient:
    if not settings.supabase_service_role_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for admin operations")
    return AsyncClient(settings.supabase_url, settings.supabase_service_role_key)
