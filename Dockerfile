# Counterfactual Participant Studio -- single-image production build.
#
# Stage 1 builds the React/Vite frontend into static files. Stage 2 installs the
# Python + Bambi/PyMC stack and serves both the API and that built frontend from
# one FastAPI process (api/main.py mounts ../frontend/dist at "/").
#
# Designed to run on Hugging Face Spaces (Docker SDK), but the same image runs on
# Render, Fly.io, Cloud Run, or `docker run` locally. The server binds to $PORT
# (default 7860, which is what Spaces expects).

# --------------------------------------------------------------------------- #
# Stage 1: build the frontend
# --------------------------------------------------------------------------- #
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # -> /build/dist

# --------------------------------------------------------------------------- #
# Stage 2: Python runtime
# --------------------------------------------------------------------------- #
FROM python:3.11-slim AS runtime

# PyTensor (under PyMC) compiles C at runtime, so a C/C++ compiler must be
# present. libgomp1 provides the OpenMP runtime it links against.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential g++ libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user with UID 1000 (the user Hugging Face Spaces expects).
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Writable locations for everything that caches or persists at runtime. Spaces'
# container filesystem is writable but ephemeral; mount persistent storage at
# /data and set STUDIO_DATA_DIR=/data to keep projects across restarts.
ENV STUDIO_DATA_DIR=/home/user/app/data \
    MPLCONFIGDIR=/home/user/.cache/matplotlib \
    NUMBA_CACHE_DIR=/home/user/.cache/numba \
    PYTENSOR_FLAGS=base_compiledir=/home/user/.cache/pytensor \
    PYTHONUNBUFFERED=1

WORKDIR /home/user/app

# Install Python deps first so the layer caches across code changes.
COPY --chown=user backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --user -r backend/requirements.txt \
    && pip install --no-cache-dir --user "uvicorn[standard]==0.34.0"

# Application code + the built frontend (as a sibling of backend/, which is where
# api/main.py looks for frontend/dist).
COPY --chown=user backend/ backend/
COPY --chown=user --from=frontend /build/dist frontend/dist

# api.main imports the `studio` package by name, so backend/ must be importable.
ENV PYTHONPATH=/home/user/app/backend
WORKDIR /home/user/app/backend

EXPOSE 7860
# Shell form so ${PORT} is expanded (Spaces/Render inject it; default 7860).
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-7860}
