import os
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required
from werkzeug.utils import secure_filename
from config import Config
from services import importer

papers_bp = Blueprint("papers", __name__)


@papers_bp.route("/import", methods=["GET", "POST"])
@login_required
def import_papers():
    if request.method == "POST":
        files = request.files.getlist("files")
        if not files or all(f.filename == "" for f in files):
            flash("No files selected.", "warning")
            return redirect(request.url)

        total_imported = total_skipped = 0
        total_errors = []

        for f in files:
            if not f or not f.filename:
                continue
            filename = secure_filename(f.filename)
            if not importer.allowed_file(filename):
                flash(f"Skipped '{filename}' — unsupported format (use RIS, BibTeX, CSV, TXT).", "warning")
                continue

            save_path = os.path.join(Config.UPLOAD_FOLDER, filename)
            f.save(save_path)

            result = importer.import_file(save_path, filename)
            total_imported += result["imported"]
            total_skipped += result["skipped"]
            total_errors.extend(result["errors"])

            # Clean up uploaded temp file
            try:
                os.remove(save_path)
            except OSError:
                pass

        flash(f"Imported {total_imported} paper(s), skipped {total_skipped} duplicate(s).", "success")
        if total_errors:
            flash(f"Errors: {'; '.join(total_errors[:3])}", "danger")

        return redirect(url_for("papers.list_papers"))

    return render_template("import.html")


@papers_bp.route("/papers")
@login_required
def list_papers():
    from services.screener import get_all_papers
    decision = request.args.get("decision")
    papers = get_all_papers(decision_filter=decision)
    return render_template("papers.html", papers=papers, filter=decision)
