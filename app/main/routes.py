from flask import jsonify, render_template

from app.main import bp


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/health")
def health():
    return jsonify(status="ok")
