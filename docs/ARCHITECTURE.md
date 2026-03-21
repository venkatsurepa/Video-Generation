# Architecture

## System Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  FastAPI     │────▶│  PostgreSQL  │────▶│  Pipeline        │
│  REST API    │     │  Job Queue   │     │  Worker          │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                           ┌───────────────────────┼───────────────────────┐
                           │              │        │        │              │
                      ┌────▼───┐   ┌──────▼──┐ ┌──▼───┐ ┌──▼──┐   ┌──────▼────┐
                      │ Claude │   │Fish Audio│ │fal.ai│ │ Groq│   │  Remotion  │
                      │ Script │   │   TTS    │ │ Image│ │Whisp│   │  Renderer  │
                      └────────┘   └─────────┘ └──────┘ └─────┘   └─────┬─────┘
                                                                          │
                                                                   ┌──────▼──────┐
                                                                   │Cloudflare R2│
                                                                   │   Storage   │
                                                                   └──────┬──────┘
                                                                          │
                                                                   ┌──────▼──────┐
                                                                   │   YouTube    │
                                                                   │   Upload     │
                                                                   └─────────────┘
```

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| API Framework | FastAPI | Async-native, auto OpenAPI docs, Pydantic integration |
| Database | Supabase (PostgreSQL) | Managed Postgres with auth, realtime, and edge functions |
| Job Queue | Postgres FOR UPDATE SKIP LOCKED | No extra infrastructure, transactional consistency |
| Scripting AI | Claude (Anthropic) | Best long-form narrative generation |
| TTS | Fish Audio | High-quality voice cloning, fast turnaround |
| Image Gen | fal.ai | Fast inference, good quality, cost-effective |
| Transcription | Groq Whisper | Fastest whisper inference for word-level timestamps |
| Video Render | Remotion | Programmatic React-based video composition |
| Object Storage | Cloudflare R2 | S3-compatible, no egress fees |
| CI | GitHub Actions | Native to GitHub, free for public repos |

## Pipeline DAG

```
script_generation
├── voiceover_generation
│   ├── audio_processing (+ music_selection)
│   └── caption_generation
├── image_generation
│   └── image_processing
├── music_selection
│   └── audio_processing (+ voiceover_generation)
└── thumbnail_generation

audio_processing ──┐
image_processing ──┼── video_assembly
caption_generation─┘        │
                            ├── youtube_upload
thumbnail_generation────────┘
```
