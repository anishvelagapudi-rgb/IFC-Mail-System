"""Flask app: JSON API under /api, and the existing web/ folder as static files (one deployment).

Run locally:   flask --app backend.app run --debug        (from the repo root)
Production:    gunicorn 'backend.app:create_app()'
"""
import logging

from flask import Flask, jsonify, request, send_from_directory
from postgrest.exceptions import APIError
from werkzeug.exceptions import HTTPException

from . import config

log = logging.getLogger(__name__)


def create_app() -> Flask:
    logging.basicConfig(level=logging.INFO)
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES
    if config.missing():
        log.warning("Missing settings: %s (see .env.example)", ", ".join(config.missing()))

    from .routes import auth, mail, members, org, requests_messages

    for mod in (auth, members, mail, requests_messages, org):
        app.register_blueprint(mod.bp, url_prefix="/api")

    @app.get("/api/health")
    def health():
        return jsonify({"ok": not config.missing(), "missing": config.missing(), "pipeline": bool(config.ANTHROPIC_API_KEY)})

    @app.errorhandler(HTTPException)
    def http_error(e: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"error": e.description or e.name}), e.code
        return e

    @app.errorhandler(APIError)
    def db_error(e: APIError):
        # 42501 = row-level security / permission denied, 23505 = unique, 23503 = foreign key
        code = {"42501": 403, "23505": 409, "23503": 400, "23514": 400, "22P02": 400, "PGRST116": 404}.get(str(e.code), 500)
        log.warning("database error %s: %s", e.code, e.message)
        msg = {403: "Not allowed.", 409: "That already exists.", 404: "Not found."}.get(code, "Invalid data." if code == 400 else "Database error.")
        return jsonify({"error": msg}), code

    @app.errorhandler(Exception)
    def unexpected(e: Exception):
        if isinstance(e, HTTPException):
            return http_error(e)
        log.exception("unhandled error")
        return jsonify({"error": "Something went wrong on the server."}), 500

    @app.get("/")
    def index():
        return send_from_directory(config.WEB_DIR, "index.html")

    @app.get("/<path:path>")
    def static_files(path):
        if path.startswith("api/"):
            return jsonify({"error": "Not found."}), 404
        return send_from_directory(config.WEB_DIR, path)

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    return app
