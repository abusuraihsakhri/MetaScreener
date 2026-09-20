"""
Unified multi-provider AI client for the web app.
Reads all credentials from Config (env vars) — no plaintext JSON.
"""
import json
import logging
import re
import time
from typing import Optional

import requests
from config import Config


# ---------------------------------------------------------------------------
# Robust JSON extraction
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    for strategy in [
        lambda t: json.loads(t),
        lambda t: json.loads(re.sub(r"```(?:json)?", "", t).strip().rstrip("`")),
        lambda t: json.loads(re.search(r"\{[\s\S]*?\}", t).group()) if re.search(r"\{[\s\S]*?\}", t) else (_ for _ in ()).throw(ValueError()),
        lambda t: json.loads(t[t.find("{"):t.rfind("}") + 1]) if "{" in t else (_ for _ in ()).throw(ValueError()),
    ]:
        try:
            return strategy(text)
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class _OllamaProvider:
    def generate(self, prompt: str, temperature: float) -> Optional[str]:
        url = Config.OLLAMA_URL
        payload = {
            "model": Config.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature, "num_predict": 1000, "num_ctx": 4096},
        }
        try:
            r = requests.post(url, json=payload, timeout=180)
            if r.status_code == 200:
                return r.json().get("response", "").strip()
            logging.error(f"Ollama HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logging.error(f"Ollama error: {e}")
        return None

    def list_models(self) -> list:
        base = Config.OLLAMA_URL.replace("/api/generate", "")
        try:
            r = requests.get(f"{base}/api/tags", timeout=5)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
        return []

    def test(self) -> tuple:
        base = Config.OLLAMA_URL.replace("/api/generate", "")
        try:
            r = requests.get(f"{base}/api/tags", timeout=5)
            if r.status_code == 200:
                n = len(r.json().get("models", []))
                return True, f"Connected — {n} model(s)"
        except Exception as e:
            return False, str(e)
        return False, "Unreachable"


class _OpenAIProvider:
    def generate(self, prompt: str, temperature: float) -> Optional[str]:
        if not Config.OPENAI_API_KEY:
            return None
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {Config.OPENAI_API_KEY}"},
                json={
                    "model": Config.OPENAI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": 1000,
                    "response_format": {"type": "json_object"},
                },
                timeout=60,
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            logging.error(f"OpenAI HTTP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            logging.error(f"OpenAI error: {e}")
        return None

    def list_models(self) -> list:
        if not Config.OPENAI_API_KEY:
            return ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
        try:
            r = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {Config.OPENAI_API_KEY}"},
                timeout=10,
            )
            if r.status_code == 200:
                return sorted(
                    [m["id"] for m in r.json().get("data", []) if m["id"].startswith("gpt")],
                    reverse=True,
                )
        except Exception:
            pass
        return ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]

    def test(self) -> tuple:
        if not Config.OPENAI_API_KEY:
            return False, "API key not set"
        try:
            r = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {Config.OPENAI_API_KEY}"},
                timeout=10,
            )
            if r.status_code == 200:
                return True, "OpenAI connected"
            if r.status_code == 401:
                return False, "Invalid API key"
        except Exception as e:
            return False, str(e)
        return False, "Unknown error"


class _AnthropicProvider:
    def generate(self, prompt: str, temperature: float) -> Optional[str]:
        if not Config.ANTHROPIC_API_KEY:
            return None
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": Config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": Config.ANTHROPIC_MODEL,
                    "max_tokens": 1024,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            if r.status_code == 200:
                return r.json()["content"][0]["text"]
            logging.error(f"Anthropic HTTP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            logging.error(f"Anthropic error: {e}")
        return None

    def list_models(self) -> list:
        return [
            "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
            "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
        ]

    def test(self) -> tuple:
        if not Config.ANTHROPIC_API_KEY:
            return False, "API key not set"
        try:
            r = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": Config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10,
            )
            if r.status_code == 200:
                return True, "Anthropic connected"
            if r.status_code == 401:
                return False, "Invalid API key"
        except Exception as e:
            return False, str(e)
        return False, "Unknown error"


