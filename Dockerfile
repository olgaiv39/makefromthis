# One service: no frontend development server, compiler or GPU in the runtime.
# Override images with reviewed digest-qualified references for immutable releases.
ARG NODE_IMAGE=node:22.16.0-bookworm-slim
ARG PYTHON_IMAGE=python:3.12.11-slim-bookworm
FROM ${NODE_IMAGE} AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
WORKDIR /build/frontend
RUN npm ci --no-audit --no-fund
WORKDIR /build
COPY frontend ./frontend
COPY public ./public
# Curated manual-photo fallback; benchmark/synthetic manifests are backend-only.
COPY backend/app/public-scenes.json ./backend/app/public-scenes.json
RUN npm --prefix frontend run build

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 BIND_HOST=0.0.0.0 AI_ENABLED=false REQUIRE_FRONTEND=true FRONTEND_DIST=/app/frontend/dist \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY backend/requirements-runtime.lock ./backend/requirements-runtime.lock
RUN python -m pip install --no-cache-dir --only-binary=:all: -r backend/requirements-runtime.lock \
    && python -m pip check \
    && python -c "import shapely, PIL; from shapely.geometry import box; assert box(0,0,1,1).area == 1" \
    && useradd --create-home --uid 10001 app
COPY --chown=app:app backend/app ./backend/app
COPY --chown=app:app public ./public
COPY --from=frontend --chown=app:app /build/frontend/dist ./frontend/dist
COPY --chown=app:app tools/start_release.py ./tools/start_release.py
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/ready', timeout=3)"
CMD ["python", "tools/start_release.py"]
