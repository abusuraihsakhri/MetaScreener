"""
Web app configuration — all secrets come from environment variables / .env file.
Never hard-code credentials here.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY: str = os.environ["SECRET_KEY"]
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = True

    # Auth
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD")
    if not ADMIN_PASSWORD:
        raise ValueError("FATAL: ADMIN_PASSWORD environment variable must be set for security.")

    # Database
    DB_PATH: str = os.getenv("DB_PATH", "metascreener.db")

    # Uploads
    MAX_CONTENT_LENGTH: int = int(os.getenv("MAX_UPLOAD_MB", 50)) * 1024 * 1024
    UPLOAD_FOLDER: str = os.getenv("UPLOAD_FOLDER", "uploads")
    ALLOWED_EXTENSIONS = {"ris", "bib", "csv", "txt", "pdf"}

    # AI
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "ollama")
    TEMPERATURE_SCREEN: float = float(os.getenv("TEMPERATURE_SCREEN", 0.1))
    TEMPERATURE_EXTRACT: float = float(os.getenv("TEMPERATURE_EXTRACT", 0.0))

    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "mistral")

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    CUSTOM_BASE_URL: str = os.getenv("CUSTOM_BASE_URL", "")
    CUSTOM_API_KEY: str = os.getenv("CUSTOM_API_KEY", "")
    CUSTOM_MODEL: str = os.getenv("CUSTOM_MODEL", "")

    # Rate limiting
    RATE_LIMIT_DEFAULT: str = os.getenv("RATE_LIMIT_DEFAULT", "200 per day, 50 per hour")
    RATE_LIMIT_AI: str = os.getenv("RATE_LIMIT_AI", "30 per hour")
