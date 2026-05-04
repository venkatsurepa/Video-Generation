# CrimeMill / Street Level — System Reference Document

**Last updated:** May 4, 2026
**Entity:** Rizpah Investments LLC (Texas Series LLC)
**Repository:** github.com/venkatsurepa/Video-Generation
**Supabase project:** `qflkctgemkwochgkzqzj` (region: us-east-1)
**Railway service:** `travel-street-level-production.up.railway.app`

---

## 1. What This System Does

This is a fully automated YouTube video production pipeline that takes a topic or intelligence report as input and produces a complete, upload-ready video as output. The pipeline handles every stage: scriptwriting, voiceover narration, scene image generation, video assembly, caption generation, thumbnail creation, and YouTube upload.

The system operates two YouTube channels under one codebase with niche-specific routing:

**CrimeMill** — Financial crime documentary content (fraud, corruption, Ponzi schemes, money laundering). 15-minute deep-dive investigations with dark, cinematic visuals and a serious narrator tone.

**Street Level** — Travel safety content powered by geographic risk intelligence from the Rhyo Security Solutions database. 14-minute destination guides, scam breakdowns, and safety briefings with warm, conversational narration. Data partner credited in descriptions only; Street Level presents as an independent channel.

The pipeline is designed to produce videos at ~$0.60–$1.00 per video at scale, enabling high-volume content production with minimal human intervention.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CONTENT SOURCES                          │
├──────────────────────────┬──────────────────────────────────────┤
│  CrimeMill               │  Street Level                       │
│  • Topic backlog (DB)    │  • Rhyo intelligence reports (.md)  │
│  • FOIA requests         │  • Travel advisories (DB)           │
│  • Court documents       │  • Destination analysis             │
│  • News/GDELT signals    │  • Scam pattern library             │
└──────────┬───────────────┴──────────┬───────────────────────────┘
           │                          │
           ▼                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     NICHE ROUTER                                │
│  channel.niche → prompts + generator + archetypes + affiliates  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PIPELINE STAGES (17)                          │
│                                                                 │
│  1. topic_selection        10. caption_generation               │
│  2. research_gathering     11. content_classification (gate)    │
│  3. script_generation      12. thumbnail_generation             │
│  4. scene_breakdown        13. description_generation           │
│  5. image_generation       14. youtube_upload                   │
│  6. voiceover_generation   15. podcast_publishing               │
│  7. music_selection        16. shorts_generation                │
│  8. video_assembly         17. cross_platform_distribution      │
│  9. audio_mastering                                             │
│                                                                 │
│  Stage 11 (content_classification) is a GATE:                   │
│  high-risk content → unlisted for human review                  │
│  safe content → proceeds to upload                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Infrastructure Stack

| Layer | Service | Purpose | Cost |
|---|---|---|---|
| **Database** | Supabase (PostgreSQL 17) | All application data, pipeline state, cost tracking | Free tier (500MB) |
| **Backend/API** | Railway | FastAPI application server + pipeline worker | ~$5/mo (usage-based) |
| **Storage** | Cloudflare R2 | Media file storage (images, audio, video) during assembly | Free tier (10GB) |
| **Video Assembly** | Remotion Lambda (AWS) | Serverless video rendering at 2560×1440 (CrimeMill) or 1080p | ~$0.11/render |
| **Script Generation** | Anthropic Claude Sonnet 4 | Primary scriptwriter — generates full video scripts | ~$0.06-0.09/script |
| **Structured Extraction** | Anthropic Claude Haiku 4.5 | Scene breakdowns, image prompts, titles, destinations | ~$0.01-0.02/call |
| **Voiceover** | Fish Audio S2 | Text-to-speech narration with voice cloning | ~$0.015/second audio |
| **Image Generation** | fal.ai (Flux Dev) | Scene images for video assembly | $0.025/image |
| **Captions** | Groq Whisper Large v3 Turbo | Audio transcription for subtitle generation | Free |
| **Music** | Epidemic Sound / Suno | Background music tracks (manual curation) | $10/mo subscription |
| **Monitoring** | Healthchecks.io + DB views | Uptime pings + SQL-based dashboards | Free tier |

---

## 4. Per-Video Cost Breakdown

| Stage | Service | Typical Cost |
|---|---|---|
| Script generation | Anthropic Sonnet 4 | $0.06–$0.09 |
| Scene breakdown + image prompts | Anthropic Haiku 4.5 | $0.01–$0.02 |
| Title + description generation | Anthropic Haiku 4.5 | $0.01 |
| Image generation (18-20 images) | fal.ai Flux Dev | $0.45–$0.50 |
| Voiceover (~14 min) | Fish Audio S2 | $0.13 |
| Caption generation | Groq Whisper | $0.00 (free) |
| Video assembly | Remotion Lambda | $0.08–$0.12 |
| **Total per video** | | **$0.75–$0.85** |

Budget enforcement: $15.00 hard cap per video with 70% soft warning. Enforced via `check_video_budget()` database function called before each pipeline stage.

---

## 5. Channel Configuration

### CrimeMill (Financial Crime)

