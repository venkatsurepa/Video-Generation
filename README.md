# CrimeMill

Automated YouTube crime documentary pipeline. Produces cinematic videos from topic selection through YouTube upload using AI services for scripting, voiceover, imagery, and assembly.

## Architecture

- **Backend**: FastAPI + psycopg3 async, Postgres job queue
- **Video**: Remotion compositions for programmatic video rendering
- **Database**: Supabase (PostgreSQL) with migrations via SQL Editor
- **Storage**: Cloudflare R2 for media assets
- **CI**: GitHub Actions (lint, type-check, test)

## Quick Start

```bash
# Install backend dependencies
make install-dev

# Copy and configure environment
cp .env.example .env

# Run development server
make dev

# Run linting and tests
make lint
make test
```

## Pipeline Stages

1. Script Generation (Claude)
2. Voiceover Generation (Fish Audio)
3. Image Generation (fal.ai)
4. Music Selection
5. Audio Processing (voice + music mix)
6. Image Processing (Ken Burns effects)
7. Caption Generation (Groq whisper)
8. Video Assembly (Remotion)
9. Thumbnail Generation (fal.ai)
10. YouTube Upload

See [docs/PIPELINE.md](docs/PIPELINE.md) for details.
