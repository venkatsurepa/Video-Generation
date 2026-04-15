# ============================================================
# CrimeMill Backend — Docker image
# ============================================================
# Build context: repository root (not backend/)
#   Railway: dockerfilePath = "backend/Dockerfile", context = repo root
#   Local:   docker build -f backend/Dockerfile .
#
# Layer strategy (top = rarely changes, bottom = changes often):
#   1. System deps (ffmpeg, curl)        — changes: ~never
#   2. Node.js runtime                   — changes: ~never
#   3. Python deps (pyproject.toml)      — changes: weekly
#   4. Node deps (package.json)          — changes: weekly
#   5. Application code (src/)           — changes: every commit
# ============================================================

FROM python:3.12-slim AS base

# --- Layer 1: System dependencies (cached — rarely changes) ---------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl && \
    rm -rf /var/lib/apt/lists/*

# --- Layer 2: Node.js for Remotion bridge (cached — rarely changes) -------
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r crimemill && useradd -r -g crimemill -d /app crimemill

WORKDIR /app

# --- Layer 3: Python deps (cached until pyproject.toml changes) -----------
COPY backend/pyproject.toml backend/
RUN cd backend && pip install --no-cache-dir .

# --- Layer 4: Remotion deps (cached until package.json changes) -----------
COPY video/package.json video/package-lock.json* video/
RUN cd video && npm ci --omit=dev 2>/dev/null || npm install --omit=dev

# --- Layer 5: Application code (changes frequently — last layer) ----------
COPY backend/src/ backend/src/
COPY backend/assets/ backend/assets/
COPY video/src/ video/src/
COPY video/tsconfig.json video/remotion.config.ts video/
COPY video/scripts/ video/scripts/
RUN chmod +x video/scripts/*.sh 2>/dev/null || true

# Create tmp directories for pipeline artifacts.
# Railway provides 100GB ephemeral disk — use /tmp for all transient files.
RUN mkdir -p /tmp/crimemill/images /tmp/crimemill/audio /tmp/crimemill/renders && \
    chown -R crimemill:crimemill /tmp/crimemill

USER crimemill

ENV PYTHONPATH=/app/backend
ENV NODE_PATH=/app/video/node_modules
ENV TMPDIR=/tmp/crimemill

# Railway injects PORT=8080 at runtime. Default to 8080 so the EXPOSE
# directive below resolves to 8080 at build time, matching the runtime PORT
# and making Railway's image-manifest port detection align with uvicorn.
ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

EXPOSE ${PORT}

# CLI alias: docker exec <ctr> python -m src.cli <cmd>
# Default CMD for local. Railway overrides via startCommand.
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