| Setting | Value |
|---|---|
| Handle | @crimemill |
| Niche | financial_crime |
| Target length | 15 minutes / 3,000 words |
| Images per video | 20 |
| Script model | Claude Sonnet 4 |
| Structured model | Claude Haiku 4.5 |
| Image model | Flux Dev |
| Thumbnail archetype | interrogation |
| Font | Bebas Neue |
| Color palette | #1a1a2e (dark navy), #e94560 (red), #ffffff |
| Voice | Serious tone, 150 WPM |
| Image style | Dark moody cinematic lighting, high contrast, film noir |

### Street Level (Travel Safety)

| Setting | Value |
|---|---|
| Handle | @streetlevel |
| Niche | travel_safety |
| Target length | 14 minutes / 2,200 words |
| Images per video | 18 |
| Script model | Claude Sonnet 4 |
| Structured model | Claude Haiku 4.5 |
| Image model | Flux Dev |
| Thumbnail archetype | destination_dramatic |
| Font | Montserrat |
| Color palette | #2d3436 (dark gray), #f0932b (warm orange), #ffffff |
| Voice | Warm conversational, 160 WPM |
| Image style | Documentary travel photography, warm natural lighting, golden hour |
| Data partner | Rhyo Security Solutions (rhyo.com) — credited in descriptions only |

**Brand rules for Street Level:**
- The narrator NEVER mentions Rhyo, rhyo.com, or any data provider by name in spoken script
- The narrator says "we pulled the safety data" / "our research shows" / "the numbers say" — vague first-party attribution
- Descriptions include: "Special thanks to Rhyo Security Solutions for providing the safety intelligence data used in this video. Learn more at rhyo.com"
- Street Level NEVER says "we built" or "we created" a safety tool — it positions as a research channel, not a tech company

---

## 6. Street Level Content Pipeline (Travel Safety)

Street Level's content pipeline is distinct from CrimeMill's. It transforms Rhyo intelligence reports into YouTube-ready video scripts.

**Input:** Markdown intelligence report from Rhyo Security Solutions' geographic risk-scoring database (158M H3 hex cells, 9-factor AHP scores, 740+ country indicators, ~10 real-time streaming sources)

**Rhyo report structure (10 sections):**
1. Composite scores (day/night/women safety per H3 hex cell)
2. Cell-level risk factors (9-factor AHP breakdown)
3. Raw signals (29-39 covariates with source citations)
4. Nearest emergency medical facilities
5. State/city-level threats
6. National-level context (740 indicators)
7. Environmental and epidemiological risks
8. Anthropogenic/crime risks
9. Targeted threat profile
10. Data quality disclosures

**Transformation:** `TravelSafetyScriptGenerator` takes the markdown report, selects a video format (safety_briefing, scam_anatomy, destination_guide, things_to_do, crisis_response), and generates a warm conversational script via Claude Sonnet 4. Multi-call pipeline: script → scene breakdown → image prompts → title → description (each a separate Claude call for quality).

**Video formats (5 types, auto-selected based on report content):**
- Destination Guide: "48 Hours in Bangkok: What's Worth Your Time"
- Scam Anatomy: "How the Bali Money Changer Scam Actually Works"
- Safety Briefing: "Is Mexico City Safe in 2026? Real Talk"
- Things to Do: "12 Hidden Spots in Lisbon Locals Don't Want You to Find"
- Crisis Response: "What to Do If Your Passport Gets Stolen Abroad"

**Title formulas (6, rotated — never two of the same kind in a row):**
- Direct question: "Is [Destination] Safe Right Now?"
- Personal hook: "I Spent 30 Days in [Destination] — Here's What Surprised Me"
- Insider angle: "What Locals in [Destination] Wish Tourists Would Stop Doing"
- Numbered list: "7 Scams Targeting Tourists in [Destination]"
- Warning frame: "Don't Visit [Destination] Until You Watch This"
- Practical: "How to Actually Stay Safe in [Destination]"

---

## 7. Rhyo Intelligence Reports Available

Seven destination reports are saved as fixtures, ready to convert to videos when API credits are available:

| Destination | File | Day/Night Score | Key Content Angle |
|---|---|---|---|
| Hyderabad Banjara Hills | hyderabad_banjara_hills.md | 65.1 / 53.1 | Upscale India, road traffic is #1 risk, honey trap scam |
| Hyderabad Old City | hyderabad_old_city.md | 68.7 / 60.1 | Data says safer than Banjara Hills — but it's WRONG (confidence=1 artifact) |
| Bangkok Sukhumvit | bangkok_sukhumvit.md | 69.7 / 30.8 | Massive 56% night safety drop, nightlife predation |
| Mexico City Roma/Condesa | mexico_city_roma_condesa.md | 67.2 / 27.7 | +Tepito comparison (46.5/27.8) — same city, different world |
| Istanbul Sultanahmet | istanbul_sultanahmet.md | 67.3 / 57.9 | Smallest night drop (9.4 pts), richest data (39 covariates) |
| Lisbon Alfama | lisbon_alfama.md | 83.7 / 83.7 | "Clear" band — safest destination, counter-narrative potential |
| Bali Kuta/Seminyak | bali_kuta_seminyak.md | 78.2 / 73.5 | Money changer scam, 2002 Bali Bombings UCDP legacy data |

---

## 8. Automated Topic Discovery

**Status:** ✅ Built and deployed (commits `c265623`, `ff5c090`).

A standalone discovery service polls 7 sources for video-worthy topics, deduplicates against the existing backlog (Jaccard word-overlap + Postgres `pg_trgm` index), optionally scores via Claude Haiku, and writes survivors to `discovered_topics`.

