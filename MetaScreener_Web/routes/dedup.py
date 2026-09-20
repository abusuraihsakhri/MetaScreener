from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from services import deduplicator

dedup_bp = Blueprint("dedup", __name__)


@dedup_bp.route("/deduplicate")
@login_required
def index():
    stats = deduplicator.get_stats()
    groups = deduplicator.find_duplicates()
    return render_template("dedup.html", stats=stats, groups=groups)


@dedup_bp.route("/deduplicate/resolve", methods=["POST"])
@login_required
def resolve():
    keep_ids_raw = request.form.getlist("keep_id")
    try:
        keep_ids = [int(x) for x in keep_ids_raw if x.isdigit()]
    except ValueError:
        flash("Invalid paper IDs.", "danger")
        return redirect(url_for("dedup.index"))

    removed = deduplicator.resolve_duplicates(keep_ids)
    flash(f"Marked {removed} paper(s) as duplicates.", "success")
    return redirect(url_for("dedup.index"))
