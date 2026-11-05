# MakeFromThis

**Give leftover material a second life with geometry-verified cutting plans.**
Built for the **Meta Global AI Developer Hackathon**.

Upload a flat, overhead photograph. Review and accept its automatically detected
boundary, supply a real measurement, choose rectangle or square dimensions and
quantity, and export a measured SVG cutting pattern. Each layout passes independent
containment, overlap, clearance and rotation checks. Photo-only detection works
offline with OpenCV. Optional Baseten Muse image understanding supplies approximate
localization and material suitability, not a SAM mask or physical scale.

Public examples must be genuine craft photographs without supplied segmentation.
One licensed real photograph is included for regression testing.
The public gallery is therefore empty and the upload-first automatic-detection flow
remains available. CTVG and synthetic assets remain internal regression fixtures,
not target-audience acceptance photographs. No scale or outline is prepopulated. Automatic detection supports one isolated piece without internal holes; unsuitable photos are refused.
[Demonstration photograph credits](docs/PHOTO_CREDITS.md).

## Run locally

From this repository, with Python 3.12 and npm/Node installed:

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --only-binary=:all: -r backend/requirements-runtime.lock
backend/.venv/bin/python -m pip install pytest==8.4.2
backend/.venv/bin/python -c 'import shapely; print(shapely.__version__)'
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --reload
```

In another terminal:

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to the backend on port 8000.
Use `backend/.venv/bin/python` for backend commands: installing Shapely into a
separate interpreter does not fix the running backend. `geometry_unavailable`
is a local missing-Shapely/preflight error, not a Baseten authentication error.
The current normal environment imports Python 3.12.8 / Shapely 2.1.2 successfully.

For the single-service application (including SVG downloads):

```sh
npm --prefix frontend run build
AI_ENABLED=false backend/.venv/bin/python tools/start_release.py
```

Open **http://127.0.0.1:8000**. The launcher loads the existing private
`backend/.env.local` if present, or the explicit `MFT_ENV_FILE`; process settings
win. `BIND_HOST` defaults to `127.0.0.1`, `PORT` to `8000`. Docker and Render bind
`0.0.0.0` explicitly. Keep HTTPS termination on the production hosting platform.

## Try it

Upload a photograph of one flat material piece. Choose **Find material**, review
the highlighted boundary and **Use this outline**, then calibrate with a known
width or two points on a coplanar ruler. Check project fits, choose
an actually verified result, preview and download SVG. Detection sends the photo to this backend without saving it. If available and
selected, AI analysis sends a bounded JPEG copy to Baseten only when requested. Back retains
the current image. None of the unavailable source candidates has been tested for
outlining, scaling, feasibility or SVG; existing regression success is separate.

The main cutting operation makes 1–50 rectangles or squares at user-entered
cutting dimensions. A real measurement is required; add seam allowance yourself.
Miniature templates remain API regression fixtures only, outside the public workflow. The grid heuristic can miss feasible arrangements; only verified complete
layouts can be exported. Perspective/lens correction is not implemented.

## Verify and deploy

```sh
AI_ENABLED=false backend/.venv/bin/python -m pytest -q backend
npm --prefix frontend test
npm --prefix frontend run build
AI_ENABLED=false backend/.venv/bin/python tools/release_smoke.py --asgi
AI_ENABLED=false backend/.venv/bin/python tools/verify_real_dataset.py
```

The commands above explicitly use `AI_ENABLED=false` for offline testing:
OpenCV detection, nesting and SVG export work without Baseten calls. The existing
Render configuration uses `AI_ENABLED=true` with a backend-only secret. See
[Enabling Meta Muse Spark Open on Render](docs/DEPLOYMENT.md#enabling-meta-muse-spark-open-on-render)
for deployment, environment values and one manually triggered inference check.

Live Muse Spark Open recommendations through Baseten were successfully verified
in Chrome during the hackathon demo, using `meta-models/muse-spark-open-1026`.
This does not establish live image-understanding or SAM inference, or acceptance
of a particular public deployment. Live AI consumes credits; never commit API keys.

## Credits

Photographs/annotations: Daniel Costa, João Cruz, Gualter Barros and Nelson Rodrigues
(2024), **CTVG**, Mendeley Data V1, [DOI 10.17632/m5wds8287s.1](https://doi.org/10.17632/m5wds8287s.1),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Original selected JPEG/JSON
bytes and coordinates are preserved; binary masks, thumbnails and cutting layouts
are attributed derivatives. No author endorsement is implied.
[Exact sources, modifications and dataset assessment](docs/DATA_SOURCES.md).

Original hackathon contributions are the application, importer, synthetic test
fixtures, geometry workflow and verification code. React/Vite/FastAPI/Shapely/GEOS
are third-party dependencies. The competition demonstration is submitted separately.
