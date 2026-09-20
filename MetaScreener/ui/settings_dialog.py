import logging

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QStackedWidget,
    QTextEdit, QVBoxLayout, QWidget, QDoubleSpinBox,
)

import config
from modules.ai_client import PROVIDER_LABELS, PROVIDERS, get_provider
from modules.security import save_api_key, load_api_key, keyring_available


# ---------------------------------------------------------------------------
# Background connection test thread
# ---------------------------------------------------------------------------

class _TestThread(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, provider_key: str):
        super().__init__()
        self.provider_key = provider_key

    def run(self):
        config.Config.load()
        # Temporarily use the provider the user is configuring
        old = config.Config.AI_PROVIDER
        config.Config.AI_PROVIDER = self.provider_key
        try:
            provider = get_provider()
            ok, msg = provider.test_connection()
            self.done.emit(ok, msg)
        finally:
            config.Config.AI_PROVIDER = old


# ---------------------------------------------------------------------------
# Per-provider configuration pages
# ---------------------------------------------------------------------------

def _make_group(title: str) -> tuple[QGroupBox, QFormLayout]:
    box = QGroupBox(title)
    form = QFormLayout(box)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    return box, form


class _OllamaPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        box, form = _make_group("Ollama Settings (Local)")

        self.url_edit = QLineEdit(config.Config.OLLAMA_URL)
        form.addRow("Server URL:", self.url_edit)

        model_row = QWidget()
        model_hl = QHBoxLayout(model_row)
        model_hl.setContentsMargins(0, 0, 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.setFixedWidth(90)
        self.btn_refresh.clicked.connect(self._load_models)
        model_hl.addWidget(self.model_combo, 1)
        model_hl.addWidget(self.btn_refresh)
        form.addRow("Model:", model_row)

        self.status_lbl = QLabel("Click Refresh to load models")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #888;")
        form.addRow("", self.status_lbl)

        layout.addWidget(box)
        layout.addStretch()
        self._load_models()

    def _load_models(self):
        try:
            import requests
            base = self.url_edit.text().strip().rstrip("/").replace("/api/generate", "")
            r = requests.get(f"{base}/api/tags", timeout=5)
            if r.status_code == 200:
                names = [m["name"] for m in r.json().get("models", [])]
                self.model_combo.clear()
                self.model_combo.addItems(names)
                current = config.Config.MODEL_NAME
                if current in names:
                    self.model_combo.setCurrentText(current)
                self.status_lbl.setText(f"{len(names)} model(s) available")
                self.status_lbl.setStyleSheet("font-size: 11px; color: #2ECC71;")
                return
        except Exception:
            pass
        self.model_combo.clear()
        self.model_combo.addItem(config.Config.MODEL_NAME)
        self.status_lbl.setText("Ollama not reachable — enter model name manually")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #E74C3C;")

    def apply(self):
        config.Config.OLLAMA_URL = self.url_edit.text().strip()
        config.Config.MODEL_NAME = self.model_combo.currentText().strip()


class _OpenAIPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        box, form = _make_group("OpenAI Settings")

        self.key_edit = QLineEdit(load_api_key("openai"))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-… (stored in OS keyring)")
        form.addRow("API Key:", self.key_edit)

        model_row = QWidget()
        model_hl = QHBoxLayout(model_row)
        model_hl.setContentsMargins(0, 0, 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.setFixedWidth(90)
        self.btn_refresh.clicked.connect(self._load_models)
        model_hl.addWidget(self.model_combo, 1)
        model_hl.addWidget(self.btn_refresh)
        form.addRow("Model:", model_row)

        defaults = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
        self.model_combo.addItems(defaults)
        current = config.Config.OPENAI_MODEL or "gpt-4o-mini"
        if current in defaults:
            self.model_combo.setCurrentText(current)
        else:
            self.model_combo.insertItem(0, current)
            self.model_combo.setCurrentIndex(0)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #888;")
        form.addRow("", self.status_lbl)

        layout.addWidget(box)
        layout.addStretch()

    def _load_models(self):
        key = self.key_edit.text().strip()
        if not key:
            self.status_lbl.setText("Enter your API key first")
            return
        try:
            import requests
            r = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            if r.status_code == 200:
                gpt_models = sorted(
                    [m["id"] for m in r.json().get("data", []) if m["id"].startswith("gpt")],
                    reverse=True,
                )
                if gpt_models:
                    current = self.model_combo.currentText()
                    self.model_combo.clear()
                    self.model_combo.addItems(gpt_models)
                    if current in gpt_models:
                        self.model_combo.setCurrentText(current)
                    self.status_lbl.setText(f"{len(gpt_models)} GPT model(s) fetched")
                    self.status_lbl.setStyleSheet("font-size: 11px; color: #2ECC71;")
                    return
            elif r.status_code == 401:
                self.status_lbl.setText("Invalid API key")
                self.status_lbl.setStyleSheet("font-size: 11px; color: #E74C3C;")
                return
        except Exception:
            pass
        self.status_lbl.setText("Could not fetch models")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #E74C3C;")

    def apply(self):
        key = self.key_edit.text().strip()
        save_api_key("openai", key)
        config.Config.OPENAI_API_KEY = key
        config.Config.OPENAI_MODEL = self.model_combo.currentText().strip()


class _AnthropicPage(QWidget):
    MODELS = [
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-haiku-20240307",
    ]

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        box, form = _make_group("Anthropic Settings")

        self.key_edit = QLineEdit(load_api_key("anthropic"))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-ant-… (stored in OS keyring)")
        form.addRow("API Key:", self.key_edit)

        self.model_combo = QComboBox()
        self.model_combo.addItems(self.MODELS)
        current = config.Config.ANTHROPIC_MODEL or self.MODELS[2]
        if current in self.MODELS:
            self.model_combo.setCurrentText(current)
        form.addRow("Model:", self.model_combo)

        layout.addWidget(box)
        layout.addStretch()

    def apply(self):
        key = self.key_edit.text().strip()
        save_api_key("anthropic", key)
        config.Config.ANTHROPIC_API_KEY = key
        config.Config.ANTHROPIC_MODEL = self.model_combo.currentText().strip()


class _GeminiPage(QWidget):
    MODELS = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ]

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        box, form = _make_group("Google Gemini Settings")

        self.key_edit = QLineEdit(load_api_key("gemini"))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("AIza… (stored in OS keyring)")
        form.addRow("API Key:", self.key_edit)

        model_row = QWidget()
        model_hl = QHBoxLayout(model_row)
        model_hl.setContentsMargins(0, 0, 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(self.MODELS)
        current = config.Config.GEMINI_MODEL or self.MODELS[0]
        if current in self.MODELS:
            self.model_combo.setCurrentText(current)
        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.setFixedWidth(90)
        self.btn_refresh.clicked.connect(self._load_models)
        model_hl.addWidget(self.model_combo, 1)
        model_hl.addWidget(self.btn_refresh)
        form.addRow("Model:", model_row)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #888;")
        form.addRow("", self.status_lbl)

        layout.addWidget(box)
        layout.addStretch()

    def _load_models(self):
        key = self.key_edit.text().strip()
        if not key:
            self.status_lbl.setText("Enter your API key first")
            return
        try:
            import requests
            r = requests.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                timeout=10,
            )
            if r.status_code == 200:
                models = [
                    m["name"].replace("models/", "")
                    for m in r.json().get("models", [])
                    if "gemini" in m.get("name", "").lower()
                ]
                if models:
                    current = self.model_combo.currentText()
                    self.model_combo.clear()
                    self.model_combo.addItems(models)
                    if current in models:
                        self.model_combo.setCurrentText(current)
                    self.status_lbl.setText(f"{len(models)} Gemini model(s) fetched")
                    self.status_lbl.setStyleSheet("font-size: 11px; color: #2ECC71;")
                    return
        except Exception:
            pass
        self.status_lbl.setText("Could not fetch models")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #E74C3C;")

    def apply(self):
        key = self.key_edit.text().strip()
        save_api_key("gemini", key)
        config.Config.GEMINI_API_KEY = key
        config.Config.GEMINI_MODEL = self.model_combo.currentText().strip()


class _CustomPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        box, form = _make_group("OpenAI-Compatible Endpoint (Groq, Together, LM Studio, Mistral API…)")

        self.url_edit = QLineEdit(config.Config.CUSTOM_BASE_URL)
        self.url_edit.setPlaceholderText("https://api.groq.com/openai/v1")
        form.addRow("Base URL:", self.url_edit)

        self.key_edit = QLineEdit(load_api_key("custom"))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Your API key — stored in OS keyring (use 'none' for local)")
        form.addRow("API Key:", self.key_edit)

        model_row = QWidget()
        model_hl = QHBoxLayout(model_row)
        model_hl.setContentsMargins(0, 0, 0, 0)
        self.model_edit = QComboBox()
        self.model_edit.setEditable(True)
        self.model_edit.setPlaceholderText("e.g. llama-3.3-70b-versatile")
        if config.Config.CUSTOM_MODEL:
            self.model_edit.addItem(config.Config.CUSTOM_MODEL)
        self.btn_refresh = QPushButton("⟳ Fetch")
        self.btn_refresh.setFixedWidth(80)
        self.btn_refresh.clicked.connect(self._load_models)
        model_hl.addWidget(self.model_edit, 1)
        model_hl.addWidget(self.btn_refresh)
        form.addRow("Model:", model_row)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #888;")
        form.addRow("", self.status_lbl)

        # Example URLs label
        tip = QLabel(
            "<b>Examples:</b> Groq: <code>https://api.groq.com/openai/v1</code> · "
            "Together: <code>https://api.together.xyz/v1</code> · "
            "LM Studio: <code>http://localhost:1234/v1</code>"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("font-size: 11px; color: #666; margin-top: 4px;")
        layout.addWidget(box)
        layout.addWidget(tip)
        layout.addStretch()

    def _load_models(self):
        url = self.url_edit.text().strip().rstrip("/")
        key = self.key_edit.text().strip() or "none"
        if not url:
            self.status_lbl.setText("Enter Base URL first")
            return
        try:
            import requests
            r = requests.get(
                f"{url}/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    models = [m.get("id", "") for m in data.get("data", [])]
                else:
                    models = [m.get("id", str(m)) for m in data]
                models = [m for m in models if m]
                if models:
                    current = self.model_edit.currentText()
                    self.model_edit.clear()
                    self.model_edit.addItems(models)
                    if current in models:
                        self.model_edit.setCurrentText(current)
                    self.status_lbl.setText(f"{len(models)} model(s) fetched")
                    self.status_lbl.setStyleSheet("font-size: 11px; color: #2ECC71;")
                    return
        except Exception:
            pass
        self.status_lbl.setText("Could not fetch models — enter name manually")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #E74C3C;")

    def apply(self):
        key = self.key_edit.text().strip()
        save_api_key("custom", key)
        config.Config.CUSTOM_BASE_URL = self.url_edit.text().strip()
        config.Config.CUSTOM_API_KEY = key
        config.Config.CUSTOM_MODEL = self.model_edit.currentText().strip()


# ---------------------------------------------------------------------------
# Main settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(620, 600)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        # --- Screening criteria ---
        crit_box, crit_form = _make_group("Screening Criteria")
        self.inclusion_edit = QTextEdit()
        self.inclusion_edit.setFixedHeight(70)
        self.inclusion_edit.setPlainText(config.Config.INCLUSION_CRITERIA)
        crit_form.addRow("Inclusion:", self.inclusion_edit)

        self.exclusion_edit = QTextEdit()
        self.exclusion_edit.setFixedHeight(70)
        self.exclusion_edit.setPlainText(config.Config.EXCLUSION_CRITERIA)
        crit_form.addRow("Exclusion:", self.exclusion_edit)
        root.addWidget(crit_box)

        # --- Keyring status ---
        if keyring_available():
            kr_lbl = QLabel("🔒 API keys stored securely in OS keyring (Windows Credential Manager)")
            kr_lbl.setStyleSheet("font-size: 11px; color: #2ECC71; padding: 4px 0;")
        else:
            kr_lbl = QLabel("⚠ keyring not installed — run: pip install keyring  (API keys will be in memory only)")
            kr_lbl.setStyleSheet("font-size: 11px; color: #E67E22; padding: 4px 0;")
        kr_lbl.setWordWrap(True)
        root.addWidget(kr_lbl)

        # --- Provider selector ---
        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("AI Provider:"))
        self.provider_combo = QComboBox()
        for key, label in PROVIDER_LABELS.items():
            self.provider_combo.addItem(label, key)
        current_provider = config.Config.AI_PROVIDER or "ollama"
        idx = self.provider_combo.findData(current_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_row.addWidget(self.provider_combo, 1)
        root.addLayout(provider_row)

        # --- Provider-specific pages ---
        self._pages = {
            "ollama": _OllamaPage(),
            "openai": _OpenAIPage(),
            "anthropic": _AnthropicPage(),
            "gemini": _GeminiPage(),
            "openai_compatible": _CustomPage(),
        }
        self.stack = QStackedWidget()
        for key in PROVIDER_LABELS:
            self.stack.addWidget(self._pages[key])
        root.addWidget(self.stack)

        # --- Temperature ---
        temp_box, temp_form = _make_group("Temperature (lower = more deterministic)")
        self.temp_screen = QDoubleSpinBox()
        self.temp_screen.setRange(0.0, 2.0)
        self.temp_screen.setSingleStep(0.05)
        self.temp_screen.setDecimals(2)
        self.temp_screen.setValue(config.Config.TEMPERATURE_SCREEN)
        temp_form.addRow("Screening:", self.temp_screen)

        self.temp_extract = QDoubleSpinBox()
        self.temp_extract.setRange(0.0, 2.0)
        self.temp_extract.setSingleStep(0.05)
        self.temp_extract.setDecimals(2)
        self.temp_extract.setValue(config.Config.TEMPERATURE_EXTRACT)
        temp_form.addRow("Extraction:", self.temp_extract)
        root.addWidget(temp_box)

        # --- Test + Save / Cancel ---
        btn_row = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._test_connection)
        self.test_lbl = QLabel("")
        self.test_lbl.setStyleSheet("font-size: 11px;")
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")
        self.save_btn.clicked.connect(self._save)
        self.cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(self.test_btn)
        btn_row.addWidget(self.test_lbl, 1)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)
        root.addLayout(btn_row)

        self._sync_stack()

    # ------------------------------------------------------------------

    def _on_provider_changed(self):
        self._sync_stack()

    def _sync_stack(self):
        key = self.provider_combo.currentData()
        keys = list(PROVIDER_LABELS.keys())
        if key in keys:
            self.stack.setCurrentIndex(keys.index(key))

    def _current_provider_key(self) -> str:
        return self.provider_combo.currentData() or "ollama"

    def _test_connection(self):
        self.test_btn.setEnabled(False)
        self.test_lbl.setText("Testing…")
        self.test_lbl.setStyleSheet("font-size: 11px; color: #888;")

        # Apply current page values to config temporarily
        self._apply_page(self._current_provider_key())

        self._test_thread = _TestThread(self._current_provider_key())
        self._test_thread.done.connect(self._on_test_done)
        self._test_thread.start()

    def _on_test_done(self, ok: bool, msg: str):
        self.test_btn.setEnabled(True)
        color = "#2ECC71" if ok else "#E74C3C"
        icon = "✓" if ok else "✗"
        self.test_lbl.setText(f"{icon} {msg}")
        self.test_lbl.setStyleSheet(f"font-size: 11px; color: {color};")

    def _apply_page(self, key: str):
        """Write the current page's UI values into Config (without saving to disk)."""
        page = self._pages.get(key)
        if page and hasattr(page, "apply"):
            page.apply()

    def _save(self):
        try:
            config.Config.INCLUSION_CRITERIA = self.inclusion_edit.toPlainText()
            config.Config.EXCLUSION_CRITERIA = self.exclusion_edit.toPlainText()
            config.Config.AI_PROVIDER = self._current_provider_key()
            config.Config.TEMPERATURE_SCREEN = self.temp_screen.value()
            config.Config.TEMPERATURE_EXTRACT = self.temp_extract.value()

            # Apply all pages (not just the visible one) so nothing is lost
            for key in PROVIDER_LABELS:
                self._apply_page(key)

            config.Config.save()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")