**Sources:**

| Source | Cost | API key | Status (latest run, 2026-05-04) |
|---|---|---|---|
| `reddit` | free | none | ✅ found 91 / saved 91 |
| `advisory` (US State Dept + CDC + UK FCDO) | free | none | ✅ found 51 / saved 6 (CDC + UK feeds upstream-broken; State Dept worked) |
| `wikipedia` | free | none (UA header required) | ✅ found 77 / saved 77 |
| `gdelt` | free | none | ✅ found 21 / saved 20 |
| `google_trends` | free | none (`pytrends`) | ⚠️ Not yet exercised |
| `competitor` (YouTube channel monitoring) | free quota | `YOUTUBE_API_KEY` | ⚠️ Skips silently when key absent |
| `court_listener` (legal cases) | free tier | `COURTLISTENER_API_TOKEN` | ⚠️ Skips silently when token absent |

**Scorer:** `TopicScorer` invokes Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) to assign a composite score from 5 weighted dimensions: virality (30%), narrative_strength (25%), data_availability (20%), competition_gap (15%), timeliness (10%). ~$0.01 per candidate. Currently blocked on Anthropic credit balance — sources still produce candidates with raw heuristic scores when scoring is skipped.

**Deduplication:**
- Within a batch: Jaccard word-overlap > 0.6 → merge
- Against backlog: case-insensitive exact title + Jaccard against `used_in_video_id IS NULL` rows
- Hard floor: Postgres trigram index (`gin_trgm_ops`) on `title` for fast `ILIKE %...%` lookup at insert time

**Orchestrator:** `DiscoveryOrchestrator.run_all()` runs sources in series, dedupes, optionally scores, then routes survivors to each source's `save_candidates()` (which uses `INSERT ... ON CONFLICT DO NOTHING`-style logic). `run_source(name)` runs one source.

**CLI:**
```bash
python -m src.cli discover list-sources               # show registered sources
python -m src.cli discover run-source reddit -v       # run one source verbosely
python -m src.cli discover run-all --score            # all sources + Claude scoring
python -m src.cli discover show-backlog --limit 30    # top unassigned topics by score
```

**HTTP API** (mounted at `/api/discovery`):
- `POST /api/discovery/run` — run every source, return summary JSON
- `POST /api/discovery/run/{source_name}` — run a single source
- `GET  /api/discovery/backlog?limit=20` — top unassigned topics

**Periodic cron:** `_discovery_cron()` in `main.py` runs `run_all(score=False)` every 6 hours when `ENABLE_DISCOVERY_CRON=true`. **Off by default** — set the env var on Railway when you want continuous discovery without manual triggers.

**Competitor seed list (22 channels):**
| Category | Count |
|---|---|
| `true_crime` | 9 |
| `travel_safety` | 4 |
| `financial_crime` | 3 |
| `business_documentary` | 2 |
| `travel_documentary` | 2 |
| `finance_education` | 1 |
| `travel` | 1 |

The competitor scanner skips itself when `YOUTUBE_API_KEY` is missing — adding the key activates it without code changes.

**Latest run (2026-05-04) — top 10 candidates from new discovery sources:**

| Score | Source | Category | Title |
|---:|---|---|---|
| 98.0 | state_dept | destination_safety | Do NOT Travel to Chad Right Now — Here's Why |
| 86.0 | state_dept | destination_safety | Is Jordan Safe? The Advisory Just Changed |
| 86.0 | state_dept | destination_safety | Is Trinidad and Tobago Safe? The Advisory Just Changed |
| 86.0 | state_dept | destination_safety | Is United Arab Emirates Safe? The Advisory Just Changed |
| 86.0 | state_dept | destination_safety | Is DRC Safe? The Advisory Just Changed |
| 86.0 | state_dept | destination_safety | Is Papua New Guinea Safe? The Advisory Just Changed |
| 81.7 | reddit | destination_safety | Unpopular opinion: I loved Brussels! |
| 67.5 | reddit | murder | Collin Griffith shot his father (Feb 14 2023) |
| 62.8 | reddit | murder | Kenneth McDuff: obscure but evil serial killer |
| 62.1 | reddit | cold_case | Missing 16-year-old found dismembered (dating-app meeting) |

Total backlog after the run: **224 unassigned topics** (was 30 before).

---

## 9. Content Backlog

30 topics seeded in `discovered_topics` table (15 per channel), prioritized by composite score:

**CrimeMill (financial_crime) — Top 5:**
1. The Wirecard Scandal: How a $30 Billion Fraud Went Undetected
2. Bernie Madoff: The $65 Billion Ponzi Scheme
3. 1MDB: The $4.5 Billion Malaysian Scandal
4. Elizabeth Holmes and Theranos
5. Enron: The Smartest Guys in the Room

**Street Level (travel_safety) — Top 5:**
1. Is Bangkok Actually Safe? Neighborhood by Neighborhood *(Rhyo report ready)*
2. Mexico City: Which Neighborhoods to Worry About *(Rhyo report ready)*
3. How the Bali Money Changer Scam Works *(Rhyo report ready)*
4. Istanbul After Dark: Safety Data Breakdown *(Rhyo report ready)*
5. The Real Risks in Marrakech *(needs Rhyo report)*

---

## 10. Database Schema

