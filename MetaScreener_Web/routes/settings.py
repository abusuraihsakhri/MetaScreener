from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required
from services.ai_client import get_provider, PROVIDER_LABELS

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings")
@login_required
def index():
    from config import Config
    return render_template("settings.html",
                           provider_labels=PROVIDER_LABELS,
                           config=Config)


@settings_bp.route("/settings/test_connection", methods=["POST"])
@login_required
def test_connection():
    provider = get_provider()
    ok, msg = provider.test()
    return jsonify({"ok": ok, "message": msg})


@settings_bp.route("/settings/list_models", methods=["POST"])
@login_required
def list_models():
    provider = get_provider()
    models = provider.list_models()
    return jsonify({"models": models})
