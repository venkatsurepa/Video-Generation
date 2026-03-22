# Architecture

CrimeMill is a monorepo with three main components: a Python backend (FastAPI + CLI), a TypeScript video renderer (Remotion), and SQL database migrations (Supabase PostgreSQL).

## System Overview

```
                    +-------------------+
                    |   CLI (Click)     |
                    |   32 commands     |
                    +--------+----------+
                             |
                    +--------v----------+
                    |   FastAPI API     |
                    |   50+ endpoints   |
                    +--------+----------+
                             |
                    +--------v----------+
                    |   Orchestrator    |
                    |   DAG scheduler   |
                    +--------+----------+
                             |
                    +--------v----------+
                    |   Worker          |
                    |   SKIP LOCKED     |
                    |   Circuit breakers|
                    +--------+----------+
                             |
    +------------------------+------------------------+
    |            |           |           |            |
+---v---+  +----v----+ +----v----+ +----v----+ +-----v-----+
|Script | |Voiceover| | Image   | | Music   | |Thumbnail  |
|Claude | |Fish S2  | | Flux    | | Library | |Flux+Pillow|
+---+---+  +----+----+ +----+----+ +----+----+ +-----+-----+
    |            |           |           |            |
    |       +----v----+ +----v----+ +----v----+       |
    |       |  Audio  | |  Image  | | Caption |       |
    |       | FFmpeg  | | Pillow  | | Whisper |  +----v----+
    |       +----+----+ +----+----+ +----+----+  |Content  |
    |            |           |           |       |Classify |
    |            +-----+-----+-----------+       |Haiku 4.5|
    |                  |                         +----+----+
    |           +------v------+                       |
    |           |   Video     |                       |
    |           |  Assembly   +-----------------------+
    |           |  Remotion   |
    |           +------+------+
    |                  |
    |           +------v------+
    |           |   YouTube   |
    |           |   Upload    |
    |           +------+------+
    |                  |
    +--+-----+--+--+--+
       |     |  |  |  |
  +----v-+ +-v--v+ | +v-----------+
  |Podcast| |Shorts| |Cross-plat  |
  |Publish| |Gen  | |Distribution|
  +------+ +-----+ +------------+
              +----v----+ +---v---------+
              |Community| |Discord      |
              |Post     | |Notification |
              +---------+ +-------------+
```

## Layer Breakdown

### API Layer (`src/api/`)

FastAPI routers organized by domain. All endpoints return Pydantic models and are documented via OpenAPI.

| Router | Prefix | Endpoints | Purpose |
|--------|--------|-----------|---------|
| `health.py` | `/health` | 1 | System health + DB + queue depth |
| `videos.py` | `/api/v1/videos` | 5 | CRUD for video records |
| `channels.py` | `/api/v1/channels` | 3 | Channel management |
| `pipeline.py` | `/api/v1/pipeline` | 3 | Trigger, status, retry |
| `topics.py` | `/api/v1/topics` | 3 | Topic discovery + listing |
| `analytics.py` | `/api/v1/analytics` | 6 | YouTube metrics collection |
| `schedule.py` | `/api/v1/schedule` | 6 | Publishing calendar + review |
| `series.py` | `/api/v1/series` | 7 | Multi-part series CRUD |
| `community.py` | `/api/v1/community` | 5 | Topic submissions |
| `research.py` | `/api/v1/research` | 8 | Research sources + FOIA |

### Pipeline Layer (`src/pipeline/`)

**Orchestrator** (`orchestrator.py`): Reads the DAG from `stages.py`, resolves dependencies, and enqueues jobs. Each video gets 17 pipeline jobs inserted into `pipeline_jobs` with proper dependency ordering.

**Worker** (`worker.py`): Polls `pipeline_jobs` using PostgreSQL `FOR UPDATE SKIP LOCKED` for reliable, concurrent job processing. Features:
- Configurable concurrency via semaphore (`max_concurrent_jobs`)
- Per-provider circuit breakers (Anthropic, Fish Audio, fal.ai, Groq, YouTube)
- Budget enforcement before each stage
- Automatic degradation when budget thresholds are hit
- Timeout handling per stage
- Dead-letter queue for permanently failed jobs
- Healthchecks.io ping integration

### Pipeline DAG

```
script_generation ─────────────────────────────────────┐
├── voiceover_generation                               |
│   ├── audio_processing (+ music_selection)           |
│   └── caption_generation                             |
├── image_generation                                   |
│   └── image_processing                               |
├── music_selection                                    |
│   └── audio_processing (+ voiceover_generation)      |
└── thumbnail_generation                               |
    └── content_classification (+ script_generation) <─┘

audio_processing ──┐
image_processing ──┼── video_assembly ──┐
caption_generation─┘                    ├── youtube_upload
content_classification ─────────────────┘       |
                                                ├── podcast_publish (optional)
                                                ├── shorts_generation (optional)
                                                │   └── cross_platform_distribution
                                                ├── localization (optional)
                                                ├── community_post (optional)
                                                └── discord_notification (optional)
```

### Service Layer (`src/services/`)

23 service classes, each responsible for a single pipeline stage or cross-cutting concern:

| Service | External Dependency | Purpose |
|---------|-------------------|---------|
| `script_generator.py` | Anthropic Claude | Generate narration scripts |
| `voiceover_generator.py` | Fish Audio S2 | Text-to-speech synthesis |
| `image_generator.py` | fal.ai Flux Pro | AI image generation |
| `music_selector.py` | Local library | Select mood-matched music |
| `audio_processor.py` | FFmpeg, pydub | Mix voice + music, normalize loudness |
| `image_processor.py` | Pillow, NumPy | Ken Burns effects, resizing |
| `caption_generator.py` | Groq Whisper | Generate SRT captions |
| `video_assembler.py` | Remotion Lambda | Render final video |
| `thumbnail_generator.py` | fal.ai + Pillow | Generate YouTube thumbnails |
| `content_classifier.py` | Claude Haiku 4.5 | YouTube content safety ratings |
| `youtube_uploader.py` | YouTube Data API | Upload + set metadata |
| `podcast_publisher.py` | Buzzsprout API | Publish podcast episodes |
| `shorts_generator.py` | FFmpeg + Remotion | Generate YouTube Shorts |
| `localizer.py` | Claude + Fish Audio | Translate to other languages |
| `cross_platform.py` | Repurpose/Ayrshare | Distribute to TikTok/IG/X |
| `community.py` | Discord, Patreon | Community engagement |
| `series_planner.py` | Claude | Multi-part series planning |
| `topic_selector.py` | GDELT, Reddit | Topic discovery + scoring |
| `research_collector.py` | CourtListener, web | Research source collection |
| `analytics_collector.py` | YouTube Analytics | Collect performance data |
| `performance_analyzer.py` | -- | Analyze video metrics |
| `budget_enforcer.py` | -- | Per-video cost tracking |
| `benchmark.py` | -- | Provider cost comparison |

### Provider Abstraction (`src/services/providers/`)

Pluggable provider system for switching between API and self-hosted models:

```python
# Switch providers with one config change:
tts = ProviderFactory.get_tts_provider("fish_audio", settings, http)    # API
tts = ProviderFactory.get_tts_provider("chatterbox", settings, http)    # Self-hosted GPU
tts = ProviderFactory.get_tts_provider("kokoro", settings, http)        # Self-hosted CPU
```

| Category | API Provider | Self-Hosted Options |
|----------|-------------|-------------------|
| TTS | Fish Audio S2 | Chatterbox (GPU), Kokoro-82M (CPU) |
| Images | fal.ai Flux Pro | Local Flux Dev (GPU) |
| Music | Epidemic Sound Library | ACE-Step v1.5 (GPU) |
| LLM | Anthropic Claude | -- (no viable alternative) |

### Data Layer

**Database**: Supabase PostgreSQL 17 with 38 tables across 13 migrations. Key patterns:
- `pipeline_jobs`: SKIP LOCKED job queue with status tracking
- `video_daily_metrics`: Time-series analytics
- `discovered_topics`: Scored topics with viral potential signals
- Row-level security via Supabase

**Storage**: Cloudflare R2 (S3-compatible) for all media assets:
- Voiceover WAV files
- Generated images
- Rendered videos
- Thumbnails
- Caption SRT files

### Video Renderer (`video/`)

Remotion compositions written in React/TypeScript:
- `CrimeMillVideo`: Main documentary composition
- `CrimeMillShort`: YouTube Shorts variant
- Scene transitions, Ken Burns effects, caption overlay
- Rendered via Remotion Lambda (serverless)

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| API Framework | FastAPI | Async-native, auto OpenAPI docs, Pydantic integration |
| Database | Supabase PostgreSQL | Managed Postgres with auth, realtime, edge functions |
| Job Queue | Postgres SKIP LOCKED | No extra infrastructure, transactional consistency |
| Scripting AI | Claude Sonnet 4 | Best long-form narrative generation |
| Classification | Claude Haiku 4.5 | Fast, cheap structured output |
| TTS | Fish Audio S2 | High-quality voice cloning, fast turnaround |
| Image Gen | fal.ai Flux Pro | Fast inference, good quality, cost-effective |
| Transcription | Groq Whisper | Fastest whisper inference for word-level timestamps |
| Video Render | Remotion Lambda | Programmatic React-based video, serverless rendering |
| Object Storage | Cloudflare R2 | S3-compatible, zero egress fees |
| CLI | Click + Rich | Composable commands, beautiful terminal output |
| Logging | structlog | Structured JSON logging, async-aware |
| Types | mypy strict | Full type coverage across 120 source files |
| Linting | ruff | Fast Python linting + formatting |

## Resilience

- **Circuit breakers**: Per-provider with configurable failure threshold and recovery timeout
- **Retries**: Exponential backoff with jitter on transient failures
- **Budget enforcement**: Hard stop when per-video cost exceeds configurable limit ($15 default)
- **Degradation**: Automatic quality reduction when approaching budget limits (fewer images, shorter scripts)
- **Dead-letter queue**: Failed jobs moved to dead-letter after max retries
- **Idempotent stages**: Safe to retry any stage without side effects
- **SKIP LOCKED queue**: No duplicate processing even with multiple workers
- **Healthchecks.io**: External uptime monitoring with per-stage pings
