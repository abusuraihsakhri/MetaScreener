"""
Backward-compatible shim over the unified ai_client module.
All screening and extraction now routes through ai_client.get_provider().
"""

import logging
import time

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from config import Config
from modules.ai_client import (
    get_provider,
    screen_abstract as _screen_abstract,
    extract_fields as _extract_fields,
    _keyword_fallback,
    OllamaProvider,
)


# ---------------------------------------------------------------------------
# OllamaClient — kept for any code that still imports it directly
# ---------------------------------------------------------------------------

class OllamaClient:
    def __init__(self):
        Config.load()
        self._provider = OllamaProvider()
        self.model = self._resolve_model_name()

    def _resolve_model_name(self) -> str:
        try:
            names = self._provider.list_models()
            if not names:
                return Config.MODEL_NAME
            configured = Config.MODEL_NAME.lower().strip()
            for name in names:
                if name.lower() == configured:
                    return name
            for name in names:
                if configured.split(":")[0] in name.lower():
                    Config.MODEL_NAME = name
                    Config.save()
                    return name
            fallback = names[0]
            Config.MODEL_NAME = fallback
            Config.save()
            return fallback
        except Exception as e:
            logging.error(f"Model resolution error: {e}")
            return Config.MODEL_NAME

    def check_connection(self) -> bool:
        ok, _ = self._provider.test_connection()
        return ok

    def check_model_available(self) -> tuple[bool, str | None]:
        try:
            names = self._provider.list_models()
            if not names:
                return False, None
            for name in names:
                if Config.MODEL_NAME.lower() in name.lower():
                    return True, name
            first = names[0]
            Config.MODEL_NAME = first
            return True, first
        except Exception as e:
            logging.error(f"check_model_available error: {e}")
            return False, None

    def _generate(self, prompt: str, temperature: float):
        return self._provider.generate(prompt, temperature)


# ---------------------------------------------------------------------------
# Screener — now delegates to unified ai_client
# ---------------------------------------------------------------------------

class Screener:
    def __init__(self):
        self.client = OllamaClient()  # kept for compatibility

    def screen_abstract(self, title: str, abstract: str) -> dict:
        return _screen_abstract(title, abstract)

    def screen_batch(self, papers_list: list, progress_callback=None) -> list:
        results = []
        total = len(papers_list)
        for i, paper in enumerate(papers_list):
            res = self.screen_abstract(paper.get("title", ""), paper.get("abstract", ""))
            res["paper_id"] = paper.get("id")
            results.append(res)
            if progress_callback:
                progress_callback(i + 1, total)
            time.sleep(0.3)
        return results


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class Extractor:
    def __init__(self):
        self.client = OllamaClient()  # kept for compatibility

    def extract_fields(self, pdf_text: str, field_names: list) -> dict:
        return _extract_fields(pdf_text, field_names)


# ---------------------------------------------------------------------------
# Status worker (checks the currently configured provider)
# ---------------------------------------------------------------------------

class OllamaStatusWorker(QThread):
    status_ready = pyqtSignal(bool, object)

    def run(self):
        Config.load()
        provider = get_provider()
        ok, message = provider.test_connection()
        if ok:
            models = provider.list_models()
            model_name = models[0] if models else Config.MODEL_NAME
            self.status_ready.emit(True, model_name)
        else:
            logging.warning(f"AI provider connection failed: {message}")
            self.status_ready.emit(False, None)