**Supabase project:** `qflkctgemkwochgkzqzj` (PostgreSQL 17, us-east-1)

**Statistics:**
- 50 objects in public schema (42 tables + 8 views)
- 119 indexes
- 24 triggers (13 auto-updated_at + 11 application triggers)
- 87 CHECK constraints
- 64 foreign keys
- 2 materialized views
- 5 pg_cron scheduled jobs
- 1 pgmq message queue
- 38 database functions
- 8 monitoring/reporting views
- RLS enabled on all tables (bypassed by service_role key)

**Core tables:**
- `channels` — YouTube channels with niche routing (financial_crime, travel_safety)
- `channel_brand_settings` — Colors, fonts, thumbnail archetypes per channel
- `channel_voice_settings` — Fish Audio voice ID, speed, emotion per channel
- `channel_generation_settings` — Target length, models, image count per channel
- `videos` — All video records with status tracking through pipeline
- `pipeline_jobs` — Per-stage job queue with status, retry count, error tracking
- `pipeline_transitions` — Stage-to-stage transition log
- `discovered_topics` — Content backlog with priority and source signals
- `script_generations` — Generated scripts with version history
- `scene_images` — Per-scene image generation records
- `voiceover_generations` — TTS generation records
- `video_assemblies` — Remotion render records
- `thumbnail_generations` — Thumbnail generation records
- `generation_costs` — Per-operation cost tracking (provider, model, tokens, cost, latency)

**Travel-specific tables:**
- `travel_advisories` — State Dept/CDC/OSAC advisory tracking
- `video_destinations` — Per-video destination tagging with country codes and SafePath tags
- `partner_app_metrics` — Rhyo/SafePath attribution tracking (not actively used yet)

**Discovery tables:**
- `competitor_channels` — 22 seeded YouTube channels (9 true_crime, 4 travel_safety, 3 financial_crime, 2 business_documentary, 2 travel_documentary, 1 finance_education, 1 travel) consumed by the competitor scanner
- `competitor_videos` — Per-video tracking from competitor channels (view counts, dates, signals)

**Discovery indexes on `discovered_topics`** (4 added for the discovery service):
- `idx_discovered_topics_source` on `(source_signals->>'source')` — fast per-source filtering
- `idx_discovered_topics_channel` on `(source_signals->>'channel')` — per-channel queries
- `idx_discovered_topics_unused_score` partial index `(composite_score DESC) WHERE used_in_video_id IS NULL` — backlog top-N
- `idx_discovered_topics_title_trgm` GIN trigram on `title` (`gin_trgm_ops`) — fuzzy duplicate matching at insert time

**Monitoring tables:**
- `health_check_log` — Service health history with latency tracking
- `case_files` — Research source material for crime investigations

**Materialized views (refreshed daily via pg_cron):**
- `mv_video_profitability` — Revenue vs. cost per video
- `mv_channel_daily_summary` — Daily aggregates per channel

**Reporting views:**
- `v_pipeline_dashboard` — Real-time pipeline status with stage progress
- `v_cost_summary` — Spend by channel, provider, model, date
- `v_content_calendar` — Videos by status and publish date
- `v_channel_health` — Per-channel video counts and spend
- `v_daily_spend` — Daily spend breakdown by provider
- `v_service_uptime` — 24h/7d uptime percentages per service
- `v_active_alerts` — Services unhealthy in the last hour
- `v_production_readiness` — 8-point launch checklist

**Database functions:**
- `check_video_budget(video_id, cap)` — Returns spend, remaining, percentage, over-budget flag
- `get_video_pipeline_status(video_id)` — Returns per-stage completion with cost and duration
- `update_updated_at_column()` — Trigger function for auto-updating timestamps

**Scheduled jobs (pg_cron):**
- `cleanup-stale-jobs` — Every 15 min: fail pipeline jobs stuck processing > 30 min
- `archive-old-videos` — Weekly: archive published videos older than 30 days
- `purge-old-health-logs` — Daily: delete health logs older than 30 days
- `refresh-mv-profitability` — Daily 5 AM UTC: refresh video profitability view
- `refresh-mv-channel-summary` — Daily 5:05 AM UTC: refresh channel summary view

**Message queue:**
- `pipeline_jobs` queue via pgmq — worker polls for pending jobs

---

## 11. Codebase Structure

