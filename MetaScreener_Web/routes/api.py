"""
REST API blueprint — JSON endpoints for programmatic access.
All routes require login (session-based) or can be extended with token auth.
"""
from flask import Blueprint, jsonify, request, current_app
from functools import wraps
import jwt
from app import limiter
from services import screener, deduplicator, exporter

api_bp = Blueprint("api", __name__)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid token"}), 401
        token = auth_header.split(" ")[1]
        try:
            jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401
        return f(*args, **kwargs)
    return decorated


@api_bp.route("/stats")
@token_required
def stats():
    return jsonify({
        "screening": screener.get_stats(),
        "dedup": deduplicator.get_stats(),
        "prisma": exporter.prisma_counts(),
    })


@api_bp.route("/papers")
@token_required
def papers():
    decision = request.args.get("decision")
    return jsonify(screener.get_all_papers(decision_filter=decision))


@api_bp.route("/papers/<int:paper_id>")
@token_required
def paper_detail(paper_id: int):
    p = screener.get_paper(paper_id)
    if not p:
        return jsonify({"error": "Not found"}), 404
    return jsonify(p)


@api_bp.route("/papers/<int:paper_id>/decide", methods=["POST"])
@token_required
def decide(paper_id: int):
    data = request.get_json(silent=True) or {}
    decision = data.get("decision", "")
    reason = data.get("reason", "")
    if decision not in ("include", "exclude", "uncertain", "pending"):
        return jsonify({"error": "Invalid decision"}), 400
    screener.save_decision(paper_id, decision, reason)
    return jsonify({"ok": True})


@api_bp.route("/papers/<int:paper_id>/ai_screen", methods=["POST"])
@token_required
@limiter.limit("30 per hour")
def ai_screen(paper_id: int):
    try:
        result = screener.ai_screen_paper(paper_id)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/duplicates")
@token_required
def duplicates():
    return jsonify(deduplicator.find_duplicates())
