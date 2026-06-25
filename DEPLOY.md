# Deploying the Counterfactual Participant Studio

The app is **one Docker image**. A multi-stage build (`Dockerfile` at the repo
root) compiles the React/Vite frontend, installs the Python + Bambi/PyMC stack,
and runs a single FastAPI process that serves **both** the JSON API under
`/api/*` and the built UI at `/`. The server listens on `$PORT` (default
`7860`).

Because the modeling step runs real MCMC (PyMC), the app needs a host that can
run Python with a few GB of RAM — it is **not** a static site, so plain GitHub
Pages cannot run it. The recommended host is **Hugging Face Spaces (Docker
SDK)**, whose free CPU tier (2 vCPU / 16 GB) comfortably fits and samples the
model. The same image runs unchanged on Render, Fly.io, Google Cloud Run, or a
local Docker daemon.

---

## Option A — Hugging Face Spaces (recommended)

1. **Create a Space**: https://huggingface.co/new-space → choose **Docker → Blank**,
   pick **CPU basic** hardware, and give it a name.

2. **Add the contents of this repository to the Space's git repo.** Either push
   this repo's files into the Space remote, or copy them in. The Space only
   needs the `Dockerfile`, `backend/`, `frontend/`, and `.dockerignore`.

3. **Make sure the Space's `README.md` starts with this front-matter** (Hugging
   Face reads it to know the Space is Docker-based and which port to expose). If
   you push this repo's `README.md` over the one HF generated, prepend this
   block to it:

   ```yaml
   ---
   title: Counterfactual Participant Studio
   emoji: 📊
   colorFrom: blue
   colorTo: indigo
   sdk: docker
   app_port: 7860
   pinned: false
   ---
   ```

4. **Push.** Hugging Face builds the Dockerfile and starts the container. First
   build takes a few minutes (it installs PyMC and compiles the frontend). When
   it goes green, the wizard is live at
   `https://huggingface.co/spaces/<you>/<space-name>`.

### Persisting projects across restarts (optional)

By default each project's SQLite row and generated artifacts live in the
container filesystem, which **resets when the Space restarts or rebuilds** —
fine for a shared demo where runs are transient. To keep them:

- Add **persistent storage** to the Space (Settings → Storage), which mounts at
  `/data`, and
- set a Space **secret/variable** `STUDIO_DATA_DIR=/data`.

The app already reads `STUDIO_DATA_DIR` for all of its on-disk state.

---

## Option B — Render / Fly.io / Cloud Run

Any Docker host works. Two things to know:

- **RAM**: PyMC sampling needs headroom. Render's **free** 512 MB tier will OOM
  during a fit — use an instance with **≥ 2 GB**.
- **Port**: these platforms inject `$PORT`; the image already binds to it
  (`--port ${PORT:-7860}`), so no change is needed.

On Render: New → **Web Service** → from this repo → Runtime **Docker**. Leave the
start command empty (the Dockerfile's `CMD` is used). For persistence, attach a
disk and set `STUDIO_DATA_DIR` to its mount path.

---

## Run the production image locally

```bash
docker build -t cf-studio .
docker run --rm -p 7860:7860 cf-studio
# open http://localhost:7860
```

To persist data on the host, mount a volume and point the app at it:

```bash
docker run --rm -p 7860:7860 \
  -e STUDIO_DATA_DIR=/data -v "$PWD/studio-data:/data" \
  cf-studio
```

---

## Configuration reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `7860` | Port the server binds to. |
| `STUDIO_DATA_DIR` | `/home/user/app/data` (in image) | Where SQLite + generated artifacts are written. Point at a mounted volume to persist. |

The image also sets writable cache locations for matplotlib, Numba, and
PyTensor's C-compile directory, so nothing tries to write outside the
non-root user's home.