```
C:\Users\Varun\crimemill\
├── backend/
│   ├── src/
│   │   ├── api/              # FastAPI routes (health, videos, pipeline, channels)
│   │   ├── models/           # Pydantic models (channel, video, topic, costs, travel)
│   │   ├── services/         # Business logic
│   │   │   ├── script_generator.py          # CrimeMill script generation
│   │   │   ├── script_generators/
│   │   │   │   └── travel_safety_generator.py  # Street Level script generation
│   │   │   ├── prompts/
│   │   │   │   ├── crime_prompts.py         # Re-exports from script_generator.py
│   │   │   │   └── travel_prompts.py        # Street Level voice, titles, structure
│   │   │   ├── niche_router.py              # channel.niche → prompts + generator
│   │   │   ├── rhyo_agent_client.py         # Rhyo report parser (markdown → structured)
│   │   │   ├── image_generator.py           # fal.ai Flux Dev integration
│   │   │   ├── voiceover_generator.py       # Fish Audio S2 integration
│   │   │   ├── thumbnail_generator.py       # Pillow-based thumbnail compositing
│   │   │   ├── youtube_uploader.py          # YouTube Data API v3 integration
│   │   │   ├── topic_selector.py            # Topic discovery and scoring
│   │   │   └── ... (~30 more service files)
│   │   ├── pipeline/
│   │   │   └── handlers/
│   │   │       ├── script.py                # Crime script handler + niche dispatch
│   │   │       └── script_travel.py         # Travel script handler
│   │   ├── config.py          # Pydantic Settings with absolute .env path resolution
│   │   ├── cli.py             # 30+ CLI commands across 15 groups
│   │   └── main.py            # FastAPI app entrypoint
│   ├── scripts/
│   │   ├── smoke_test.py                    # 9-test API connectivity checker
│   │   ├── production_validation.py         # 8-test end-to-end validator
│   │   ├── generate_travel_sample.py        # Live Street Level script generator
│   │   └── test_media_services.py           # Fish Audio + fal.ai + Groq tester
│   ├── fixtures/
│   │   └── rhyo_reports/      # 7 Rhyo intelligence reports (markdown)
│   ├── tests/                 # 127 tests (pytest)
│   ├── .env                   # Local environment variables
│   ├── .env.example           # Template for .env
│   ├── Dockerfile             # Multi-stage Docker build
│   └── pyproject.toml         # Python dependencies
├── video/
│   ├── src/
│   │   ├── Root.tsx           # Remotion entry point
│   │   ├── CrimeDocumentary.tsx  # 2560×1440 crime composition
│   │   ├── CrimeShort.tsx     # 1080×1920 Shorts composition
│   │   └── components/        # Reusable Remotion components
│   ├── scripts/               # Lambda deploy scripts
│   └── package.json           # Node.js dependencies (Remotion)
├── railway.json               # Railway deployment config
├── docker-compose.yml         # Local development stack
└── docs/
    └── PRODUCTION_VALIDATION_RESULTS.md
```

**Test suite:** 127 passed, 25 skipped, 0 failed. mypy clean. ruff clean.

---

## 12. Environment Variables

All secrets stored in `backend/.env` locally and Railway service variables in production. The config uses Pydantic Settings with per-class `env_prefix` for nested grouping.

| Group | Prefix | Variables |
|---|---|---|
| Database | `SUPABASE_` | URL, ANON_KEY, SERVICE_ROLE_KEY, DB_URL |
| Scripts | `ANTHROPIC_` | API_KEY |
| Voiceover | `FISH_AUDIO_` | API_KEY |
| Images | `FAL_AI_` | API_KEY |
| Captions | `GROQ_` | API_KEY |
| Storage | `R2_` | ACCOUNT_ID, ACCESS_KEY_ID, SECRET_ACCESS_KEY, BUCKET_NAME, PUBLIC_URL, ENDPOINT_URL |
| Video render | `REMOTION_` | AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, LAMBDA_FUNCTION_NAME, SERVE_URL |
| YouTube | `YOUTUBE_` | CLIENT_ID, CLIENT_SECRET |
| App | (none) | ENVIRONMENT, LOG_LEVEL, MAX_CONCURRENT_JOBS, PIPELINE_POLL_INTERVAL_SECONDS |

**Critical config note:** Supabase DB_URL must use the **session pooler** URL (port 6543, host `aws-1-us-east-1.pooler.supabase.com`), not the direct connection. Direct connections use IPv6 which Railway cannot reach. The username format for the pooler is `postgres.qflkctgemkwochgkzqzj` (with project ref appended).

**Critical config note:** The `.env` file must NOT have inline comments (e.g., `KEY=value # comment`). Pydantic Settings reads the comment as part of the value. The `.env` must be UTF-8 encoded without BOM. Windows Notepad may add BOM or save as UTF-16 — use VS Code or PowerShell `Out-File -Encoding utf8` instead.

---

## 13. Deployment

**Railway backend:**
- URL: `https://travel-street-level-production.up.railway.app`
- Health check: `GET /health` returns JSON with db, r2, worker, queue status
- Auto-deploys from GitHub push to `master` branch
- Root directory: `/` (project root — Dockerfile references both `backend/` and `video/`)
- Builder: Railpack (detects Dockerfile automatically)
- Start command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT --workers 1`

**Remotion Lambda:**
- Function: `remotion-render-4-0-438-mem2048mb-disk2048mb-300sec`
- Serve URL: `https://remotionlambda-useast1-iczjvx1mx4.s3.us-east-1.amazonaws.com/sites/crimemill/index.html`
- Region: us-east-1
- Memory: 2048 MB
- Timeout: 300 seconds
- Compositions: `CrimeDocumentary` (2560×1440), `CrimeShort` (1080×1920)

**AWS IAM:**
- User: `remotion-lambda` (account 829910101905)
- Role: `remotion-lambda-role` (Lambda execution role with S3 + CloudWatch)
- Policy: `remotion-lambda-policy` (Lambda, S3, CloudWatch, IAM, STS with appropriate scoping)

**Cloudflare R2:**
- Bucket: `crimemill-assets`
- Account ID: `431bd6d80431311c88ac8302f4e7c0c3`
- Endpoint: `https://431bd6d80431311c88ac8302f4e7c0c3.r2.cloudflarestorage.com`

---

## 14. Current System Status

**Production readiness (8/8 checks pass):**

