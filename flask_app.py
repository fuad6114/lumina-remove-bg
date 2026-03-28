"""
flask_app.py – Flask alternative to main.py (FastAPI)
======================================================
Drop-in replacement if your stack uses Flask instead of FastAPI.
Usage:
    pip install flask flask-cors
    python flask_app.py
"""

from __future__ import annotations

import io
import logging
import time
from functools import lru_cache

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

from processor import BackgroundRemover

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s")
log = logging.getLogger("flask_bg_remover")

SUPPORTED_MIME = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}
MAX_BYTES = 20 * 1024 * 1024

app = Flask(__name__, static_folder="static")
CORS(app)

# Module-level singleton so U2-Net loads once
_remover: BackgroundRemover | None = None


def get_remover() -> BackgroundRemover:
    global _remover
    if _remover is None:
        log.info("Loading U2-Net model …")
        _remover = BackgroundRemover()
        log.info("Model ready.")
    return _remover


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "model": "u2net"})


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/remove-background", methods=["POST"])
def remove_background():
    if "file" not in request.files:
        return jsonify({"error": "No file field in request."}), 400

    f = request.files["file"]
    ct = (f.content_type or "").lower()

    if ct not in SUPPORTED_MIME:
        return jsonify({
            "error": f"Unsupported content-type '{ct}'. "
                     "Accepted: image/jpeg, image/png, image/webp, image/bmp, image/tiff."
        }), 400

    raw = f.read()
    if len(raw) > MAX_BYTES:
        return jsonify({"error": f"File exceeds 20 MB limit."}), 400

    t0 = time.perf_counter()
    try:
        result_png = get_remover().process(raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        log.exception("Processing failed")
        return jsonify({"error": f"Processing error: {exc}"}), 500

    elapsed = time.perf_counter() - t0
    log.info("Processed in %.2fs", elapsed)

    buf = io.BytesIO(result_png)
    buf.seek(0)
    response = send_file(buf, mimetype="image/png",
                         as_attachment=True,
                         download_name="removed_bg.png")
    response.headers["X-Processing-Time"] = f"{elapsed:.3f}s"
    return response


@app.route("/remove-background/json", methods=["POST"])
def remove_background_json():
    import base64
    from PIL import Image

    if "file" not in request.files:
        return jsonify({"error": "No file field."}), 400

    f = request.files["file"]
    raw = f.read()
    if len(raw) > MAX_BYTES:
        return jsonify({"error": "File too large."}), 400

    t0 = time.perf_counter()
    try:
        result_png = get_remover().process(raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    elapsed = time.perf_counter() - t0
    img = Image.open(io.BytesIO(result_png))
    return jsonify({
        "success": True,
        "processing_time_s": round(elapsed, 3),
        "width": img.width,
        "height": img.height,
        "format": "PNG",
        "image_base64": base64.b64encode(result_png).decode(),
    })


if __name__ == "__main__":
    get_remover()   # warm up at startup
    app.run(host="0.0.0.0", port=8000, debug=False)
