"""Local demo server: serves the web app and one endpoint that reads envelopes with Claude.

    python server/app.py          then open http://localhost:8080

All app data still lives in your browser (IndexedDB). This server stores nothing; it only
forwards the two photos of a scanned envelope to Claude and returns what Claude read.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

import pipeline  # noqa: E402  (after load_dotenv so it sees the key)

WEB = ROOT / "web"
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024


@app.post("/api/extract")
def extract():
    """multipart form with `front` and `back` photos -> JSON (see web/js/pipeline.js)."""
    front, back = request.files.get("front"), request.files.get("back")
    if not front or not back:
        return jsonify({"error": "Send both a front and a back photo."}), 400
    return jsonify(pipeline.read_envelope(front.read(), back.read()))


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "claude": bool(os.environ.get("ANTHROPIC_API_KEY")), "model": pipeline.MODEL})


@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/<path:path>")
def files(path):
    return send_from_directory(WEB, path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", 8080))
    print(f"IFC Mail demo: http://localhost:{port}")
    print("Claude envelope reading:", "ON" if os.environ.get("ANTHROPIC_API_KEY") else "OFF (no ANTHROPIC_API_KEY in .env, manual entry only)")
    app.run(host="127.0.0.1", port=port)
