# CrimeMill

Automated YouTube true-crime documentary pipeline. Takes a topic and produces a fully rendered, uploaded video — scripting, voiceover, imagery, music, assembly, thumbnails, captions, content classification, and publishing — all orchestrated by a DAG-based pipeline with budget enforcement and circuit breakers.

Built with FastAPI, Remotion, Claude, Fish Audio, fal.ai, and Supabase.

## Architecture

```mermaid
graph TD
    CLI[CLI / API] --> O[Pipeline Orchestrator]
    O --> W[Worker - SKIP LOCKED queue]
    W --> SG[Script Generation<br/>Claude Sonnet 4]
    SG --> VO[Voiceover<br/>Fish Audio S2]
    SG --> IG[Image Generation<br/>fal.ai Flux]
    SG --> MS[Music Selection<br/>Epidemic Sound Library]
    SG --> TH[Thumbnail<br/>Flux + Pillow]
    VO --> AP[Audio Processing<br/>FFmpeg + pydub]
    MS --> AP
    IG --> IP[Image Processing<br/>Pillow + Ken Burns]
    VO --> CG[Caption Generation<br/>Groq Whisper]
    SG --> CC[Content Classification<br/>Claude Haiku 4.5]
    TH --> CC
    AP --> VA[Video Assembly<br/>Remotion Lambda]
    IP --> VA
    CG --> VA
    VA --> YU[YouTube Upload]
    CC --> YU
    YU --> PP[Podcast Publish<br/>Buzzsprout]
    YU --> SH[Shorts Generation]
    YU --> LO[Localization]
    YU --> CP[Community Post]
    YU --> DN[Discord Notification]
    SH --> XP[Cross-Platform<br/>TikTok/IG/X]
    W --> R2[(Cloudflare R2)]
    W --> DB[(Supabase PostgreSQL)]
```

```
API Layer (FastAPI, 50+ endpoints)
         |
Pipeline Orchestrator (DAG state machine, 17 stages)
         |
Worker (SKIP LOCKED queue consumer, circuit breakers)
         |
+------------------+------------------+------------------+-----------+
|   Script Gen     |   TTS            |   Image Gen      |   Music   |
|   (Claude)       |   (Fish S2)      |   (Flux/fal)     |   (Lib)   |
+------------------+------------------+------------------+-----------+
|   Audio Proc     |   Image Proc     |   Captions       |   Thumbs  |
|   (FFmpeg)       |   (Pillow)       |   (Whisper)      |   (Flux)  |
+------------------+------------------+------------------+-----------+
|   Assembly       |   Classifier     |   Upload         |   Post-   |
|   (Remotion)     |   (Haiku)        |   (YT API)       |   Upload  |
+------------------+------------------+------------------+-----------+
         |
Storage (Cloudflare R2) + Database (Supabase PostgreSQL)
```

## Quick Start

```bash
# Clone
git clone https://github.com/your-org/crimemill.git
cd crimemill

# Backend setup
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your API keys (see Full Setup below)

# Run database migrations
npx supabase db push

# Start development server
uvicorn src.main:app --reload --port 8000

# Or use the CLI
python -m src.cli health
```

## Full Setup

### 1. Supabase (Database)

```bash
# Link to your Supabase project
npx supabase link --project-ref YOUR_PROJECT_REF

# Push all 13 migrations
npx supabase db push
```

Required `.env` variables:
```
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
DATABASE_URL=postgresql://postgres:PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres
```

### 2. API Keys

| Service | Variable | Purpose | Cost |
|---------|----------|---------|------|
| Anthropic | `ANTHROPIC_API_KEY` | Script generation, content classification | ~$2-4/video |
| Fish Audio | `FISH_AUDIO_API_KEY` | Text-to-speech voiceover | ~$1-2/video |
| fal.ai | `FAL_API_KEY` | Image generation (Flux Pro) | ~$1-3/video |
| Groq | `GROQ_API_KEY` | Whisper transcription for captions | ~$0.01/video |
| YouTube | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | Upload + analytics | Free |
| Cloudflare R2 | `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Asset storage | ~$0.015/GB |

### 3. Cloudflare R2 (Storage)

Create a bucket named `crimemill-assets` with an API token that has Object Read & Write permissions.

### 4. YouTube OAuth

```bash
python -m src.cli channel create --name "MyCrimeMill" --niche true_crime_general
python -m src.cli channel setup-youtube-auth --channel "MyCrimeMill"
# Follow the browser OAuth flow
```

### 5. Remotion Lambda (Video Rendering)

```bash
cd video
npm install
npx remotion lambda sites create src/index.ts --site-name crimemill
npx remotion lambda functions deploy
```

Set in `.env`:
```
REMOTION_AWS_ACCESS_KEY_ID=...
REMOTION_AWS_SECRET_ACCESS_KEY=...
REMOTION_LAMBDA_FUNCTION_NAME=remotion-render-...
REMOTION_SERVE_URL=https://remotionlambda-...s3.us-east-1.amazonaws.com/sites/crimemill/index.html
```

### 6. Deploy

```bash
# Railway (recommended)
railway link
railway up