| Check | Status |
|---|---|
| Channels configured | ✅ 2 active channels |
| Topics backlog | ✅ 224 unused topics (after first automated discovery run on 2026-05-04; was 30 manual) |
| Discovery sources | ✅ 7 registered, 4 free sources verified (reddit, advisory, wikipedia, gdelt) |
| API providers seeded | ✅ 5 active providers |
| Brand settings | ✅ 2 brand configs |
| Voice settings | ✅ 2 voice configs |
| Generation settings | ✅ 2 generation configs |
| Queue active | ✅ 1 message queue |
| Cron jobs | ✅ 5 scheduled jobs |

**Service health:**

| Service | Status | Notes |
|---|---|---|
| Railway backend | ✅ Healthy | db connected, worker running, r2 reachable |
| Supabase DB (pooler) | ✅ Connected | Session pooler on port 6543 |
| Cloudflare R2 | ✅ Read/Write verified | Write + delete round-trip tested |
| Fish Audio TTS | ✅ Working | $0.008/voiceover verified |
| Groq Whisper | ✅ Working | Free tier, 21-word transcription in 1.2s |
| Anthropic | ❌ Credits exhausted | Needs $5+ top-up at console.anthropic.com (also blocks discovery scorer) |
| Discovery service | ✅ Live | 7 sources registered, 4 free (reddit / advisory / wikipedia / gdelt) verified producing candidates; cron off by default behind `ENABLE_DISCOVERY_CRON` |
| fal.ai | ❌ Credits exhausted | Needs $5+ top-up at fal.ai/dashboard/billing |
| Remotion Lambda | ⚠️ Needs real props | Function deployed, empty-props render times out at 300s |
| YouTube Upload | ❌ Blocked on partner | Needs YOUTUBE_CLIENT_ID + YOUTUBE_CLIENT_SECRET from partner |

---

## 15. Known Issues and Workarounds

| Issue | Severity | Workaround |
|---|---|---|
| Anthropic credits exhausted | 🔴 Blocks script generation | Top up $5+ at console.anthropic.com |
| fal.ai credits exhausted | 🔴 Blocks image generation | Top up $5+ at fal.ai/dashboard/billing |
| YouTube OAuth not configured | 🟡 Blocks uploads only | Partner delivering credentials; pre-produce videos in the meantime |
| Remotion empty-props timeout | 🟡 Test limitation | Will work with real scene data; not a production bug |
| Fish Audio voice IDs empty | 🟡 No voice cloning yet | Need 30s clean audio sample per channel to clone from |
| Street Level prompt doesn't force brand in description body | 🟢 By design | LLM correctly omits self-reference; brand appears in channel name and metadata |
| Supabase direct connection fails from Railway (IPv6) | 🟢 Solved | Use session pooler URL (port 6543) exclusively |
| Windows .env encoding issues | 🟢 Solved | Config uses absolute path resolution; always save .env as UTF-8 without BOM |

---

## 16. Open Items / TODO

**Immediate (blocked on money — $10 total):**
- [ ] Top up Anthropic credits ($5)
- [ ] Top up fal.ai credits ($5)
- [ ] Generate first 5 Street Level video scripts from Rhyo reports
- [ ] Generate images for those 5 videos
- [ ] Render test videos via Remotion Lambda with real scene data
- [ ] End-to-end pipeline test: topic → script → images → voiceover → video → R2

**Blocked on partner:**
- [ ] YouTube OAuth credentials (CLIENT_ID + CLIENT_SECRET) — partner is handling Google Cloud setup, OAuth verification, and API compliance audit
- [ ] YouTube channel creation (Brand Account + phone verification)
- [ ] AdSense account setup and tax configuration
- [ ] Amazon Associates affiliate tag
- [ ] Discord bot token + guild setup
- [ ] Buzzsprout podcast ID + API key

**Infrastructure (not blocking but should do):**
- [ ] Set up Healthchecks.io — sign up, create check, add HEALTHCHECKS_PING_URL to Railway env vars
- [ ] Set up Grafana Cloud — add Supabase PostgreSQL as data source
- [ ] Download fonts (Bebas Neue + Montserrat) via `scripts/download_fonts.sh`
- [ ] Music library — subscribe to Epidemic Sound ($10/mo), curate 20-30 tracks by mood
- [ ] Voice cloning — record 30s clean audio samples for CrimeMill narrator + Street Level host
- [ ] Wire NicheRouter into the orchestrator (currently dispatch is handler-level, not orchestrator-level)

**Content production:**
- [ ] Generate Rhyo reports for remaining 10 Street Level topics (Marrakech, Cape Town, Tokyo, etc.)
- [ ] Research and outline first 5 CrimeMill scripts (Wirecard, Madoff, 1MDB, Theranos, Enron)
- [ ] Design channel art + profile pictures for both channels
- [ ] Plan whirlpool launch strategy (3 simultaneous videos per channel with circular end-screen links)

