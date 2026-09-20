"""
MetaScreener Web — Flask application factory.
Run: flask run  (or: python app.py for development)
"""
import logging
import logging.handlers
import os

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS

from config import Config
from services.database import init_db

# Global extensions
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
login_manager = LoginManager()
cors = CORS()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # ── Logging ────────────────────────────────────────────────────────────
    handler = logging.handlers.RotatingFileHandler(
        "metascreener_web.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    # ── Extensions ─────────────────────────────────────────────────────────
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access MetaScreener."
    login_manager.login_message_category = "info"
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})

    # ── Ensure upload dir exists ───────────────────────────────────────────
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ── Database ───────────────────────────────────────────────────────────
    with app.app_context():
        init_db()

    # ── Blueprints ─────────────────────────────────────────────────────────
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.papers import papers_bp
    from routes.screening import screening_bp
    from routes.dedup import dedup_bp
    from routes.export import export_bp
    from routes.settings import settings_bp
    from routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(papers_bp)
    app.register_blueprint(screening_bp)
    app.register_blueprint(dedup_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    csrf.exempt(api_bp)

    return app


# ── User model (simple single-user auth) ───────────────────────────────────

from flask_login import UserMixin


class User(UserMixin):
    id = "admin"

    @staticmethod
    def check_password(password: str) -> bool:
        from werkzeug.security import check_password_hash
        from services.database import get_db
        with get_db() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key='admin_pw_hash'").fetchone()
        if row:
            return check_password_hash(row["value"], password)
        # Fallback for first run
        return password == Config.ADMIN_PASSWORD


@login_manager.user_loader
def load_user(user_id: str):
    if user_id == "admin":
        return User()
    return None


if __name__ == "__main__":
    app = create_app()
    app.run(debug=False, host="0.0.0.0", port=5000)
