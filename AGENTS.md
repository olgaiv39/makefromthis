# MakeFromThis: coding-agent handoff

Read this file and [README.md](README.md) before changing the repository. These
instructions apply across the project. Preserve the existing application; do not
start a replacement app or treat historical stage labels as pending feature work.

## A. Project identity and scope

MakeFromThis is a Meta Global AI Developer Hackathon prototype for reusing flat
material. The submission is complete; this is not an industrial cutting solver.
The public flow is upload → automatic outline → confirmation → physical calibration
→ cutting dimensions/quantity → verified layout → SVG export.

- **Implemented:** one-piece photo-only OpenCV detection; user measurement;
  1–50 rectangle/square pieces; cardinal rotations and clearance; independent
  geometry verification; SVG export; optional Baseten AI ideas and image guidance.
- **Test coverage:** deterministic geometry, APIs, CV acceptance/refusal, mocked
  provider transports, environment/security behavior and frontend helpers. Actual
  check results depend on the checkout, assets and environment; report each run.
  Live Muse recommendations were verified by the operator in Chrome during the
  hackathon demo, not by every subsequent automated test.
- **Experimental:** approximate photo segmentation and optional Muse localization.
  Review is mandatory. Do not claim live vision/SAM verification from text inference.
- **Unsupported/future:** arbitrary garment patterns, curves in the public cutting
  operation, automatic seam allowance, scale inference, perspective correction,
  fabric-grain/stretch handling and industrial/global packing optimization. Do not
  implement these without a scoped request. No heavy local model or Xcode is needed.

## B. Repository architecture

Paths below are relative to the repository root; inspect source before editing.

| Path | Responsibility |
| --- | --- |
| `backend/app/main.py` | FastAPI application; scene metadata routes; loads explicitly selected environment; registers layout/AI routes and release middleware/static fallback. Public gallery filtering excludes annotated/synthetic fixtures. |
| `backend/app/ai_api.py` | Bounded image/JSON input validation, availability, photo detection, validated image guidance and geometry-verified cutting-idea ranking. Also retains legacy segmentation/template recommendation routes. |
| `backend/app/material_detection.py` | Image decode/MIME/dimension checks and EXIF normalization; bounded vision JPEG; serialized deterministic OpenCV background hypotheses, GrabCut, contour extraction and conservative ambiguity/topology refusal. |
| `backend/app/cutting_options.py` | Bounded, deduplicated rectangle/square/strip/panel alternatives, safe search grids, actual fit checks and unsupported-project explanations. |
| `backend/app/geometry.py` | Valid finite Polygon/MultiPolygon input; GeoJSON coordinate/complexity bounds; limited binary SVG mask parsing and pixel-to-mm conversion for internal fixtures. |
| `backend/app/nesting.py` | Deterministic grid placement, cardinal rotations, independent `verify()` and guarded `svg_layout()` with physical mm dimensions. |
| `backend/app/layout_api.py` | Layout request validation, work budget, `calculate()`, fit diagnostics and `/api/layouts` + `/api/layouts/svg`; scene scale/attribution handling. Miniature templates are internal demonstrations, not public craft patterns. |
| `backend/app/providers/core.py` | Provider interfaces/configuration, bounded HTTP transport, sanitized errors/telemetry, completion parsing, Baseten image understanding and runtime concurrency/timeouts/optional cache. Legacy Modal adapter is not the public workflow. |
| `backend/app/providers/baseten.py` | Official endpoint/exact model constants, structured ranking schema and allowed/feasible project-ID validation. |
| `backend/app/environment.py` | Explicit backend-only literal env-file parsing; atomic validation; process settings win; no shell execution or secret output. |
| `backend/app/release.py` | Readiness, static assets/SPA fallback, filesystem containment, CSP/security headers, configured CORS and bounded request/CPU admission. |
| `frontend/src/main.tsx` | Five-step in-memory workflow, image/measurement retention, detected-outline acceptance, checked-request state and calibrated complete-layout navigation gates. |
| `frontend/src/api.ts` | Same-origin API/image reads, abort handling, friendly errors with separate diagnostic codes and SVG response handling. |
| `frontend/src/components/` | `UploadOrDemo`, `AutomaticOutline`, `CalibrationPanel`, `ProjectPicker`, `LayoutPreview`, `ResultsDownload`; `AIActions` requests optional ideas. `ImageStage`/`ErrorMessage` support display/errors. Legacy `MaterialOutlineEditor` is not the public detection flow. |
| `frontend/src/types.ts` | Shared frontend data contracts, calibration/geometry helpers, rectangle composition, bounded grid choice and preview eligibility. |
| `tools/start_release.py` | One-service Uvicorn entry point, private-file loading and local/container host/port/browser-URL configuration. |
| `tools/release_smoke.py` | Offline production-asset/API/layout/SVG checks; `--asgi` is in-process, `--url` uses real HTTP. Requires AI disabled on the target. |
| `tools/baseten_live_smoke.py` | Explicitly gated single-inference smoke with a billing-status GET and sanitized metrics; never run implicitly. |
| `Dockerfile` / `render.yaml` | Multi-stage frontend + Python 3.12 image, non-root single-service runtime; existing Render Blueprint enables AI and prompts for its secret. |
| `docs/DEPLOYMENT.md` | Detailed runtime/environment, Render/Baseten configuration and verification procedures. |