**Discovery (built — running):**
- [x] Reddit scraper — built, verified 91 candidates / first run
- [x] Advisory poller (US State Dept + CDC + UK FCDO) — built; State Dept produces clean candidates, CDC + UK FCDO feeds upstream-broken (their XML, not ours)
- [x] GDELT integration — built, verified 20 candidates / first run
- [x] Wikipedia monitor — built, verified 77 candidates / first run (User-Agent fix in commit `ff5c090`)
- [x] Google Trends scanner — built (`pytrends`), not yet exercised
- [x] Competitor scanner — built; activates when `YOUTUBE_API_KEY` is set
- [x] CourtListener integration — built; activates when `COURTLISTENER_API_TOKEN` is set
- [x] Claude Haiku virality scorer — built; blocked on Anthropic credits, sources still produce raw heuristic scores
- [x] Discovery CLI (run-all / run-source / list-sources / show-backlog) — built
- [x] Discovery API (`POST /api/discovery/run`, `POST /api/discovery/run/{source}`, `GET /api/discovery/backlog`) — built
- [x] Optional 6h cron (`ENABLE_DISCOVERY_CRON=true`) — built, default off

**Future enhancements:**
- [ ] Automate Rhyo report generation (currently manual via safepath Claude Code session)
- [ ] Shorts generation pipeline (top-of-funnel to long-form)
- [ ] A/B thumbnail testing
- [ ] YouTube analytics feedback loop (auto-adjust topic selection based on view performance)
- [ ] Podcast distribution via Buzzsprout
- [ ] Newsletter via Resend
- [ ] Community management (Discord + Patreon integration)
- [ ] Multi-language support (localization_config table exists but not wired)

---

## 17. Potential Applications Beyond YouTube

The pipeline architecture is content-format-agnostic. The core capability (topic → research → script → media → assembly) can be repurposed for:

**Direct extensions:**
- **Podcast production** — Script → voiceover → intro/outro music → RSS upload. Buzzsprout integration is specced, table exists. Same scripts, different output format.
- **Short-form content** — Shorts composition exists in Remotion (`CrimeShort.tsx`, 1080×1920). Automated clip extraction from long-form videos for TikTok/Reels/Shorts.
- **Newsletter/blog** — Script → markdown → email via Resend. Same research, different distribution channel.
- **Social media clips** — Scene images + key quotes → Instagram carousels, Twitter threads, LinkedIn posts. Ayrshare integration specced.

**Adjacent applications:**
- **Corporate travel security briefings** — The Rhyo intelligence reports are already executive-briefing quality. Package as a B2B SaaS product: company inputs employee travel destinations, system generates per-destination safety briefs. Monetize per report or per seat.
- **Insurance risk assessment** — The Rhyo data (158M hex cells, 9-factor AHP, 740 country indicators) is directly applicable to travel insurance underwriting. Premium adjustment by destination risk score.
- **Real estate safety scoring** — Same hex-cell infrastructure applied to neighborhoods in a single city. Buyer/renter safety reports.
- **Event safety planning** — Venue-specific risk assessments for conference organizers, wedding planners, festival producers.

**Data products:**
- **Rhyo API** — The geographic risk-scoring database itself is a product. Sell API access to travel apps, booking platforms, corporate travel departments. Street Level YouTube channel serves as proof-of-concept and demand generation.
- **Safety data licensing** — License the scored H3 hex grid to mapping companies (Google Maps, Apple Maps, Waze) for safety layer overlays.
- **Advisory intelligence feed** — Real-time travel advisory changes packaged as a subscription feed for travel agencies and corporate travel managers.

**The strategic flywheel:**
```
Rhyo data → Street Level videos → organic YouTube audience
                                       ↓
                              audience trusts the data
                                       ↓
                              rhyo.com app signups
                                       ↓
                              user travel data improves Rhyo scoring
                                       ↓
                              better data → better videos → more audience
```

CrimeMill operates independently of this flywheel but cross-promotes to the same demographic (risk-aware, research-oriented viewers who travel internationally and care about financial security).

---

## 18. Key Technical Decisions and Rationale