class _GeminiProvider:
    def generate(self, prompt: str, temperature: float) -> Optional[str]:
        if not Config.GEMINI_API_KEY:
            return None
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{Config.GEMINI_MODEL}:generateContent?key={Config.GEMINI_API_KEY}"
        )
        try:
            r = requests.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": 1000,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=60,
            )
            if r.status_code == 200:
                return (
                    r.json()
                    .get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
            logging.error(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            logging.error(f"Gemini error: {e}")
        return None

    def list_models(self) -> list:
        return ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"]

    def test(self) -> tuple:
        if not Config.GEMINI_API_KEY:
            return False, "API key not set"
        try:
            r = requests.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={Config.GEMINI_API_KEY}",
                timeout=10,
            )
            if r.status_code == 200:
                return True, "Gemini connected"
            if r.status_code == 400:
                return False, "Invalid API key"
        except Exception as e:
            return False, str(e)
        return False, "Unknown error"


class _CustomProvider:
    def generate(self, prompt: str, temperature: float) -> Optional[str]:
        if not Config.CUSTOM_BASE_URL:
            return None
        try:
            r = requests.post(
                f"{Config.CUSTOM_BASE_URL.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {Config.CUSTOM_API_KEY or 'none'}"},
                json={
                    "model": Config.CUSTOM_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": 1000,
                },
                timeout=60,
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            logging.error(f"Custom provider HTTP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            logging.error(f"Custom provider error: {e}")
        return None

    def list_models(self) -> list:
        if not Config.CUSTOM_BASE_URL:
            return []
        try:
            r = requests.get(
                f"{Config.CUSTOM_BASE_URL.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {Config.CUSTOM_API_KEY or 'none'}"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                items = data.get("data", data) if isinstance(data, dict) else data
                return [m.get("id", str(m)) for m in items if isinstance(m, dict)]
        except Exception:
            pass
        return []

    def test(self) -> tuple:
        if not Config.CUSTOM_BASE_URL:
            return False, "Base URL not set"
        try:
            r = requests.get(
                f"{Config.CUSTOM_BASE_URL.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {Config.CUSTOM_API_KEY or 'none'}"},
                timeout=10,
            )
            if r.status_code == 200:
                return True, "Custom endpoint connected"
            return False, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)


_PROVIDERS = {
    "ollama": _OllamaProvider,
    "openai": _OpenAIProvider,
    "anthropic": _AnthropicProvider,
    "gemini": _GeminiProvider,
    "openai_compatible": _CustomProvider,
}

PROVIDER_LABELS = {
    "ollama": "Ollama (Local)",
    "openai": "OpenAI (GPT-4o / GPT-3.5)",
    "anthropic": "Anthropic (Claude)",
    "gemini": "Google Gemini",
    "openai_compatible": "OpenAI-Compatible (Groq, Together, LM Studio…)",
}


def get_provider():
    return _PROVIDERS.get(Config.AI_PROVIDER, _OllamaProvider)()


def _retry(provider, prompt: str, temperature: float, retries: int = 3) -> Optional[str]:
    delay = 2
    for i in range(retries):
        raw = provider.generate(prompt, temperature)
        if raw is not None:
            return raw
        if i < retries - 1:
            time.sleep(delay)
            delay *= 2
    return None


def _keyword_fallback(title: str, abstract: str) -> dict:
    from config import Config
    text = (title + " " + abstract).lower()
    incl_kw = [w for w in re.split(r"[\s,;]+", Config.INCLUSION_CRITERIA.lower()) if len(w) > 3]
    excl_kw = [w for w in re.split(r"[\s,;]+", Config.EXCLUSION_CRITERIA.lower()) if len(w) > 3]
    incl = sum(1 for k in incl_kw if k in text)
    excl = sum(1 for k in excl_kw if k in text)
    if excl > 0 and incl == 0:
        return {"decision": "exclude", "confidence": 55, "reason": f"Keyword: {excl} exclusion term(s)"}
    if incl > 0:
        return {"decision": "uncertain", "confidence": 40, "reason": f"Keyword: {incl} inclusion term(s) — review needed"}
    return {"decision": "uncertain", "confidence": 20, "reason": "No criteria matched — manual review needed"}


def screen_abstract(title: str, abstract: str) -> dict:
    from config import Config
    inclusion = getattr(Config, "INCLUSION_CRITERIA", "relevant clinical studies")
    exclusion = getattr(Config, "EXCLUSION_CRITERIA", "none specified")

    prompt = (
        "You are a systematic review screener. Respond ONLY with valid JSON.\n\n"
        f"Inclusion criteria: {inclusion}\n"
        f"Exclusion criteria: {exclusion}\n\n"
        f"Title: {title or 'Unknown'}\n"
        f"Abstract: {(abstract or 'No abstract')[:1200]}\n\n"
        'JSON keys required:\n'
        '  "decision": "include" | "exclude" | "uncertain"\n'
        '  "confidence": integer 0-100\n'
        '  "reason": string max 20 words\n'
    )
    provider = get_provider()
    raw = _retry(provider, prompt, Config.TEMPERATURE_SCREEN)
    if raw:
        parsed = _extract_json(raw)
        if parsed:
            decision = str(parsed.get("decision", "uncertain")).lower()
            if decision in ("include", "exclude", "uncertain"):
                try:
                    conf = int(parsed.get("confidence", 0))
                except Exception:
                    conf = 0
                return {"decision": decision, "confidence": conf,
                        "reason": str(parsed.get("reason", ""))}
    return _keyword_fallback(str(title or ""), str(abstract or ""))


def extract_fields(pdf_text: str, field_names: list) -> dict:
    from config import Config
    schema = {f: "extracted value or null" for f in field_names}
    prompt = (
        "Extract the following fields from the paper. "
        "Return ONLY valid JSON. Use null for missing fields.\n\n"
        f"Schema:\n{json.dumps(schema, indent=2)}\n\n"
        f"Paper text:\n{pdf_text[:6000]}"
    )
    provider = get_provider()
    raw = _retry(provider, prompt, Config.TEMPERATURE_EXTRACT)
    default = {f: None for f in field_names}
    if raw:
        parsed = _extract_json(raw)
        if parsed:
            return {f: parsed.get(f) for f in field_names}
    return default
