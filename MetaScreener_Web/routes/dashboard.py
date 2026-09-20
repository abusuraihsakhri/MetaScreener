from flask import Blueprint, render_template
from flask_login import login_required
from services import screener, deduplicator, exporter

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    screen_stats = screener.get_stats()
    dedup_stats = deduplicator.get_stats()
    prisma = exporter.prisma_counts()
    return render_template("dashboard.html",
                           screen=screen_stats,
                           dedup=dedup_stats,
                           prisma=prisma)
