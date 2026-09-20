from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app import limiter
from services import screener

screening_bp = Blueprint("screening", __name__)


@screening_bp.route("/screening")
@login_required
def index():
    stats = screener.get_stats()
    papers = screener.get_pending_papers()
    current = papers[0] if papers else None
    return render_template("screening.html", stats=stats, paper=current,
                           remaining=len(papers))


@screening_bp.route("/screening/decide", methods=["POST"])
@login_required
def decide():
    paper_id = request.form.get("paper_id", type=int)
    decision = request.form.get("decision", "")
    reason = request.form.get("reason", "")
    if paper_id and decision in ("include", "exclude", "uncertain"):
        screener.save_decision(paper_id, decision, reason)
    return redirect(url_for("screening.index"))


@screening_bp.route("/screening/undo", methods=["POST"])
@login_required
def undo():
    undone = screener.undo_last()
    if undone:
        flash(f"Undone: '{(undone.get('title') or '')[:60]}'", "info")
    return redirect(url_for("screening.index"))


@screening_bp.route("/screening/ai_suggest/<int:paper_id>", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def ai_suggest(paper_id: int):
    """AJAX endpoint — returns AI screening suggestion as JSON."""
    try:
        result = screener.ai_screen_paper(paper_id)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
