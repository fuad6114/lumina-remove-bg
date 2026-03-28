"""
processor.py – Core background-removal pipeline
================================================
Uses rembg (U2-Net) for subject segmentation, then:
  1. Extracts the alpha mask produced by the model.
  2. Refines edges with OpenCV morphology + Gaussian blur.
  3. Feathers the mask with Pillow for smooth, anti-aliased edges.
  4. Composites the subject over a pure-white (#FFFFFF) background.
"""

from __future__ import annotations

import io
import logging

import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageOps
from rembg import remove, new_session

log = logging.getLogger("bg_remover.processor")

# Supported PIL format strings accepted at decode time
_SUPPORTED_PIL_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF", "MPO"}

WHITE = (255, 255, 255, 255)   # RGBA pure white


class BackgroundRemover:
    """
    Stateful wrapper around the rembg session so the U2-Net model is
    loaded only once and reused across requests (thread-safe for inference).
    """

    def __init__(self, model_name: str = "u2net"):
        self.session = new_session(model_name)
        log.info("rembg session initialised with model '%s'", model_name)

    # ── Public API ──────────────────────────────────────────────────────────
    def process(self, image_bytes: bytes) -> bytes:
        """
        Full pipeline:
          raw bytes → PIL Image → rembg mask → edge refinement → white BG → PNG bytes

        Parameters
        ----------
        image_bytes : bytes
            Raw bytes of the uploaded image (any supported format).

        Returns
        -------
        bytes
            PNG-encoded image with white background.

        Raises
        ------
        ValueError
            If the file cannot be decoded as a supported image format.
        """
        input_img = self._decode(image_bytes)
        rgba_cut  = self._remove_background(input_img)
        refined   = self._refine_edges(rgba_cut)
        result    = self._composite_white(refined)
        return self._encode_png(result)

    # ── Private helpers ─────────────────────────────────────────────────────
    def _decode(self, data: bytes) -> Image.Image:
        """Decode raw bytes to a PIL RGBA image; raise ValueError on failure."""
        try:
            img = Image.open(io.BytesIO(data))
            img.verify()                      # catch truncated / corrupt files
        except Exception as exc:
            raise ValueError(f"Cannot decode image: {exc}") from exc

        # Re-open after verify() (verify() exhausts the stream)
        img = Image.open(io.BytesIO(data))

        if img.format not in _SUPPORTED_PIL_FORMATS:
            raise ValueError(
                f"Unsupported image format '{img.format}'. "
                "Accepted: JPEG, PNG, WEBP, BMP, TIFF."
            )

        img = ImageOps.exif_transpose(img)    # honour EXIF orientation
        return img.convert("RGBA")

    def _remove_background(self, img: Image.Image) -> Image.Image:
        """
        Run rembg (U2-Net) on the image and return an RGBA image where
        the alpha channel encodes the foreground mask (255 = subject, 0 = BG).
        """
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        result = remove(buf.read(), session=self.session)
        return Image.open(io.BytesIO(result)).convert("RGBA")

    def _refine_edges(self, rgba: Image.Image) -> Image.Image:
        """
        Post-process the alpha mask with OpenCV morphology + Gaussian blur,
        then feather it with Pillow to eliminate jagged / haloed edges.
        """
        r, g, b, a = rgba.split()
        alpha_np = np.array(a, dtype=np.uint8)

        # ── 1. Morphological cleanup (removes stray pixels / holes) ──────
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        alpha_np = cv2.morphologyEx(alpha_np, cv2.MORPH_CLOSE, kernel, iterations=2)
        alpha_np = cv2.morphologyEx(alpha_np, cv2.MORPH_OPEN,  kernel, iterations=1)

        # ── 2. Edge feathering via Gaussian blur on the mask ─────────────
        #    Blur only in the transition zone (0 < α < 255) to keep hard
        #    interior pixels intact while softening boundary pixels.
        blurred = cv2.GaussianBlur(alpha_np, (7, 7), sigmaX=2, sigmaY=2)
        transition = (alpha_np > 10) & (alpha_np < 245)
        alpha_np[transition] = blurred[transition]

        # ── 3. Pillow smooth pass for sub-pixel anti-aliasing ─────────────
        alpha_pil = Image.fromarray(alpha_np, mode="L")
        alpha_pil = alpha_pil.filter(ImageFilter.SMOOTH_MORE)

        rgba.putalpha(alpha_pil)
        return rgba

    def _composite_white(self, rgba: Image.Image) -> Image.Image:
        """
        Flatten RGBA onto a solid white (#FFFFFF) canvas.
        This is equivalent to alpha-blending against white.
        """
        white_bg = Image.new("RGBA", rgba.size, WHITE)
        white_bg.paste(rgba, mask=rgba.split()[3])   # use alpha as mask
        return white_bg.convert("RGB")               # drop alpha – BG is opaque

    @staticmethod
    def _encode_png(img: Image.Image) -> bytes:
        """Encode a PIL Image to PNG bytes (lossless, web-safe)."""
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


# ── Convenience function (stateless, creates a new session each call) ─────────
def remove_background_simple(image_bytes: bytes) -> bytes:
    """
    One-shot helper – useful for scripting / testing without managing a
    BackgroundRemover instance.  For production, prefer BackgroundRemover
    so the model is loaded only once.
    """
    remover = BackgroundRemover()
    return remover.process(image_bytes)
