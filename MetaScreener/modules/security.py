"""
Secure credential storage using the OS keyring (Windows Credential Manager,
macOS Keychain, Linux Secret Service).

API keys are stored here — never written to metascreener_settings.json.
Non-sensitive settings (model names, URLs, criteria) stay in the JSON file.
"""
import logging

try:
    import keyring
    _KEYRING_OK = True
except ImportError:
    _KEYRING_OK = False
    logging.warning("keyring not installed — API keys will not be stored securely. Run: pip install keyring")

_SERVICE = "MetaScreener"

# Credential names stored in keyring
_KEYS = {
    "openai":    "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini":    "gemini_api_key",
    "custom":    "custom_api_key",
}


def save_api_key(provider: str, key: str) -> bool:
    """Store an API key in the OS keyring. Returns True on success."""
    name = _KEYS.get(provider)
    if not name:
        logging.error(f"Unknown provider for keyring: {provider}")
        return False
    if not _KEYRING_OK:
        logging.warning("keyring unavailable — API key not saved securely")
        return False
    try:
        if key:
            keyring.set_password(_SERVICE, name, key)
        else:
            # Deleting an empty key avoids stale entries
            try:
                keyring.delete_password(_SERVICE, name)
            except keyring.errors.PasswordDeleteError:
                pass
        return True
    except Exception as exc:
        logging.error(f"keyring save error ({provider}): {exc}")
        return False


def load_api_key(provider: str) -> str:
    """Retrieve an API key from the OS keyring. Returns '' if not found."""
    name = _KEYS.get(provider)
    if not name or not _KEYRING_OK:
        return ""
    try:
        value = keyring.get_password(_SERVICE, name)
        return value or ""
    except Exception as exc:
        logging.error(f"keyring load error ({provider}): {exc}")
        return ""


def delete_api_key(provider: str) -> bool:
    name = _KEYS.get(provider)
    if not name or not _KEYRING_OK:
        return False
    try:
        keyring.delete_password(_SERVICE, name)
        return True
    except Exception:
        return False


def keyring_available() -> bool:
    return _KEYRING_OK
