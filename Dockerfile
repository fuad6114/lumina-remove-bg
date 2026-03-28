# ── Stage 1: builder (install deps) ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Pre-download the U2-Net model weights so the container starts instantly
RUN python -c "from rembg import new_session; new_session('u2net')"

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

# System libs for OpenCV headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1-mesa-glx \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin
# Copy cached model weights
COPY --from=builder /root/.u2net /root/.u2net

# Copy application code
COPY main.py processor.py ./
#COPY static ./static

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
