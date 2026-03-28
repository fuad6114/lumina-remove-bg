"""
Background Removal API
======================
FastAPI backend for AI-powered background removal using rembg (U2-Net).
Replaces background with solid white (#FFFFFF) with edge smoothing via OpenCV & Pillow.
"""

import io
import logging
import time
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageFilter

from processor import BackgroundRemover

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
log = logging.getLogger("bg_remover")

# ── Supported formats ─────────────────────────────────────────────────────────
SUPPORTED_MIME = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}
SUPPORTED_EXT  = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
MAX_FILE_MB    = 20
MAX_BYTES      = MAX_FILE_MB * 1024 * 1024


# ── App lifespan (warm up model once at startup) ──────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Loading U2-Net model via rembg …")
    app.state.remover = BackgroundRemover()
    log.info("Model ready.")
    yield
    log.info("Shutting down.")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Background Removal API",
    description=(
        "Remove image backgrounds with AI (U2-Net / rembg). "
        "Returns a PNG with a pure-white (#FFFFFF) background."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Serve the bundled web UI
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Utility"])
async def health():
    return {"status": "ok", "model": "u2net"}


# ── Main endpoint ─────────────────────────────────────────────────────────────
@app.post(
    "/remove-background",
    tags=["Background Removal"],
    summary="Remove background and replace with white",
    responses={
        200: {"content": {"image/png": {}}, "description": "Processed PNG image"},
        400: {"description": "Bad request (unsupported format / file too large)"},
        500: {"description": "Internal processing error"},
    },
)
async def remove_background(
    file: UploadFile = File(..., description="Image file (JPEG, PNG, WEBP, BMP, TIFF)"),
):
    # ── Validate content-type ─────────────────────────────────────────────
    ct = (file.content_type or "").lower()
    fname = (file.filename or "").lower()
    ext = "." + fname.rsplit(".", 1)[-1] if "." in fname else ""

    if ct not in SUPPORTED_MIME and ext not in SUPPORTED_EXT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file format '{file.content_type}'. "
                f"Accepted types: JPEG, PNG, WEBP, BMP, TIFF."
            ),
        )

    # ── Read & size-check ─────────────────────────────────────────────────
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the {MAX_FILE_MB} MB limit ({len(raw)//1024//1024} MB received).",
        )

    # ── Process ───────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        result_png = app.state.remover.process(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.exception("Processing failed")
        raise HTTPException(status_code=500, detail=f"Processing error: {exc}")

    elapsed = time.perf_counter() - t0
    log.info("Processed '%s' in %.2fs  (%d bytes → %d bytes)", fname, elapsed, len(raw), len(result_png))

    return Response(
        content=result_png,
        media_type="image/png",
        headers={
            "X-Processing-Time": f"{elapsed:.3f}s",
            "Content-Disposition": f'attachment; filename="removed_bg.png"',
        },
    )


# ── Metadata endpoint (dimensions, format info) ───────────────────────────────
@app.post("/remove-background/json", tags=["Background Removal"],
          summary="Same as /remove-background but returns base64 JSON")
async def remove_background_json(
    file: UploadFile = File(...),
):
    import base64

    ct = (file.content_type or "").lower()
    fname = (file.filename or "").lower()
    ext = "." + fname.rsplit(".", 1)[-1] if "." in fname else ""

    if ct not in SUPPORTED_MIME and ext not in SUPPORTED_EXT:
        raise HTTPException(status_code=400, detail="Unsupported file format.")

    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_FILE_MB} MB limit.")

    t0 = time.perf_counter()
    try:
        result_png = app.state.remover.process(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.exception("Processing failed")
        raise HTTPException(status_code=500, detail=str(exc))

    elapsed = time.perf_counter() - t0

    img = Image.open(io.BytesIO(result_png))
    return JSONResponse({
        "success": True,
        "processing_time_s": round(elapsed, 3),
        "width": img.width,
        "height": img.height,
        "format": "PNG",
        "image_base64": base64.b64encode(result_png).decode(),
    })


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