# Or Docker
docker build -t crimemill-backend ./backend
docker run -p 8000:8000 --env-file .env crimemill-backend
```

## CLI Reference

### Channel Management
```bash
python -m src.cli channel create --name "CrimeMill" --niche true_crime_general
python -m src.cli channel list
python -m src.cli channel setup-voice --channel "CrimeMill" --sample ./voice.wav
python -m src.cli channel setup-youtube-auth --channel "CrimeMill"
```

### Pipeline Operations
```bash
python -m src.cli pipeline trigger VIDEO_ID [--stage script_generation]
python -m src.cli pipeline status VIDEO_ID
python -m src.cli pipeline retry VIDEO_ID [--stage voiceover_generation]
python -m src.cli pipeline list --channel "CrimeMill" --status pending
```

### Review Workflow
```bash
python -m src.cli review queue --channel "CrimeMill"
python -m src.cli review approve VIDEO_ID
python -m src.cli review reject VIDEO_ID --reason "Needs stronger hook"
```

### Publishing Schedule
```bash
python -m src.cli schedule show --channel "CrimeMill" --days 14
python -m src.cli schedule publish-now VIDEO_ID
```

### Analytics
```bash
python -m src.cli analytics daily --channel "CrimeMill" --days 30
python -m src.cli analytics top-videos --channel "CrimeMill" --limit 10
python -m src.cli analytics costs --days 30
```

### Topic Discovery
```bash
python -m src.cli topics discover --channel "CrimeMill"
python -m src.cli topics list --channel "CrimeMill" --min-score 70
```

### Music Library
```bash
python -m src.cli music library
python -m src.cli music add --file ./track.wav --mood suspenseful_investigation --bpm 90
```

### Series Management
```bash
python -m src.cli series create --channel "CrimeMill" --title "The Vanishing" --type sequential
python -m src.cli series plan SERIES_ID
python -m src.cli series status --channel "CrimeMill"
python -m src.cli series analytics SERIES_ID
```

### Research & FOIA
```bash
python -m src.cli research search "cold case disappearance"
python -m src.cli research collect --topic "Doe v. State"
python -m src.cli research cases --limit 20
python -m src.cli research foia-file --agency "FBI" --subject "Case #12345"
python -m src.cli research foia-list --status pending
```

### Community
```bash
python -m src.cli community submissions list
python -m src.cli community submissions review SUBMISSION_ID --action accept
python -m src.cli community discord-notify --channel "CrimeMill" --message "New video!"
python -m src.cli community metrics --channel "CrimeMill"
```

### Optimization
```bash
python -m src.cli optimize thumbnails VIDEO_ID --variants 3
python -m src.cli optimize titles VIDEO_ID --variants 5
python -m src.cli optimize report --channel "CrimeMill"
```

### System
```bash
python -m src.cli health
python -m src.cli budget --channel "CrimeMill"
```

## API Reference

The FastAPI server exposes OpenAPI documentation at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

See [docs/API.md](docs/API.md) for the full endpoint reference.

## Pipeline Stages

17 stages organized as a DAG with automatic dependency resolution:

| # | Stage | Service | Depends On | Timeout | Retries |
|---|-------|---------|------------|---------|---------|
| 1 | `script_generation` | Claude Sonnet 4 | -- | 120s | 3 |
| 2 | `voiceover_generation` | Fish Audio S2 | 1 | 300s | 3 |
| 3 | `image_generation` | fal.ai Flux Pro | 1 | 600s | 3 |
| 4 | `music_selection` | Epidemic Sound Library | 1 | 60s | 2 |
| 5 | `audio_processing` | FFmpeg + pydub | 2, 4 | 180s | 2 |
| 6 | `image_processing` | Pillow (Ken Burns) | 3 | 120s | 2 |
| 7 | `caption_generation` | Groq Whisper | 2 | 60s | 2 |
| 8 | `video_assembly` | Remotion Lambda | 5, 6, 7 | 300s | 2 |
| 9 | `thumbnail_generation` | fal.ai Flux + Pillow | 1 | 120s | 2 |
| 10 | `content_classification` | Claude Haiku 4.5 | 1, 9 | 60s | 2 |
| 11 | `youtube_upload` | YouTube Data API | 8, 10 | 600s | 3 |
| 12 | `podcast_publish` | Buzzsprout API | 11 | 300s | 2 |
| 13 | `shorts_generation` | FFmpeg + Remotion | 11 | 600s | 2 |
| 14 | `localization` | Claude + Fish Audio | 11 | 900s | 2 |
| 15 | `cross_platform_distribution` | Repurpose/Ayrshare | 13 | 120s | 2 |
| 16 | `community_post` | Discord/Patreon | 11 | 30s | 1 |
| 17 | `discord_notification` | Discord Webhook | 11 | 30s | 1 |

Stages 12-17 are **optional** -- failures don't block the pipeline.

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **API** | FastAPI 0.115+ | REST API with OpenAPI docs |
| **CLI** | Click + Rich | Terminal interface |
| **Database** | Supabase PostgreSQL 17 | Persistent storage, job queue |
| **Queue** | psycopg3 `SKIP LOCKED` | Reliable job processing |
| **Storage** | Cloudflare R2 (S3-compat) | Media asset storage |
| **Scripting** | Claude Sonnet 4 | Script generation |
| **Classification** | Claude Haiku 4.5 | Content safety |
| **TTS** | Fish Audio S2 | Voiceover generation |
| **Images** | fal.ai Flux Pro | AI image generation |
| **Captions** | Groq Whisper | Speech-to-text |
| **Music** | Epidemic Sound (curated) | Background music |
| **Audio** | FFmpeg + pydub | Audio mixing, loudness normalization |
| **Images** | Pillow + NumPy | Image processing, Ken Burns |
| **Video** | Remotion + React | Programmatic video rendering |
| **Rendering** | AWS Lambda (Remotion) | Serverless video rendering |
| **Upload** | YouTube Data API v3 | Video publishing |
| **Podcast** | Buzzsprout API | Podcast distribution |
| **Monitoring** | structlog + Healthchecks.io | Structured logging, uptime |
| **Types** | mypy + ruff | Static analysis, linting |
| **Deployment** | Railway / Docker | Production hosting |

## Cost Breakdown (Per Video)

| Service | Cost | Notes |
|---------|------|-------|
| Claude Sonnet 4 (script) | $2.00-4.00 | ~8K input + ~4K output tokens |
| Claude Haiku 4.5 (classifier) | $0.10-0.20 | Content safety check |
| Fish Audio S2 (voiceover) | $1.00-2.00 | 10-15 min narration |
| fal.ai Flux Pro (images) | $1.00-3.00 | 8-12 scene images |
| fal.ai Flux Pro (thumbnail) | $0.10-0.20 | 1 thumbnail |
| Groq Whisper (captions) | $0.01 | Transcription |
| Remotion Lambda (render) | $0.50-1.00 | ~15 min video |
| Cloudflare R2 (storage) | $0.02 | ~500MB per video |
| **Total per video** | **$5-11** | Budget cap: $15 default |

## Project Structure

```
crimemill/
+-- backend/
|   +-- src/
|   |   +-- api/            # FastAPI routers (10 files, 50+ endpoints)
|   |   +-- cli.py           # Click CLI (32 commands, 10 groups)
|   |   +-- config.py        # Pydantic settings (17 config sections)
|   |   +-- main.py          # FastAPI app entry point
|   |   +-- dependencies.py  # DI container
|   |   +-- models/          # Pydantic models (29 files)
|   |   +-- services/        # Business logic (23 services)
|   |   +-- pipeline/        # DAG orchestrator + worker
|   |   +-- db/              # SQL queries + connection pool
|   |   +-- utils/           # Retry, circuit breaker, storage
|   |   +-- monitoring/      # Health checks
|   |   +-- services/providers/  # Pluggable provider abstraction (9 providers)
|   +-- tests/               # pytest test suite (13 files)
|   +-- assets/              # Music library, fonts
|   +-- pyproject.toml
|   +-- Dockerfile
+-- video/
|   +-- src/                 # Remotion compositions (13 files)
|   +-- package.json
|   +-- remotion.config.ts
+-- supabase/
|   +-- migrations/          # 13 SQL migrations (38 tables, 57 indexes)
+-- docs/                    # Architecture, API, CLI, deployment docs
+-- .env.example
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Make changes and ensure checks pass:
   ```bash
   cd backend
   ruff check src/ tests/        # Linting
   ruff format src/ tests/       # Formatting
   mypy src/ --ignore-missing-imports --no-strict-optional  # Type checking
   pytest                        # Tests
   ```
5. Commit with a descriptive message
6. Open a pull request

### Code Style

- Python 3.12+, fully typed with `from __future__ import annotations`
- Pydantic v2 for all data models
- `structlog` for structured logging
- `psycopg3` async with `dict_row` factory
- Provider abstraction layer for all external APIs

## License

Proprietary. All rights reserved.
