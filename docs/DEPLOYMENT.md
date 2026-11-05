# Deployment and configuration

## Installation and one-service startup

Use Python 3.12 and Node 20+ (Docker pins patch-version Node/Python bases). From
repository root, install reproducible runtime pins and build the frontend. The
[README Quick Start](../README.md#quick-start) is the recommended first launch;
pytest is needed only for tests.

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --only-binary=:all: -r backend/requirements-runtime.lock
backend/.venv/bin/python -m pip check
backend/.venv/bin/python -c 'import shapely; from shapely.geometry import box; assert box(0,0,1,1).area == 1'
npm --prefix frontend ci
npm --prefix frontend run build
REQUIRE_FRONTEND=true AI_ENABLED=false backend/.venv/bin/python tools/start_release.py
```

Open **http://127.0.0.1:8000**. `BIND_HOST` defaults to `127.0.0.1`; Docker and
Render explicitly set `BIND_HOST=0.0.0.0`. Always open the browser URL printed by
the launcher, rather than a wildcard bind address. React assets, `/api`, scene images/masks/annotations
and SPA navigation share one origin. There is no production localhost API setting.
The build uses `frontend/package-lock.json`; Python pins include NumPy, Shapely,
Pillow, headless OpenCV 4.10.0.84 and transitive dependencies. Registry access or compatible cached wheels
is required. Do not remove Shapely to bypass installation failures.

```sh
docker build --pull=false -t makefromthis:local .
docker run --rm -p 8000:8000 --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m --cap-drop ALL \
  --security-opt no-new-privileges --cpus=1 --memory=512m \
  -e AI_ENABLED=false makefromthis:local
```

The Docker image builds React, installs binary Python wheels, asserts real Shapely,
runs as a non-root user and packages internal regression assets. The public
gallery is empty; users upload a photo for automatic detection.
It needs no GPU, model weights, database, Xcode or persistent disk. Fixed base tags
are not immutable digests; review base updates/digests before a public release.
Docker execution remains unverified here because daemon access is sandbox-denied.

## Environment and secrets

Defaults work without credentials. Backend settings are ordinary environment
variables. The single-service launcher loads existing `backend/.env.local` when
no `MFT_ENV_FILE` is set; ordinary `.env` files are **not auto-discovered**. To explicitly load a private file:

```sh
if [ ! -f backend/.env.local ]; then
  (umask 077; cp .env.example backend/.env.local)
fi
chmod 600 backend/.env.local
# Edit the existing private file locally; never commit it.
MFT_ENV_FILE="$PWD/backend/.env.local" backend/.venv/bin/python tools/start_release.py
```

The same `MFT_ENV_FILE` works with [direct Uvicorn](../README.md#optional-hot-reload-development)
and the standalone Baseten smoke. Direct Uvicorn loads a private file only when
`MFT_ENV_FILE` is set; it does not discover `backend/.env.local` automatically.
Parsing is backend-only, bounded to 64 KiB and atomic. Existing
process variables take precedence. Supported syntax: `KEY=value`, optional
`export`, full-line comments and matching whole-value quotes. Values are literal:
no shell execution, interpolation, escapes or multiline values. Unknown/non-backend
keys and duplicate entries are rejected with safe line-number codes. Do not put
secrets in `VITE_*`, React source, Docker build arguments, logs or screenshots.
On hosting, prefer the host's runtime secret manager instead of shipping `.env`.

| Variable | Default / purpose |
| --- | --- |
| MFT_ENV_FILE | unset; explicit path to private backend settings |
| PORT | 8000; host may supply it |
| BIND_HOST | 127.0.0.1 locally; 0.0.0.0 explicitly in Docker/Render |
| REQUIRE_FRONTEND | false for API development, true for production |
| FRONTEND_DIST | repository frontend/dist; Docker uses /app/frontend/dist |
| CORS_ORIGINS | empty/same-origin; optional comma-separated exact origins |
| GEOMETRY_MAX_CONCURRENCY | 2; 1–4 expensive jobs per process |
| EXPENSIVE_REQUESTS_PER_MINUTE | 60; bounded process-wide request budget |
| AI_REQUESTS_PER_MINUTE | 10; includes deterministic AI-route fallback requests |
| REQUEST_BODY_TIMEOUT_SECONDS | 15; bounded request-body read |
| AI_ENABLED | runtime default false for offline mode; existing Render Blueprint sets true |
| AI_TIMEOUT_SECONDS | 30; >0 and <=120, whole operation |
| AI_MAX_CONCURRENCY | 2; 1–8 inference slots |
| AI_CACHE_TTL_SECONDS | 0; opt-in process-local cache, <=300 seconds, <=16 entries |
| SEGMENTATION_PROVIDER | disabled for the public automatic workflow; legacy API configuration only |
| RECOMMENDATION_PROVIDER | runtime default disabled; template/Render select baseten; AI_ENABLED=false prevents calls regardless |
| SEGMENTATION_ENDPOINT_URL / RECOMMENDATION_ENDPOINT_URL | explicit full HTTPS gateway URLs; Baseten has exact default below |
| SEGMENTATION_MODEL_ID / RECOMMENDATION_MODEL_ID | served model IDs; Baseten exact default below |
| SEGMENTATION_AUTH_TOKEN / RECOMMENDATION_AUTH_TOKEN | secret gateway credentials; Baseten uses BASETEN_API_KEY instead |
| SEGMENTATION_AUTH_MODE / RECOMMENDATION_AUTH_MODE | explicit none, bearer or header for custom gateways |
| SEGMENTATION_AUTH_HEADER / RECOMMENDATION_AUTH_HEADER | Authorization by default |
| SEGMENTATION_AUTH_PREFIX / RECOMMENDATION_AUTH_PREFIX | empty; literal custom-header prefix |
| SEGMENTATION_SUPPORTS_POINTS / SEGMENTATION_SUPPORTS_BOXES | false; enable only for deployed capabilities |
| RECOMMENDATION_PROTOCOL | structured/custom gateway or openai; Baseten forces openai |
| RECOMMENDATION_MAX_TOKENS | runtime/template default 512; 64–2048; README AI setup and Render use 2048; standalone smoke uses 1024 |
| BASETEN_API_KEY | backend-only Baseten secret |
| LIVE_AI_TEST | not 1 by default; explicit one-request standalone smoke gate |

## Enabling Meta Muse Spark Open on Render

The committed `render.yaml` already enables AI and selects Baseten Muse Spark Open.
This procedure uses that existing configuration; no Blueprint or application edits
are required. OpenCV extracts pixel contours independently of Baseten. Muse ranks
geometry-verified cutting alternatives and optionally provides image understanding
to guide contour extraction. It does not provide a native segmentation mask, SAM
inference, physical measurements or complete garment patterns.

1. **Create or open the service.** In the Render Dashboard, open the existing
   MakeFromThis Docker web service. For a new service, choose **New → Blueprint**,
   connect the approved repository/branch and use its existing `render.yaml`.
   Review the hosting plan and any cost before confirming creation.
2. **Set the secret.** Open the service's **Environment** page and configure
   `BASETEN_API_KEY` as a secret runtime environment variable. The existing
   Blueprint uses `sync: false` so its value is supplied privately in Render.
   Never commit keys, paste them into documentation, print them, or put them in
   `VITE_*`, frontend code or Docker build arguments. All Baseten requests and
   authentication are handled by the backend; the browser calls this app's API.
3. **Confirm the existing runtime values:**

   | Variable | Render value / behavior |
   | --- | --- |
   | `AI_ENABLED` | `true` — already set in the committed Blueprint |
   | `RECOMMENDATION_PROVIDER` | `baseten` |
   | `RECOMMENDATION_ENDPOINT_URL` | `https://inference.baseten.co/v1/chat/completions`; this is also the default when unset/empty |
   | `RECOMMENDATION_MODEL_ID` | `meta-models/muse-spark-open-1026` — retain the exact hackathon model |
   | `RECOMMENDATION_MAX_TOKENS` | `2048` in the existing Blueprint |
   | `SEGMENTATION_PROVIDER` | `disabled` — default; no separate segmentation provider is needed |
   | `AI_CACHE_TTL_SECONDS` | `0` by default; keep disabled for a fresh live verification |

   Both text recommendations and optional image understanding share the
   `RECOMMENDATION_*` settings and `BASETEN_API_KEY`. The client uses direct HTTP:
   retain the full `/v1/chat/completions` endpoint, not the SDK base URL `/v1`.
   Keep the existing `BIND_HOST=0.0.0.0`, `REQUIRE_FRONTEND=true` and `/ready`
   health-check path. No GPU service is required.

   **`backend/.env.local` is local only.** It is not the Render secret store and
   must not be committed or shipped. Configure Render runtime environment
   variables directly; do not set `MFT_ENV_FILE` to a path on your MacBook.
4. **Apply and deploy.** For runtime-variable changes, select **Save and deploy**.
   Use **Save, rebuild, and deploy** when a rebuild is needed. If you selected
   **Save only**, the changes take effect on the next deploy, so redeploy the
   approved build/commit and wait for it to become healthy. See Render's
   [environment-variable instructions](https://render.com/docs/configure-environment-variables).
5. **Check readiness and configuration without inference.** Replace the placeholder
   with the actual service URL:

   ```sh
   export PUBLIC_URL='https://YOUR-SERVICE.onrender.com'
   curl --fail --silent --show-error "$PUBLIC_URL/ready"
   curl --fail --silent --show-error "$PUBLIC_URL/api/ai/availability"
   ```

   Expect HTTP 200 and `status: "ready"` from `/ready`. In availability, confirm
   `ai_enabled: true`, both `material_vision.available` and
   `recommendation.available` are `true`, and both entries report provider
   `baseten` with model ID `meta-models/muse-spark-open-1026`.
   These GET requests do not call Baseten. **Availability checks configuration,
   not successful authentication, remaining credits or real inference.** Readiness
   also does not require AI to be working.
6. **Verify one manually triggered live recommendation.** Refresh the deployed app,
   upload one unobstructed flat material photograph and select **Use photo-only
   detection** to avoid a separate paid image-understanding request. Review and
   accept the outline, supply a real measurement, then reach **Choose cutting
   pieces**. Enter the material and intended use. Open browser Developer Tools →
   Network and press **Suggest ideas with AI** once.

   Inspect `POST /api/ai/cutting-ideas?use_ai=true`: success requires HTTP 200,
   `status: "live_ai"`, a nonempty `ranked_projects` list and provenance containing
   provider `baseten` and the exact model ID. With caching disabled, this confirms
   a fresh validated inference response. `deterministic_fallback` or
   `no_verified_fits` is not live-inference success. Record only the HTTP status
   and safe error code if it fails; never copy keys, authentication headers or
   model reasoning, and do not automatically retry. Choose a returned size,
   check the fit and confirm a complete verified layout before downloading SVG.

   **Live inference consumes Baseten credits.** Opening the app, checking
   availability, OpenCV photo-only detection, **Check how many fit** and **Find
   fitting options** do not invoke Muse. Optional image understanding and
   **Suggest ideas with AI** do. There is no automatic paid retry.

A real Muse recommendation response was successfully verified in Chrome during
the hackathon demo, as confirmed by the operator. That evidence is separate from
verification of this Render deployment and does not establish live vision or SAM
inference. Offline tests explicitly use `AI_ENABLED=false`; an AI-enabled Render
service uses its existing `AI_ENABLED=true` configuration and private secret.

## Baseten: configuration and diagnostics

The existing adapter uses [Baseten's documented OpenAI-compatible endpoint and
Bearer authentication](https://docs.baseten.co/inference/model-apis/overview).
**Endpoint:** `https://inference.baseten.co/v1/chat/completions`.
**Exact hackathon model:** `meta-models/muse-spark-open-1026`; do not substitute the
unqualified model slug. The hackathon-specific entitlement is account-dependent.
[Baseten documents](https://docs.baseten.co/inference/structured-outputs) that Muse
accepts `json_schema` but **does not enforce it**. Local strict ranking validation
and independently verified template feasibility remain authoritative. Wrong IDs,
infeasible projects, extra fields, invalid JSON and incomplete output are rejected.

Set these in the backend runtime environment or explicitly selected private file:

```sh
export RECOMMENDATION_PROVIDER=baseten
export RECOMMENDATION_ENDPOINT_URL=https://inference.baseten.co/v1/chat/completions
export RECOMMENDATION_MODEL_ID=meta-models/muse-spark-open-1026
export RECOMMENDATION_MAX_TOKENS=2048
export SEGMENTATION_PROVIDER=disabled
# Supply BASETEN_API_KEY securely through host secrets or private .env; no key here.
```

Check billing/credits in the correct workspace before approving inference. The
management usage-history endpoint cannot confirm a remaining promotional balance.
With the key securely exported, explicitly authorize **one** standalone request:

```sh
LIVE_AI_TEST=1 backend/.venv/bin/python tools/baseten_live_smoke.py
# Or, for an explicitly selected private file:
MFT_ENV_FILE="$PWD/backend/.env.local" LIVE_AI_TEST=1 backend/.venv/bin/python tools/baseten_live_smoke.py
```

Choose one command, not both. The smoke prechecks actual geometry, performs a
read-only billing GET, then at most one 1024-completion-token inference POST with
reasoning_effort=low and temperature=1.0. No automatic retry/model substitution.
Only after reviewing response validity and budget set AI_ENABLED=true and restart
the backend. Public AI enables ongoing requests subject to existing limits;
activation is an operator spending decision, separate from deterministic hosting.

The operator reported one earlier response: HTTP 200, 2765 ms, prompt 335,
completion 256 tokens, `incomplete_provider_output`; billing GET returned 403.
That proves transport access, not a validated live recommendation. Billing 403 is
independent of inference status. The operator subsequently reported a successful
structured recommendation smoke (`structured_recommendation_valid=true`). This
does not verify multimodal image understanding or automatic photo acceptance.
No paid calls were made while implementing automatic detection.
Sanitized smoke fields include HTTP status/latency, model, finish_reason, visible
content presence/character count, completion tokens and optional reasoning-token
count. Raw answers/reasoning, auth headers and keys are never printed.
`incomplete_provider_output` rejects finish reasons other than stop/absent;
`malformed_provider_output` identifies unreadable JSON/empty content;
`invalid_recommendation_output` identifies schema/feasible-ID rejection;
`provider_authentication_failed`, `provider_timeout` and `provider_unavailable`
remain separate transport failures. `geometry_unavailable` means **Shapely failed
local preflight before any billing/inference request**, not a Baseten failure.

## Existing API contracts and geometry

- GET `/health`: liveness. GET `/ready`: real geometry, Pillow and packaged assets;
  production additionally requires the built UI. AI health is not required.
- GET `/api/demo-scenes`: public photograph choices (currently empty). Fixture detail routes remain
  available for reproducibility, never normal gallery/offline fallback choices.
- GET `/api/demo-scenes/{id}` and `/{id}/material`: source metadata and polygons;
  photograph material is in pixels until explicit calibration.
- GET `/api/project-templates`: three existing miniature templates.
- POST `/api/layouts` and `/api/layouts/svg`: `template_id`, clearance_mm/grid_mm;
  either `material_mm` GeoJSON or scene_id. Photograph scenes additionally require
  scene_mm_per_pixel and scene_scale_mode (`illustrative` or `user_calibrated`).
  Custom parts_mm accepts 1–50 parts; source_scene_id preserves attribution
  when geometry originates from an attributed scene. Invalid input returns 422, unknown IDs 404.
- Masks are binary black/white SVG rect/polygon paint order, preserving holes and
  disconnected regions. The reader rejects unsupported transforms/styles/paths;
  it is not a general raster tracer. Geometry also accepts Polygon/MultiPolygon.
- Nesting uses fixed-grid/area-then-ID ordering and 0/90/180/270 rotations. Clearance
  applies to boundaries/holes and other parts. A separate verifier checks all
  placements/transforms, containment, overlap, clearance and completeness.
  Utilization is placed area / usable material area. Incomplete search is not a
  proof of infeasibility; SVG export refuses incomplete layouts with 422.
- SVG uses mm dimensions, matching viewBox and even-odd paths. Dataset attribution
  and illustrative warnings are retained. Print real calibrated exports at 100%.
- GET `/api/ai/availability` makes no inference call. POST `/api/ai/recommend`
  accepts material_type, matching calibrated width_mm/height_mm, material_mm,
  preferences and layout constraints. Returns ranked existing IDs/explanations,
  explicit live_ai/deterministic_fallback and provider/model provenance.
- POST `/api/ai/segment` accepts raw PNG/JPEG/WebP bytes (not multipart), matching
  Content-Type, optional prompts JSON query with points [[x,y,label]] and boxes
  [[xmin,ymin,xmax,ymax]], normalized to [0,1]. Limits: 32 points, 8 boxes.
  Configured Modal gateway receives model, image {mime_type,base64}, prompts;
  returns 1–8 masks {geometry: normalized Polygon/MultiPolygon, confidence?:0..1}.
  The response is validated before calibration; disabled AI returns 503.

The public workflow does not use the legacy segmentation endpoint or any Modal
service. Keep SEGMENTATION_PROVIDER=disabled. It uses Baseten only for optional
textual image understanding and cutting ideas:

- POST `/api/ai/detect-material?use_ai=false`: raw JPEG/PNG/WebP, <=8 MiB,
  48..8192 pixels per axis, <=16 MP. EXIF orientation is applied; metadata stripped.
  `use_ai=true` requires enabled, authenticated Baseten with the exact hackathon
  endpoint/model. It makes at most one request with standard `image_url` content
  ([Baseten vision contract](https://docs.baseten.co/inference/model-apis/vision)),
  JPEG <=1024px / 1 MiB, max_tokens=1024, reasoning_effort=low, temperature=1.0.
  Strictly validated material classification, normalized approximate region,
  flatness and risks guide pixel processing; model coordinates never become
  cutting geometry. Failure is explicit, with no automatic paid retry/fallback.
- OpenCV normalizes colour, evaluates border and spatial background hypotheses,
  refines foreground with GrabCut and extracts/simplifies the actual contour.
  Processing uses bounded hypotheses and a 768px image, one worker at a time. Ambiguity, competing pieces,
  internal holes and missing edges are refused. Output is approximate, requires
  user confirmation, and is not SAM or ground truth. No dimensions are inferred.
- POST `/api/ai/cutting-ideas`: calibrated geometry/width/height, preferences,
  piece_width_mm, piece_height_mm, quantity (1..50), clearance and grid. Only
  parameterized rectangles/squares with independently verified complete fits
  can be ranked. Returned options supply actual dimensions. Offline status is
  explicit; deterministic results are never labeled AI.


## Bounds and public deployment

Uploads: browser and detection API <=8 MiB, 8192 pixels/axis, <=16 million pixels,
verified MIME/decoding and EXIF normalization. Geometry/recommendation bodies
<=256 KiB; query <=8 KiB; <=2048 vertices/geometry and coordinates <=1,000,000.
Solver limits 50 parts/250,000 candidates plus API weighted-work budget 10,000,000;
increase grid size if exceeded. Busy requests return 429 instead of unbounded queues.
One worker/32 connections and global process budgets limit resource usage; replicas
have separate budgets. Upstream HTTPS must bound headers/connections too.
Static paths reject traversal, dotfiles and symlink escapes; API misses remain JSON.
CORS is same-origin unless explicitly configured. Provider redirects/proxy env are
off; URLs reject credentials, query/fragment secrets and literal private addresses.
Endpoint DNS is operator-trusted, not a general SSRF/rebinding firewall.

After tests and explicit push/deployment approval, publish the reviewed repository
and use existing render.yaml via Render Dashboard **New → Blueprint**. It requests
one Docker web service, the existing AI-enabled Baseten profile, a private key
prompt, /ready health check and free plan. Review actual
plan availability/cost; do not substitute paid hosting automatically. Any compatible
Docker host is an alternative; no free hosting or public success is assumed.
For an existing approved Render service:

```sh
render login
render deploys create "$RENDER_SERVICE_ID" --commit "$(git rev-parse HEAD)" --wait
export PUBLIC_URL='https://ACTUAL_APPROVED_HOST'
curl --fail "$PUBLIC_URL/health"
curl --fail "$PUBLIC_URL/ready"
curl --fail "$PUBLIC_URL/api/ai/availability"
```

For the AI-enabled service, follow the Render section above for one manually
triggered inference check. `tools/release_smoke.py` is an offline-mode check and
requires `AI_ENABLED=false` on its target service.

No push, deployment, GPU or paid inference is authorized by these commands alone.
.gitignore/.dockerignore exclude .env, keys, venvs, node_modules, dist, caches,
archives, model weights and unrelated large datasets. Only selected attributed
assets/fixtures belong in the repository; frontend and Python locks are retained.

## Reproducible verification and browser acceptance

```sh
backend/.venv/bin/python -m pip install pytest==8.4.2
AI_ENABLED=false backend/.venv/bin/python -m pytest -q backend
AI_ENABLED=false npm --prefix frontend test
AI_ENABLED=false npm --prefix frontend run build
AI_ENABLED=false backend/.venv/bin/python tools/release_smoke.py --asgi
AI_ENABLED=false backend/.venv/bin/python tools/verify_real_dataset.py
AI_ENABLED=false backend/.venv/bin/python tools/verify_demo_scenes.py
```

Internal fixtures remain separate from the public gallery. CTVG provenance and
reimport details are in [DATA_SOURCES.md](DATA_SOURCES.md). ASGI tests exercise
actual routes/assets/geometry, not browser clicks. The tracked
[Cutting_mat.jpg](../examples/craft_photos/incoming/Cutting_mat.jpg) is a real
automatic-detection example; its scale is unknown, so test measurements must not
be presented as physical ground truth. See [photograph credits](PHOTO_CREDITS.md).
Optional browser test, using an already installed Playwright and Chrome, Node 20+:

```sh
SMOKE_URL=http://127.0.0.1:8000 npm --prefix frontend run smoke
# Optional existing installations: PLAYWRIGHT_MODULE=/absolute/path/to/playwright
# CHROME_PATH=/absolute/path/to/chrome
```

Live Muse recommendations were verified by the operator in Chrome during the
hackathon demo. The commands above do not independently establish current browser,
iPhone Safari, console-clean, actual file-saving or public HTTPS acceptance.
On a permitted host, verify ordinary photograph upload → Find material → review → Use this outline → scale gate →
user measurement → rectangle size and quantity → fit → preview → SVG download.
Go Back and confirm the image persists. Then test automatic detection refusal,
missing-measurement gating, offline AI messaging and direct infeasible SVG refusal.
On actual iPhone Safari, test portrait/landscape overflow, photo picker/EXIF,
outline acceptance, reference-marker taps, VoiceOver/focus/zoom, and saving/reopening SVG in Files.
