import json
import logging
import os


class Config:
    # Database & settings files
    DB_PATH = "metascreener.db"
    SETTINGS_FILE = "metascreener_settings.json"

    # Screening criteria
    INCLUSION_CRITERIA = ""
    EXCLUSION_CRITERIA = ""

    # AI provider: "ollama" | "openai" | "anthropic" | "gemini" | "openai_compatible"
    AI_PROVIDER = "ollama"

    # Temperature
    TEMPERATURE_SCREEN = 0.1
    TEMPERATURE_EXTRACT = 0.0

    # --- Ollama (non-sensitive) ---
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL_NAME = "mistral"

    # --- OpenAI ---
    OPENAI_API_KEY = ""          # loaded from keyring at runtime
    OPENAI_MODEL = "gpt-4o-mini"

    # --- Anthropic ---
    ANTHROPIC_API_KEY = ""       # loaded from keyring at runtime
    ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

    # --- Google Gemini ---
    GEMINI_API_KEY = ""          # loaded from keyring at runtime
    GEMINI_MODEL = "gemini-2.0-flash"

    # --- OpenAI-compatible ---
    CUSTOM_BASE_URL = ""
    CUSTOM_API_KEY = ""          # loaded from keyring at runtime
    CUSTOM_MODEL = ""

    @classmethod
    def save(cls):
        """
        Persist non-sensitive settings to JSON.
        API keys are saved to the OS keyring by the caller (settings_dialog).
        """
        data = {
            "INCLUSION_CRITERIA": cls.INCLUSION_CRITERIA,
            "EXCLUSION_CRITERIA": cls.EXCLUSION_CRITERIA,
            "AI_PROVIDER": cls.AI_PROVIDER,
            "TEMPERATURE_SCREEN": cls.TEMPERATURE_SCREEN,
            "TEMPERATURE_EXTRACT": cls.TEMPERATURE_EXTRACT,
            # Ollama
            "OLLAMA_URL": cls.OLLAMA_URL,
            "MODEL_NAME": cls.MODEL_NAME,
            # Non-sensitive model/URL fields only — NO API KEYS
            "OPENAI_MODEL": cls.OPENAI_MODEL,
            "ANTHROPIC_MODEL": cls.ANTHROPIC_MODEL,
            "GEMINI_MODEL": cls.GEMINI_MODEL,
            "CUSTOM_BASE_URL": cls.CUSTOM_BASE_URL,
            "CUSTOM_MODEL": cls.CUSTOM_MODEL,
        }
        try:
            with open(cls.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as exc:
            logging.error(f"Config save error: {exc}")

    @classmethod
    def load(cls):
        """Load non-sensitive settings from JSON, then API keys from keyring."""
        if os.path.exists(cls.SETTINGS_FILE):
            try:
                with open(cls.SETTINGS_FILE, encoding="utf-8") as f:
                    data = json.load(f)

                cls.INCLUSION_CRITERIA = data.get("INCLUSION_CRITERIA", cls.INCLUSION_CRITERIA)
                cls.EXCLUSION_CRITERIA = data.get("EXCLUSION_CRITERIA", cls.EXCLUSION_CRITERIA)
                cls.AI_PROVIDER = data.get("AI_PROVIDER", cls.AI_PROVIDER)
                cls.TEMPERATURE_SCREEN = float(data.get("TEMPERATURE_SCREEN", cls.TEMPERATURE_SCREEN))
                cls.TEMPERATURE_EXTRACT = float(data.get("TEMPERATURE_EXTRACT", cls.TEMPERATURE_EXTRACT))
                cls.OLLAMA_URL = data.get("OLLAMA_URL", cls.OLLAMA_URL)
                cls.MODEL_NAME = data.get("MODEL_NAME", cls.MODEL_NAME)
                cls.OPENAI_MODEL = data.get("OPENAI_MODEL", cls.OPENAI_MODEL)
                cls.ANTHROPIC_MODEL = data.get("ANTHROPIC_MODEL", cls.ANTHROPIC_MODEL)
                cls.GEMINI_MODEL = data.get("GEMINI_MODEL", cls.GEMINI_MODEL)
                cls.CUSTOM_BASE_URL = data.get("CUSTOM_BASE_URL", cls.CUSTOM_BASE_URL)
                cls.CUSTOM_MODEL = data.get("CUSTOM_MODEL", cls.CUSTOM_MODEL)

                # --- Migrate plaintext keys written by older versions ---
                # If an old settings file has API keys in JSON, move them to keyring then scrub.
                cls._migrate_legacy_keys(data)

            except (json.JSONDecodeError, OSError, ValueError) as exc:
                logging.error(f"Config load error: {exc}")

        # Load API keys from OS keyring
        cls._load_keys_from_keyring()

    @classmethod
    def _load_keys_from_keyring(cls):
        from modules.security import load_api_key
        cls.OPENAI_API_KEY    = load_api_key("openai")
        cls.ANTHROPIC_API_KEY = load_api_key("anthropic")
        cls.GEMINI_API_KEY    = load_api_key("gemini")
        cls.CUSTOM_API_KEY    = load_api_key("custom")

    @classmethod
    def _migrate_legacy_keys(cls, data: dict):
        """One-time migration: move plaintext keys from old JSON into keyring, then rewrite JSON."""
        from modules.security import save_api_key, keyring_available
        if not keyring_available():
            return

        migrated = False
        for provider, json_key in [
            ("openai",    "OPENAI_API_KEY"),
            ("anthropic", "ANTHROPIC_API_KEY"),
            ("gemini",    "GEMINI_API_KEY"),
            ("custom",    "CUSTOM_API_KEY"),
        ]:
            value = data.get(json_key, "")
            if value:
                save_api_key(provider, value)
                migrated = True
                logging.info(f"Migrated {json_key} from JSON to OS keyring")

        if migrated:
            # Rewrite JSON without the keys
            cls.save()
            logging.info("Rewrote settings file — API keys removed from JSON")