| Decision | Rationale |
|---|---|
| **Claude Sonnet 4 for scripts, Haiku 4.5 for structured extraction** | Sonnet produces higher-quality creative writing; Haiku is 4x cheaper and sufficient for JSON extraction tasks. Combined approach keeps per-script cost under $0.10 while maintaining quality. |
| **Fish Audio S2 over ElevenLabs** | Fish Audio Plus is $11/mo with higher quality voice cloning at lower per-second cost ($0.015/s vs ~$0.03/s). S2 model supports emotion presets. |
| **fal.ai (Flux Dev) over Midjourney/DALL-E** | Flux Dev via fal.ai is $0.025/image with API access (no Discord bot needed). Photorealistic quality matches documentary aesthetic. fal.ai's queue system handles burst generation well. |
| **Remotion Lambda over FFmpeg scripting** | Remotion provides React-based composition with Ken Burns effects, crossfades, text overlays, and caption sync — all declarative. Lambda deployment means zero server management for rendering. |
| **Supabase over raw Postgres** | Built-in auth (future), real-time subscriptions (future), edge functions (future), pgmq extension, pg_cron, and a dashboard. Free tier covers early growth. |
| **Railway over AWS ECS/Fargate** | Simpler deployment (git push → deploy), built-in logging, usage-based pricing. No container orchestration overhead. Can migrate to ECS later if needed. |
| **Cloudflare R2 over AWS S3** | Zero egress fees. S3-compatible API means boto3 works unchanged. 10GB free tier. Pipeline uses R2 as working storage (7-day lifecycle), not permanent archive. |
| **pgmq over Redis/RabbitMQ** | Pipeline queue lives in the same Postgres database — no additional infrastructure. Transactional guarantees (job won't be lost if worker crashes). Simpler ops. |
| **Niche routing via channel.niche** | One codebase, multiple channels. Adding a new niche (e.g., "business_documentary") requires only: new prompts module, new topic sources, update CHECK constraint. No pipeline code changes. |
| **Street Level brand separation from Rhyo** | Organic YouTube growth requires independent brand identity. Rhyo credited as data partner (sponsor model), not co-owner. Allows pivot if Rhyo direction changes. |

---

## 19. Useful Commands

```bash
# Local development
cd C:\Users\Varun\crimemill\backend
python scripts/smoke_test.py              # Test all API connections (9 tests)
python scripts/production_validation.py   # Full 8-test validation suite
python scripts/generate_travel_sample.py  # Generate a Street Level script
python scripts/test_media_services.py     # Test Fish Audio + fal.ai + Groq

# Railway
railway login                             # Authenticate CLI
railway up                                # Deploy from local (alternative to git push)
railway logs                              # Stream live logs

# Remotion Lambda
cd C:\Users\Varun\crimemill\video
$env:REMOTION_AWS_ACCESS_KEY_ID = "..."
$env:REMOTION_AWS_SECRET_ACCESS_KEY = "..."
npx remotion lambda functions deploy --memory=2048 --timeout=300 --region=us-east-1
npx remotion lambda sites create src/index.ts --region=us-east-1 --site-name=crimemill
npx remotion lambda render <serve-url> CrimeDocumentary --props=<json> --frames=0-60

# Database
# Use Supabase SQL Editor: https://supabase.com/dashboard/project/qflkctgemkwochgkzqzj/sql/new
SELECT * FROM v_production_readiness;     # Launch checklist
SELECT * FROM v_pipeline_dashboard;       # Active pipeline status
SELECT * FROM v_cost_summary;             # Spend tracking
SELECT * FROM v_channel_health;           # Per-channel stats
SELECT * FROM v_daily_spend;              # Daily cost breakdown
SELECT * FROM check_video_budget('video-uuid-here');  # Budget check

# Tests
cd C:\Users\Varun\crimemill\backend
pytest tests/ -v -m "not integration and not requires_db"
mypy src/ --ignore-missing-imports
ruff check src/ tests/ scripts/

# Discovery (topic backlog)
python -m src.cli discover list-sources                  # show all 7 registered sources
python -m src.cli discover run-source reddit -v          # run one source verbosely
python -m src.cli discover run-source advisory -v        # State Dept + CDC + UK FCDO
python -m src.cli discover run-source wikipedia -v       # categories + ITN + recent deaths
python -m src.cli discover run-source gdelt -v           # GDELT 2.0 news monitoring
python -m src.cli discover run-all --score               # all sources + Claude Haiku scorer
python -m src.cli discover show-backlog --limit 30       # top unassigned topics
```

---

## 20. For Future Claude Sessions

Quick orientation for whatever Claude session picks this up next:

1. **Two channels share the codebase**: `CrimeMill` (financial_crime niche) and `Street Level` (travel_safety niche). Niche dispatch happens in `src/pipeline/handlers/script.py` based on `channels.niche`.
2. **Settings is nested**, not flat. `from src.config import get_settings` → `s.anthropic.api_key`, `s.database.url`, `s.fal.api_key`, `s.fish_audio.api_key`, `s.groq.api_key`, `s.youtube.api_key`, `s.court_listener.api_token`, etc. The discovery code wraps each access in `getattr(getattr(config, "section", None), "field", None)` because the orchestrator is callable from places that may pass a non-Settings shim.
3. **Supabase is reached two ways**: (a) the FastAPI backend uses **`psycopg` against the session pooler** (`SUPABASE_DB_URL` = `aws-1-us-east-1.pooler.supabase.com:6543`); (b) the discovery code uses the **`supabase` Python client** for its REST/PostgREST surface. Both work; don't mix patterns inside one call site.
4. **Windows quirks**: psycopg's async API requires `WindowsSelectorEventLoopPolicy`. Subprocesses (Remotion CLI, etc.) only work on `ProactorEventLoop`. If you need both in one process, call `subprocess.run` via `asyncio.to_thread` so the SelectorEventLoop policy applies but subprocess work happens on a thread.
5. **Anthropic credit balance is the first failure mode** for almost every model-using path (script generation, descriptions, scorer). Check `console.anthropic.com/settings/billing` before assuming a code bug.
6. **fal.ai credits are the second failure mode** — same diagnosis pattern. Image generation 403 = top up at `fal.ai/dashboard/billing`.
7. **The Lambda render times out at 300 s** with empty `--props={}` because the React composition expects `scenes`, `audioUrl`, `captionWords`. Pass real props (or seed defaults) when you exercise it.
8. **Don't put real values in `.env.example`** — the file is committed; real secrets belong in `.env` (gitignored). GitHub secret-scanning will block pushes that leak `AKIA...` keys.
9. **Discovery service is built and deployed** (commits `c265623` + `ff5c090`). 7 sources, CLI + API + optional cron. The 4 free sources (reddit, advisory, wikipedia, gdelt) work right now and produced 194 net candidates on the 2026-05-04 inaugural run. The Claude Haiku scorer is wired but blocked on credits — set `ANTHROPIC_API_KEY` + top up to enable. Optional 6 h cron via `ENABLE_DISCOVERY_CRON=true` (Railway env var).
