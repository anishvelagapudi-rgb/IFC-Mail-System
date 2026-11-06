"""Settings from environment variables (and a local .env for development). No secrets in code."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


SUPABASE_URL = _env("SUPABASE_URL").rstrip("/")
SUPABASE_ANON_KEY = _env("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = _env("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_JWT_SECRET = _env("SUPABASE_JWT_SECRET")
STORAGE_BUCKET = _env("STORAGE_BUCKET", "mail-images")

ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
# Cheapest Haiku-class model with image input (see README "Pipeline").
PIPELINE_MODEL = _env("PIPELINE_MODEL", "claude-haiku-5-5")

AUTH_EMAIL_DOMAIN = _env("AUTH_EMAIL_DOMAIN", "users.ifc-mail.invalid")
SMS_PROVIDER = _env("SMS_PROVIDER", "simulated")

SIGNED_URL_TTL = 300  # seconds a photo link stays valid
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
WEB_DIR = ROOT / "web"


def missing() -> list[str]:
    """Required settings that are not set (reported at startup and by /api/health)."""
    req = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_ANON_KEY": SUPABASE_ANON_KEY,
        "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
    }
    return [k for k, v in req.items() if not v]
