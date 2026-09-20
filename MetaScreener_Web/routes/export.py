from flask import Blueprint, send_file, jsonify, render_template
from flask_login import login_required
from services.exporter import export_excel, prisma_counts
import io

export_bp = Blueprint("export", __name__)


@export_bp.route("/export")
@login_required
def index():
    prisma = prisma_counts()
    return render_template("export.html", prisma=prisma)


@export_bp.route("/export/excel")
@login_required
def download_excel():
    data = export_excel()
    return send_file(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="metascreener_export.xlsx",
    )


@export_bp.route("/export/prisma.json")
@login_required
def prisma_json():
    return jsonify(prisma_counts())