## C. Execution modes

All commands run from the repository root. Use Python 3.12 and Node.js 20+;
install runtime pins/build assets using [Quick Start](README.md#quick-start).
Do not install dependencies into an unrelated Python interpreter.

1. **Offline local:**
   `AI_ENABLED=false backend/.venv/bin/python tools/start_release.py`.
   Open **http://127.0.0.1:8000**; OpenCV, calibration, nesting and SVG work without
   cloud credentials. Normal automated checks explicitly disable AI.
2. **Local live Baseten:** only with explicit inference authorization and a private
   key configured by the operator, follow [optional AI setup](README.md#enable-meta-muse-spark-open):
   `AI_ENABLED=true MFT_ENV_FILE="$PWD/backend/.env.local" backend/.venv/bin/python tools/start_release.py`.
   The launcher selects `MFT_ENV_FILE` when nonempty, otherwise the existing
   `backend/.env.local`. Process settings override file values. Ordinary `.env`
   files are not discovered. Direct Uvicorn needs explicit `MFT_ENV_FILE` for a file.
3. **Production-style:** [Docker](README.md#docker) builds React and serves assets
   and API on one origin, with `BIND_HOST=0.0.0.0` inside the container. Docker
   defaults to AI disabled; the committed Render Blueprint sets `AI_ENABLED=true`
   and supplies `BASETEN_API_KEY` through a private environment secret. `/ready`
   is its health check. See [Render instructions](docs/DEPLOYMENT.md#enabling-meta-muse-spark-open-on-render).
   Local files/credentials are not deployed. GitHub is source hosting, not proof
   of a running public app. No GPU or paid deployment is needed for local work.

## D. AI integration boundaries

- **OpenCV** derives the pixel contour. **Shapely/GEOS** validate geometry;
  deterministic placement and independent checking live in the nesting engine.
- **Meta Muse Spark Open**, served through **Baseten**, ranks only supplied,
  geometry-verified cutting options and optionally interprets the photo to guide
  segmentation. Both public AI features use the existing recommendation profile.
- Exact model: `meta-models/muse-spark-open-1026`.
- Direct HTTP Chat Completions endpoint:
  `https://inference.baseten.co/v1/chat/completions`. Do not replace it with the
  SDK base URL `/v1`, substitute another model/provider or add a SAM service.
- Configuration uses `AI_ENABLED`, `BASETEN_API_KEY`, `RECOMMENDATION_PROVIDER`,
  `RECOMMENDATION_ENDPOINT_URL`, `RECOMMENDATION_MODEL_ID` and
  `RECOMMENDATION_MAX_TOKENS`. Keep `SEGMENTATION_PROVIDER=disabled` for the public
  flow. No Meta Model API credential or Modal deployment is required.
- Muse does **not** produce a verified segmentation mask, infer physical scale,
  override deterministic checks or generate an arbitrary garment pattern.
  Preserve strict structured-response/ID validation and truthful provenance.
- `GET /api/ai/availability` makes no inference call. Availability is configuration
  readiness, not proof of authentication, credits, live inference or good pixels.

## E. Geometry correctness invariants

Never weaken these conditions to make an example appear successful:

- Every placed piece is contained in usable material, with no positive-area overlap.
- Required minimum clearance applies both between pieces and to material boundaries,
  including holes. Declared rotations/transforms must reconstruct the requested part.
- Pixel coordinates, user-supplied calibration and physical millimeters stay
  consistent. Never invent dimensions from a photograph or present illustrative
  fixture scale as a measured cutting file.
- All requested pieces must be present exactly once. Incomplete/invalid layouts
  must never be exported or labeled successful.

`geometry.from_geojson()` validates input. `layout_api.calculate()` enforces request
and work budgets. `nesting.nest()` calls independent `nesting.verify()` to check
shape/transforms, containment, overlaps, clearance and completeness. Both
`layout_api.cutting_svg()` and `nesting.svg_layout()` guard export; frontend
calibration/preview gates are additional protection, not replacements for backend
validation. The heuristic is deterministic, not globally optimal; an incomplete
search is not proof of physical impossibility.

## F. Computer vision constraints

Photo-only detection uses actual pixels, not stored annotation masks. The user must
confirm the detected contour before calibration. Keep conservative refusal of
unclear foreground, incomplete edges, competing materials, occlusion/tools,
ambiguous enclosed regions, unsupported holes and excessively complex contours.
Large rectangular material must not be rejected solely for being rectangular.
AI localization is seed guidance, never a polygon substituted from a bounding box.

The supported photograph has one isolated, flat piece, its full edge visible and
a contrasting background. No automatic scale estimate or public manual-vertex
tracing is part of this flow. Internal synthetic/CTVG fixtures and legacy API tests
are regression evidence, not user-facing automatic detection capabilities.

## G. Tests and verification

Use existing dependencies first. Install `pytest==8.4.2` separately only if backend
testing requires it; it is not a runtime dependency. Commands below are offline:

| Change | Relevant checks from repository root |
| --- | --- |
| Geometry/layout | `AI_ENABLED=false backend/.venv/bin/python -m pytest -q backend/test_geometry.py backend/test_api.py backend/test_craft_cutting.py backend/test_step4.py` |
| CV detection/refusal | `AI_ENABLED=false backend/.venv/bin/python -m pytest -q backend/test_automatic_detection.py` |
| AI transport/parsing | `AI_ENABLED=false backend/.venv/bin/python -m pytest -q backend/test_ai_integration.py backend/test_baseten_activation.py backend/test_step4.py` — transports are mocked, not live inference. |
| Frontend | `AI_ENABLED=false npm --prefix frontend test` and `AI_ENABLED=false npm --prefix frontend run build` |
| Release/environment | `AI_ENABLED=false backend/.venv/bin/python -m pytest -q backend/test_release.py backend/test_environment.py` then `AI_ENABLED=false backend/.venv/bin/python tools/release_smoke.py --asgi` after building React. |
| Documentation | Check shell syntax, existing paths, relative links/anchors, env semantics, clean demo URL and diff whitespace; do not execute installation, deployment or paid smoke commands merely to lint docs. |

Full suite: `AI_ENABLED=false backend/.venv/bin/python -m pytest -q backend`.
Frontend checks live in `frontend/tests/geometry.test.cjs` and `ux.test.cjs`.
Optional real-browser prerequisites and commands are in
[deployment verification](docs/DEPLOYMENT.md#reproducible-verification-and-browser-acceptance).
ASGI tests are not browser acceptance; mocked transports are not live AI.

Known public-clone gap: the positive `Cutting_mat.jpg` fixture is tracked, but
two tests in `backend/test_automatic_detection.py` use local-only
`examples/craft_photos/incoming/Cutting_tools_sewing.jpg`. A clone without that
original fails those tests with missing-file errors. Disclose the gap; do not
silently skip/weaken tests, invent a substitute, or redistribute unreviewed assets.
Report exact commands, actual outcomes and unverified behavior, not historical
passing counts or assumptions about another machine.

## H. Secrets, costs and external services

- Never read, print, copy or commit private API key values. Operators configure
  keys themselves. Never include credentials in examples/logs, browser bundles,
  `VITE_*` variables, Docker images/build arguments or screenshots.
- Do not perform paid inference without explicit authorization. `LIVE_AI_TEST=1`
  is the standalone smoke gate, not permission to run it during normal tests.
  It makes at most one inference request; billing availability does not establish
  remaining credits. No automatic retries or silent provider/model substitutions.
- Respect existing upload/response bounds, geometry budgets, timeouts, cancellation,
  request/concurrency limits and cache defaults. Preserve safe offline operation
  and graceful, accurately labeled AI errors/fallbacks. Use budget-aware execution.
- Do not deploy, commit, push or modify hosting settings without authorization.
  Do not stage unrelated work. Never download weights, provision GPUs or require
  another paid service to run the deterministic application.

## I. Agent workflow

1. Read this file and README, then inspect source relevant to the request.
2. Understand existing API contracts, state/navigation gates and tests before editing.
3. Make the smallest coherent change; preserve working components and user files.
4. Preserve geometry, CV refusal, security, attribution and calibration invariants.
5. Run relevant offline checks using the intended interpreter and installed tools.
6. Report changed files, actual checks and any unverified behavior or limitations.

No speculative refactors, unnecessary dependencies, replacement apps or AI-generated
approximations of validated geometry/provider modules. Never silently weaken tests,
fabricate results/live SAM claims, or call deterministic fallback live AI. Stay in
the authorized scope; do not clean environments, remove user assets or expand
features merely because an implementation could be improved.

## J. Documentation and source of truth

Source code and actual tests determine implemented behavior. README is the public
getting-started guide; `docs/DEPLOYMENT.md` owns detailed runtime/provider/deployment
instructions; this file owns contributor/agent guidance. Keep links and commands
consistent and avoid copying entire guides here. Never invent verification results
or hosted URLs. The clean demo URL is `https://youtu.be/ZmWH-WzxUy0`.

## K. Project preservation

Preserve licensed examples, source attribution, deterministic verification,
regression fixtures and submission-relevant functionality. Keep original hackathon
contributions distinct from dataset/third-party code and model capabilities. See
[photo credits](docs/PHOTO_CREDITS.md) and [data sources](docs/DATA_SOURCES.md).
Do not publish private research notes, internal task histories, unrelated projects,
personal information or development credentials. Root `AGENTS.md` belongs in the
public repository; keep it tracked and review changes like other documentation.
