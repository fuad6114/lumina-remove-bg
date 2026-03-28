"""
cli.py – Command-line interface for quick testing without the web server.
=========================================================================
Usage:
    python cli.py input.jpg                     → saves removed_bg.png
    python cli.py input.jpg -o my_output.png    → custom output path
    python cli.py input.jpg --show              → open result in system viewer
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from processor import BackgroundRemover


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Remove image background and replace with white using U2-Net."
    )
    p.add_argument("input", help="Path to input image (JPEG, PNG, WEBP, BMP, TIFF).")
    p.add_argument("-o", "--output", default=None,
                   help="Output PNG path (default: <input_stem>_bg_removed.png).")
    p.add_argument("--model", default="u2net",
                   choices=["u2net", "u2net_human_seg", "isnet-general-use"],
                   help="rembg model to use (default: u2net).")
    p.add_argument("--show", action="store_true",
                   help="Open the result in the system image viewer after processing.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] File not found: {src}", file=sys.stderr)
        sys.exit(1)

    out = Path(args.output) if args.output else src.with_name(f"{src.stem}_bg_removed.png")

    print(f"[INFO] Input  : {src}  ({src.stat().st_size // 1024} KB)")
    print(f"[INFO] Model  : {args.model}")
    print("[INFO] Loading model …", end=" ", flush=True)
    remover = BackgroundRemover(model_name=args.model)
    print("ready.")

    print("[INFO] Processing …", end=" ", flush=True)
    t0 = time.perf_counter()
    raw = src.read_bytes()
    try:
        result = remover.process(raw)
    except ValueError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.perf_counter() - t0
    print(f"done in {elapsed:.2f}s.")

    out.write_bytes(result)
    print(f"[INFO] Output : {out}  ({len(result) // 1024} KB)")

    if args.show:
        import subprocess, platform
        viewer = {"Darwin": "open", "Linux": "xdg-open", "Windows": "start"}
        cmd = viewer.get(platform.system(), "xdg-open")
        subprocess.run([cmd, str(out)], check=False)


if __name__ == "__main__":
    main()
