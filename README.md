# CutOut AI — Background Removal API

AI-powered background removal microservice built on **U2-Net** (via `rembg`),
**OpenCV**, and **Pillow**. Removes backgrounds and replaces them with pure white
(`#FFFFFF`). Ships with a clean web UI and a REST API ready to plug into any
photo-editing frontend.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI / Flask App                         │
│                                                                 │
│  POST /remove-background          POST /remove-background/json  │
│         │                                  │                    │
│         └──────────────┬───────────────────┘                    │
│                        ▼                                        │
│              BackgroundRemover (processor.py)                   │
│                        │                                        │
│         ┌──────────────┼──────────────────────┐                │
│         ▼              ▼                       ▼                │
│    1. Decode      2. rembg / U2-Net      3. Edge Refine         │
│    (Pillow)       (AI segmentation)     (OpenCV + Pillow)       │
│                        │                                        │
│                        ▼                                        │
│              4. Composite white BG  →  PNG output               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

> **GPU acceleration** (optional): replace `rembg` with `rembg[gpu]` and
> install `onnxruntime-gpu` instead of `onnxruntime`.

### 2. Run the FastAPI server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** — the web UI is served automatically.

Interactive API docs: **http://localhost:8000/docs**

### 3. Run the Flask alternative

```bash
python flask_app.py
```

### 4. CLI (no server needed)

```bash
python cli.py photo.jpg                     # → photo_bg_removed.png
python cli.py photo.jpg -o output.png       # custom path
python cli.py photo.jpg --show              # open in system viewer
python cli.py photo.jpg --model u2net_human_seg  # portrait-optimised model
```

### 5. Docker

```bash
docker build -t cutout-ai .
docker run -p 8000:8000 cutout-ai
```

---

## API Reference

### `GET /health`
Returns `{"status": "ok", "model": "u2net"}`.

### `POST /remove-background`
**Input:** `multipart/form-data` with field `file` (JPEG, PNG, WEBP, BMP, TIFF — max 20 MB).  
**Output:** `image/png` binary (white background, lossless PNG).  
**Headers returned:** `X-Processing-Time` (seconds).

```bash
curl -X POST http://localhost:8000/remove-background \
     -F "file=@photo.jpg" \
     --output result.png
```

### `POST /remove-background/json`
Same processing, but returns JSON:

```json
{
  "success": true,
  "processing_time_s": 1.24,
  "width": 1920,
  "height": 1080,
  "format": "PNG",
  "image_base64": "<base64-encoded PNG>"
}
```

Ideal for JavaScript clients:

```js
const fd = new FormData();
fd.append('file', fileInput.files[0]);

const { image_base64, processing_time_s } = await fetch(
  '/remove-background/json', { method: 'POST', body: fd }
).then(r => r.json());

document.getElementById('result').src = `data:image/png;base64,${image_base64}`;
```

---

## Integrating into an Existing Photo Editing App

**Proxy approach (Next.js / Express example):**

```js
// pages/api/remove-bg.js  (Next.js)
import FormData from 'form-data';
import fetch from 'node-fetch';

export default async function handler(req, res) {
  const fd = new FormData();
  fd.append('file', req.body, { filename: 'upload.jpg', contentType: 'image/jpeg' });

  const upstream = await fetch('http://cutout-ai:8000/remove-background', {
    method: 'POST', body: fd, headers: fd.getHeaders()
  });

  res.setHeader('Content-Type', 'image/png');
  upstream.body.pipe(res);
}
```

**Python client:**

```python
import httpx

with open("photo.jpg", "rb") as f:
    r = httpx.post(
        "http://localhost:8000/remove-background",
        files={"file": ("photo.jpg", f, "image/jpeg")},
    )

with open("result.png", "wb") as out:
    out.write(r.content)
```

---

## Pipeline Details

| Step | Library | What it does |
|------|---------|--------------|
| **Decode** | Pillow | Reads any supported format; applies EXIF orientation |
| **Segment** | rembg / U2-Net | Generates a soft alpha mask for the subject |
| **Morphology** | OpenCV | `MORPH_CLOSE` fills holes; `MORPH_OPEN` removes stray pixels |
| **Edge blur** | OpenCV | Gaussian blur applied only in the mask transition zone |
| **Feather** | Pillow | `SMOOTH_MORE` for sub-pixel anti-aliasing |
| **Composite** | Pillow | Alpha-blend subject over solid white `(255,255,255)` |
| **Encode** | Pillow | Lossless PNG with `optimize=True` |

### Available models (pass `--model` to CLI or edit `BackgroundRemover()`)

| Model | Best for |
|-------|----------|
| `u2net` (default) | General objects, products |
| `u2net_human_seg` | Portraits, people |
| `isnet-general-use` | High-accuracy general |

---

## Error Handling

| HTTP code | Cause |
|-----------|-------|
| `400` | Unsupported format, file > 20 MB, corrupt file |
| `422` | Missing `file` field in multipart body |
| `500` | Model inference failure (logged server-side) |

All errors return `{"detail": "<message>"}` JSON.

---

## File Structure

```
bg_remover/
├── main.py          # FastAPI app (recommended)
├── flask_app.py     # Flask alternative
├── processor.py     # Core AI + image processing pipeline
├── cli.py           # Command-line interface for local use
├── requirements.txt
├── Dockerfile
├── README.md
└── static/
    └── index.html   # Bundled web UI
```
