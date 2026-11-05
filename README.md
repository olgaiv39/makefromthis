# MakeFromThis

Turn a photograph of leftover material into a measured cutting plan for rectangles and squares.

Built for the **Meta Global AI Developer Hackathon**.
[GitHub repository](https://github.com/olgaiv39/makefromthis) · [Quick Start](#quick-start)

## Demo video

[Watch the hackathon demo on YouTube](https://youtu.be/ZmWH-WzxUy0).

## Features

Upload one flat material piece, review its automatically detected outline, enter a
known measurement, then choose the size and number of pieces to cut. MakeFromThis
checks the placements and exports a physically sized SVG pattern.

Photo upload, OpenCV detection, calibration, cutting layouts and SVG export all
work **without an AI key**. Optional Meta Muse Spark Open features add image
understanding and cutting suggestions through Baseten.

## Quick Start

Requires **Python 3.12**, **Node.js 20+ with npm**, and **Git**. These commands are
for macOS/Linux, starting from a fresh clone:

```sh
git clone https://github.com/olgaiv39/makefromthis.git
cd makefromthis
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --only-binary=:all: -r backend/requirements-runtime.lock
npm --prefix frontend ci
npm --prefix frontend run build
AI_ENABLED=false backend/.venv/bin/python tools/start_release.py
```

Open **http://127.0.0.1:8000**. One server serves both the built React app and its
API; a separate Vite server and pytest are not needed. Stop it with **Ctrl+C**.
Package installation needs internet access or cached packages; the running
photo-only workflow needs no external AI service.

The launcher defaults to `BIND_HOST=127.0.0.1` and `PORT=8000`. It loads
`backend/.env.local` if present, or the file selected by `MFT_ENV_FILE`.
Existing process variables take precedence, so `AI_ENABLED=false` keeps this
launch offline even if a private file enables AI. Rebuild the frontend after
changing its source. See [configuration and troubleshooting](docs/DEPLOYMENT.md).

## Enable Meta Muse Spark Open

This is optional. You need a valid **Baseten API key with access to
`meta-models/muse-spark-open-1026`**. Requests consume provider credits.

Prepare a private backend file from the existing template. Run this from the
repository root; it preserves an existing private file:

```sh
if [ ! -f backend/.env.local ]; then
  (umask 077; cp .env.example backend/.env.local)
fi
chmod 600 backend/.env.local
```

Open `backend/.env.local` in your editor. Set the following entries, replacing the
key placeholder privately. Edit existing entries rather than appending duplicates:

```dotenv
BASETEN_API_KEY=YOUR_PRIVATE_BASETEN_KEY
AI_ENABLED=true
RECOMMENDATION_PROVIDER=baseten
RECOMMENDATION_ENDPOINT_URL=https://inference.baseten.co/v1/chat/completions
RECOMMENDATION_MODEL_ID=meta-models/muse-spark-open-1026
RECOMMENDATION_MAX_TOKENS=2048
SEGMENTATION_PROVIDER=disabled
```

The adapter sends direct HTTP requests, so retain `/v1/chat/completions`, not just
the SDK base URL `/v1`. The template starts with AI disabled and a 512-token
recommendation budget; the values above explicitly enable AI and use the existing
Render recommendation budget. Never commit a real key or put it in frontend
variables, screenshots, Docker images or build arguments.

Stop the offline server, then launch with the private file explicitly selected:

```sh
AI_ENABLED=true MFT_ENV_FILE="$PWD/backend/.env.local" backend/.venv/bin/python tools/start_release.py
```

All Baseten requests originate in the backend. In the app:

- **Photo-only detection** uses OpenCV without a Baseten request.
- Optional **Muse image understanding** sends a bounded copy of the photo to
  Baseten to guide detection. OpenCV extracts the pixel contour; Muse does not
  produce a SAM segmentation mask or infer physical measurements.
- **Suggest ideas with AI** asks Muse to rank supported cutting options already
  checked against the calibrated material. **Find fitting options** uses geometry
  only and does not call Muse.

Check configuration without consuming inference credits:

```sh
curl --fail --silent --show-error http://127.0.0.1:8000/api/ai/availability
```

This reports whether configuration is available, not whether authentication,
credits or a live inference will succeed. Live Muse recommendations were
successfully verified in Chrome during the hackathon demo; that does not establish
live image-understanding verification. For one deliberate live check and hosting
setup, see [Enabling Meta Muse Spark Open on Render](docs/DEPLOYMENT.md#enabling-meta-muse-spark-open-on-render).

## Docker

Requires Docker with its daemon running. From the repository root:

```sh
docker build -t makefromthis:local .
docker run --detach --rm --name makefromthis-local -p 127.0.0.1:8000:8000 -e AI_ENABLED=false makefromthis:local
```

Open **http://127.0.0.1:8000**. The image builds React and installs the Python
runtime, including Shapely and headless OpenCV. No local Python/Node installation
or GPU is required for this route. Stop the container with:

```sh
docker stop makefromthis-local
```

This launch is offline by default. Optional container AI settings belong in runtime
environment secrets, never the image. See [deployment configuration](docs/DEPLOYMENT.md#environment-and-secrets).
Do not run the local server and container on port 8000 at the same time.

## Using MakeFromThis

1. **Add photo.** Photograph one isolated, flat material piece from above, with
   its full boundary visible against a contrasting background. Separate scraps
   and remove tools. Use JPEG, PNG or WebP, up to 8 MB.
2. **Find material.** Run detection, inspect the highlighted edge and choose
   **Use this outline** only if it follows the usable material. An unclear or
   obstructed photograph may be refused; take a clearer photo instead.
3. **Enter measurements.** Supply a known width or a two-point reference length
   in millimeters. Include a ruler in the same plane or measure a visible edge.
   The app cannot determine physical scale from the photo alone.
4. **Choose cutting pieces.** Enter rectangle/square width, height and quantity,
   then **Check how many fit**. Optional AI suggestions also use these supported
   shapes. Review the placed/requested counts and any gap or rotation settings.
5. **Download pattern.** Preview a complete verified layout and download SVG.
   Print at **100% size** and check the calibration. Back navigation retains your
   current photo and inputs; refreshing the page does not persist them.

To try an included photograph, upload
[examples/craft_photos/incoming/Cutting_mat.jpg](examples/craft_photos/incoming/Cutting_mat.jpg).
It is a photograph by Lenore Edman, licensed [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/);
see [source and credits](docs/PHOTO_CREDITS.md). Its physical scale is unknown:
supply a genuine measurement for a cutting file you intend to use. A made-up test
measurement is illustrative only. The app starts with upload; internal annotated
and synthetic examples are not offered as public gallery choices.

## Architecture

React + TypeScript + Vite provide the mobile-first interface. FastAPI handles image
processing and API requests; OpenCV extracts contours, Shapely validates geometry,
and a deterministic grid heuristic places pieces. SVG exports use millimeter units.
No account, database, GPU or local model weights are required. Baseten inference is
optional and handled only by the backend.

For a source map, correctness invariants and contributor guidance, start with
[AGENTS.md](AGENTS.md). Detailed runtime configuration is in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

### Optional hot-reload development

Use the Quick Start environment and installed frontend dependencies. To run the
backend and Vite separately, open two terminals at the repository root:

```sh
# Terminal 1: backend; deliberately offline, no private file needed
AI_ENABLED=false backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

```sh
# Terminal 2: frontend
npm --prefix frontend run dev
```

Open **http://127.0.0.1:5173**. Vite proxies `/api` to port 8000. Unlike the
single-service launcher, direct Uvicorn does not discover `backend/.env.local`.
For AI-enabled hot reload, prepare that file as above and replace Terminal 1 with:

```sh
AI_ENABLED=true MFT_ENV_FILE="$PWD/backend/.env.local" backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

## Testing

Install pytest only when running backend tests. From the repository root:

```sh
backend/.venv/bin/python -m pip install pytest==8.4.2
AI_ENABLED=false backend/.venv/bin/python -m pytest -q backend
AI_ENABLED=false npm --prefix frontend test
AI_ENABLED=false npm --prefix frontend run build
AI_ENABLED=false backend/.venv/bin/python tools/release_smoke.py --asgi
```

Normal automated tests use offline execution and mocked provider transports; they
do not establish live inference. The in-process smoke checks built assets and real
API/layout/SVG operations, without a browser. More diagnostics and optional browser
checks are in [deployment verification](docs/DEPLOYMENT.md#reproducible-verification-and-browser-acceptance).

**Public-clone test limitation:** two tests in `backend/test_automatic_detection.py`
also require the local-only `examples/craft_photos/incoming/Cutting_tools_sewing.jpg`,
which is not tracked in Git. Without that original photograph those tests fail
with a missing-file error; do not interpret this as a detection regression or
replace the input with a synthetic image. The included `Cutting_mat.jpg` example
is tracked. This missing negative fixture does not prevent running the app.

## Deployment

GitHub hosts the source code; this README does not assert a live application URL.
The existing [Dockerfile](Dockerfile) and [render.yaml](render.yaml) support a
single-service deployment with static assets and backend API on the same origin.

See [Enabling Meta Muse Spark Open on Render](docs/DEPLOYMENT.md#enabling-meta-muse-spark-open-on-render)
for the existing AI-enabled Render profile, backend-only `BASETEN_API_KEY` secret,
readiness checks and a manually triggered recommendation check. The local private
environment file is not deployed. Hosting availability and cost depend on the host.

## Limitations

- Cutting supports **1–50 rectangles or squares**, not complete garment patterns,
  curved pieces or automatic seam allowance.
- Detection targets one isolated, flat piece. Overlaps, tools, severe occlusion,
  ambiguous surfaces and internal holes may be rejected. Review every outline.
- Physical measurements must be supplied by the user. Perspective/lens correction,
  fabric grain and stretch compensation are not implemented.
- Heuristic search can miss a possible arrangement; it does not prove optimal
  packing or physical impossibility. Only complete layouts that pass independent
  containment, overlap and clearance checks can be exported.
- Uploads are processed by the backend. Optional image understanding also sends a
  bounded photo to Baseten; cutting suggestions send geometry and preferences.
  See the app's sharing details before requesting AI.

## Credits and licenses

MakeFromThis's application, geometry workflow, import tooling and tests are
original contributions for the Meta Global AI Developer Hackathon. Third-party
libraries and images retain their own licenses; no third-party model weights are
distributed.

- **Demonstration photograph:** Lenore Edman, *Cutting_mat.jpg*, CC BY 2.0;
  [source and attribution](docs/PHOTO_CREDITS.md). No endorsement is implied.
- **Internal CTVG fixtures:** Daniel Costa, João Cruz, Gualter Barros and Nelson
  Rodrigues (2024), *CTVG*, Mendeley Data V1,
  [DOI 10.17632/m5wds8287s.1](https://doi.org/10.17632/m5wds8287s.1), CC BY 4.0.
  Original selected images/annotations are retained; derived masks, thumbnails
  and layouts are attributed. These are not AI-generated segmentation results.
- **Dependencies:** React, Vite, FastAPI, OpenCV, Shapely/GEOS and other pinned
  packages are third-party software.

[Dataset provenance, modifications and license details](docs/DATA_SOURCES.md).
