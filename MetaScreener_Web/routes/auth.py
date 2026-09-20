from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required
import jwt
import datetime
from app import User, limiter
from config import Config

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/api/login", methods=["POST"])
@limiter.limit("10 per minute")
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    if username == Config.ADMIN_USERNAME and User.check_password(password):
        token = jwt.encode(
            {
                "sub": username,
                "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            },
            current_app.config["SECRET_KEY"],
            algorithm="HS256"
        )
        return jsonify({"token": token})
    return jsonify({"error": "Invalid credentials"}), 401


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == Config.ADMIN_USERNAME and User.check_password(password):
            login_user(User(), remember=False)
            next_page = request.args.get("next") or url_for("dashboard.index")
            # Prevent open-redirect
            if next_page and not next_page.startswith("/"):
                next_page = url_for("dashboard.index")
            return redirect(next_page)
        flash("Invalid credentials.", "danger")
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
