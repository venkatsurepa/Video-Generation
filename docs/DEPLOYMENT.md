# Deployment Guide

Complete deployment guide for the CrimeMill automated crime documentary pipeline.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  Railway ($5-10/mo)                                              │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  FastAPI Backend (API + Pipeline Worker)                  │   │
│  │  - REST API on port $PORT                                 │   │
│  │  - Background worker polls pipeline_jobs table            │   │
│  │  - Orchestrates all external service calls                │   │
│  └──────────────────────────┬────────────────────────────────┘   │
└─────────────────────────────┼────────────────────────────────────┘
                              │
          ┌───────────────────┼──────────────────────┐
          │                   │                      │
          ▼                   ▼                      ▼
┌─────────────────┐  ┌───────────────┐  ┌──────────────────────┐
│  Supabase       │  │  Cloudflare   │  │  AWS Lambda          │
│  (PostgreSQL)   │  │  R2 Storage   │  │  (Remotion Render)   │
│  Free tier      │  │  Free egress  │  │  ~$0.11/video        │
└─────────────────┘  └───────────────┘  └──────────────────────┘
```

External APIs (pay-per-use): Claude, Fish Audio, fal.ai, Groq, YouTube.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Supabase Setup](#2-supabase-setup)
3. [Cloudflare R2 Setup](#3-cloudflare-r2-setup)
4. [AWS Setup for Remotion Lambda](#4-aws-setup-for-remotion-lambda)
5. [Remotion Lambda Deployment](#5-remotion-lambda-deployment)
6. [Railway Backend Deployment](#6-railway-backend-deployment)
7. [YouTube API Setup](#7-youtube-api-setup)
8. [Environment Variable Checklist](#8-environment-variable-checklist)
9. [Post-Deployment Verification](#9-post-deployment-verification)
10. [Monitoring Setup](#10-monitoring-setup)
11. [Cost Summary](#11-cost-summary)

---

## 1. Prerequisites

- **Node.js** 18+ (for Remotion CLI)
- **Python** 3.12+ (for local development)
- **Docker** (for building/testing container locally)
- **AWS CLI** configured (`aws configure`)
- **Railway CLI** installed (`npm install -g @railway/cli`)
- **Git** repository pushed to GitHub

---

## 2. Supabase Setup

### 2.1 Create Project

1. Go to [supabase.com](https://supabase.com) and create a new project
2. Choose a region close to your Railway deployment (e.g., `us-east-1`)
3. Set a strong database password — save it securely
4. Wait for project initialization

### 2.2 Run Database Migration

Open the SQL Editor in the Supabase dashboard and run the migration:

```sql
-- Paste the contents of supabase/migrations/001_initial_schema.sql
```

This creates all tables, indexes, triggers, materialized views, pg_cron jobs,
and row-level security policies.

### 2.3 Configure Storage Buckets

In the Supabase Dashboard → Storage, create these buckets:

| Bucket       | Access  | Cache Control   | Purpose                  |
|-------------|---------|-----------------|--------------------------|
| `thumbnails` | Public  | `31536000` (1yr) | YouTube thumbnails       |
| `images`     | Private | `86400` (1 day)  | Scene images             |
| `audio`      | Private | `86400` (1 day)  | Voiceovers, music, mixes |
| `videos`     | Private | `86400` (1 day)  | Assembled MP4 files      |

Path pattern: `{channel_id}/{video_id}/{filename}`

### 2.4 Collect Connection Details

From Supabase Dashboard → Settings → API:

| Variable                  | Where to find                          |
|--------------------------|----------------------------------------|
| `SUPABASE_URL`           | Project URL                            |
| `SUPABASE_ANON_KEY`      | API Settings → anon/public key         |
| `SUPABASE_SERVICE_ROLE_KEY` | API Settings → service_role key     |
| `SUPABASE_DB_URL`        | Database → Connection string (Session mode, port 5432) |

---

## 3. Cloudflare R2 Setup

### 3.1 Create R2 Bucket

1. Go to Cloudflare Dashboard → R2
2. Create bucket: `crimemill-assets`
3. Region: Automatic (or choose closest to Railway)

### 3.2 Create API Token

Cloudflare Dashboard → R2 → Manage R2 API Tokens:

1. Create token with **Object Read & Write** permission
2. Scope to the `crimemill-assets` bucket
3. Save the Access Key ID and Secret Access Key

### 3.3 Configure Custom Domain (Optional)

1. Add a custom domain (e.g., `assets.your-domain.com`)
2. Enable public access for the `thumbnails/` prefix only
3. All other paths use presigned URLs

### 3.4 Lifecycle Policy

Configure automatic cleanup for temporary render artifacts:

```json
{
  "rules": [
    {
      "id": "cleanup-temp-renders",
      "prefix": "tmp/",
      "expiration": { "days": 1 }
    }
  ]
}
```

### 3.5 Collect R2 Details

| Variable              | Where to find                          |
|----------------------|----------------------------------------|
| `R2_ACCOUNT_ID`     | Cloudflare Dashboard → Account ID      |
| `R2_ACCESS_KEY_ID`  | R2 API Token                           |
| `R2_SECRET_ACCESS_KEY` | R2 API Token                        |
| `R2_BUCKET_NAME`    | `crimemill-assets`                     |
| `R2_PUBLIC_URL`     | Custom domain or R2 public URL         |

---

## 4. AWS Setup for Remotion Lambda

### 4.1 Create IAM User

1. AWS Console → IAM → Users → Create User
2. Name: `crimemill-remotion`
3. Attach the policy from `video/remotion-lambda-policy.json`:

```bash
aws iam create-policy \
  --policy-name RemotionLambdaPolicy \
  --policy-document file://video/remotion-lambda-policy.json

aws iam create-user --user-name crimemill-remotion

aws iam attach-user-policy \
  --user-name crimemill-remotion \
  --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/RemotionLambdaPolicy
```

4. Create access keys:

```bash
aws iam create-access-key --user-name crimemill-remotion
```

Save the `AccessKeyId` and `SecretAccessKey`.

### 4.2 Validate Permissions

```bash
npx remotion lambda policies validate --region us-east-1
```

### 4.3 Request Lambda Concurrency Increase (If Needed)

Default Lambda concurrency is 1000. For parallel chunk rendering,
Remotion may use 50-200 concurrent invocations per video.
Check your account limits:

```bash
aws lambda get-account-settings --region us-east-1
```

---

## 5. Remotion Lambda Deployment

### 5.1 Deploy

```bash
cd video

# Set AWS credentials
export REMOTION_AWS_ACCESS_KEY_ID=<your-key>
export REMOTION_AWS_SECRET_ACCESS_KEY=<your-secret>
export REMOTION_AWS_REGION=us-east-1

# Deploy Lambda function + site bundle
bash scripts/deploy-lambda.sh
```

This deploys:
- Lambda function: 2048 MB RAM, 2048 MB disk, 5-min timeout
- S3 site: Bundled Remotion project for the Lambda to serve

### 5.2 Note the Output

The deploy script prints:
- **Function name**: e.g., `remotion-render-2024-01-15-abc123`
- **Serve URL**: e.g., `https://remotionlambda-us-east-1-abc123.s3.us-east-1.amazonaws.com/sites/crimemill-video/index.html`

Save these as `REMOTION_LAMBDA_FUNCTION_NAME` and `REMOTION_SERVE_URL`.

### 5.3 Test Render

```bash
export REMOTION_LAMBDA_FUNCTION_NAME=<function-name>
export REMOTION_SERVE_URL=<serve-url>

bash scripts/render-test.sh
```

This renders a 10-second test video with 3 placeholder scenes.
Expected completion time: ~15-20 seconds for 300 frames.

### 5.4 Verify Deployment

```bash
# List deployed functions
npx remotion lambda functions ls --region us-east-1

# List deployed sites
npx remotion lambda sites ls --region us-east-1
```

---

## 6. Railway Backend Deployment

### 6.1 Initialize Project

```bash
railway login
railway init --name crimemill
```

### 6.2 Configure Service

In Railway Dashboard → Service → Settings:

| Setting            | Value                           |
|-------------------|---------------------------------|
| Builder           | Dockerfile                      |
| Dockerfile Path   | `backend/Dockerfile`            |
| Root Directory    | `/`  (repo root)                |
| Start Command     | `uvicorn src.main:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health Check Path | `/health`                       |
| Restart Policy    | On Failure (max 3 retries)      |

Or use the `backend/railway.toml` which configures this automatically.

### 6.3 Set Environment Variables

Set every variable from the [Environment Variable Checklist](#8-environment-variable-checklist).

Via CLI:
```bash
railway variables set ENVIRONMENT=production
railway variables set SUPABASE_URL=https://your-project.supabase.co
# ... (all variables)
```

Or via Railway Dashboard → Variables tab.

### 6.4 Deploy

```bash
# Push-based deploy (connects to GitHub)
# Railway Dashboard → Service → Settings → Source → Connect Repo

# Or manual deploy
railway up
```

### 6.5 Verify Deployment

```bash
# Check health endpoint
curl https://your-app.up.railway.app/health

# Expected response:
# {"status":"healthy","environment":"production","version":"0.1.0","db":"connected"}
```

### 6.6 Important Railway Notes

- **Cost**: ~$5-10/month for a single service
- **Ephemeral disk**: 100 GB, wipes on every deploy
- **HTTP timeout**: 15 minutes (API requests only)
- **Background worker**: Runs indefinitely in the same container via asyncio task
- **No GPU**: Video rendering and image generation run on external services
- **Disable auto-deploy** during active pipeline runs to prevent filesystem wipes

---

## 7. YouTube API Setup

### 7.1 Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project: `crimemill`
3. Enable the **YouTube Data API v3**

### 7.2 OAuth Consent Screen

1. APIs & Services → OAuth consent screen
2. Choose **External** user type
3. Fill in:
   - App name: `CrimeMill`
   - User support email
   - Developer contact email
4. Add scopes:
   - `youtube.upload`
   - `youtube.readonly`
   - `youtube.force-ssl`
5. Add test users (your YouTube account email)

### 7.3 Create OAuth Credentials

1. APIs & Services → Credentials → Create Credentials → OAuth client ID
2. Application type: **Web application**
3. Authorized redirect URIs: `http://localhost:8000/api/v1/youtube/callback`
4. Download the client ID and secret

### 7.4 YouTube API Compliance

Before going to production (publishing videos publicly):

1. **Verify OAuth consent screen** — submit for Google review
2. **API compliance audit** — review YouTube API Terms of Service
3. **Quota increase** — default is 10,000 units/day
   - Each video upload costs 1,600 units
   - Request increase via Google Cloud Console → Quotas
4. **Brand verification** — may be required for automated uploads

Save `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET`.

---

## 8. Environment Variable Checklist

Every environment variable needed for production deployment:

### Database (Supabase)

| Variable | Source | Required |
|----------|--------|----------|
| `SUPABASE_URL` | Supabase Dashboard → Settings → API | Yes |
| `SUPABASE_ANON_KEY` | Supabase Dashboard → Settings → API | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Dashboard → Settings → API | Yes |
| `SUPABASE_DB_URL` | Supabase Dashboard → Database → Connection String (Session mode) | Yes |

### AI Services

| Variable | Source | Required |
|----------|--------|----------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys | Yes |
| `FISH_AUDIO_API_KEY` | [fish.audio](https://fish.audio) → Dashboard → API Keys | Yes |
| `FAL_AI_API_KEY` | [fal.ai](https://fal.ai) → Dashboard → API Keys | Yes |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) → API Keys | Yes |

### Storage (Cloudflare R2)

| Variable | Source | Required |
|----------|--------|----------|
| `R2_ACCOUNT_ID` | Cloudflare Dashboard → Account ID | Yes |
| `R2_ACCESS_KEY_ID` | R2 API Token | Yes |
| `R2_SECRET_ACCESS_KEY` | R2 API Token | Yes |
| `R2_BUCKET_NAME` | `crimemill-assets` (or your bucket name) | Yes |
| `R2_PUBLIC_URL` | Custom domain or R2 public URL | Yes |

### Remotion Lambda (Video Rendering)

| Variable | Source | Required |
|----------|--------|----------|
| `REMOTION_AWS_ACCESS_KEY_ID` | AWS IAM → crimemill-remotion user | Yes |
| `REMOTION_AWS_SECRET_ACCESS_KEY` | AWS IAM → crimemill-remotion user | Yes |
| `REMOTION_AWS_REGION` | `us-east-1` (or your chosen region) | Yes |
| `REMOTION_LAMBDA_FUNCTION_NAME` | Output of `deploy-lambda.sh` | Yes |
| `REMOTION_SERVE_URL` | Output of `deploy-lambda.sh` | Yes |

### YouTube

| Variable | Source | Required |
|----------|--------|----------|
| `YOUTUBE_CLIENT_ID` | Google Cloud Console → Credentials | Yes |
| `YOUTUBE_CLIENT_SECRET` | Google Cloud Console → Credentials | Yes |

### Monitoring

| Variable | Source | Required |
|----------|--------|----------|
| `HEALTHCHECKS_PING_URL` | [Healthchecks.io](https://healthchecks.io) → New Check | No |

### Application

| Variable | Value | Required |
|----------|-------|----------|
| `ENVIRONMENT` | `production` | Yes |
| `LOG_LEVEL` | `INFO` | Yes |
| `MAX_CONCURRENT_JOBS` | `1` (start conservative) | Yes |
| `PIPELINE_POLL_INTERVAL_SECONDS` | `5` | Yes |

---

## 9. Post-Deployment Verification

Run these checks after deploying each component:

### 9.1 Database

```bash
# Verify tables exist (via Supabase SQL Editor)
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;

# Expected: 15+ tables including channels, videos, pipeline_jobs, etc.
```

### 9.2 Backend API

```bash
# Health check
curl -s https://your-app.up.railway.app/health | jq .
# Expected: {"status":"healthy","db":"connected",...}

# API docs (dev only)
curl -s https://your-app.up.railway.app/docs
```

### 9.3 Remotion Lambda

```bash
# List functions
npx remotion lambda functions ls --region us-east-1

# Test render
cd video && bash scripts/render-test.sh
```

### 9.4 R2 Storage

```bash
# Verify bucket exists (via AWS CLI with R2 endpoint)
aws s3 ls --endpoint-url https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

### 9.5 End-to-End Pipeline Test

```bash
# Trigger a test video pipeline
curl -X POST https://your-app.up.railway.app/api/v1/videos \
  -H "Content-Type: application/json" \
  -d '{"channel_id":"<your-channel-id>","topic":"Test: The Story of a Pipeline Test"}'

# Check pipeline status
curl https://your-app.up.railway.app/api/v1/pipeline/status/<video_id>
```

---

## 10. Monitoring Setup

### 10.1 Healthchecks.io (Uptime Monitoring)

1. Create account at [healthchecks.io](https://healthchecks.io)
2. Create a new check:
   - Name: `CrimeMill API`
   - Period: 5 minutes
   - Grace: 10 minutes
3. Copy the ping URL → set as `HEALTHCHECKS_PING_URL`
4. The pipeline worker pings this URL on each successful poll cycle

### 10.2 Railway Dashboard

Railway provides built-in monitoring:
- **Logs**: Real-time structured log viewer
- **Metrics**: CPU, memory, network usage
- **Deploys**: Deploy history with rollback capability

### 10.3 Grafana Cloud (Optional)

For a metrics dashboard:

1. Sign up at [grafana.com](https://grafana.com) (free tier: 10k metrics)
2. Create a Prometheus data source pointing to your metrics endpoint
3. Import or build dashboards for:
   - Pipeline throughput (videos/hour)
   - Stage latency (p50, p95, p99)
   - Error rate by stage
   - Cost per video
   - Queue depth (pending jobs)

### 10.4 Alerts

Set up alerts for:
- Health check failures (Healthchecks.io → Slack/email)
- Pipeline errors > 3 in 1 hour
- Render failures (stuck in "rendering" > 10 minutes)
- Cost anomalies (daily spend > $5)

---

## 11. Cost Summary

Estimated per-video costs for a 10-minute documentary:

| Component | Service | Cost |
|-----------|---------|------|
| Script generation | Claude Sonnet + Haiku | ~$0.08 |
| Image generation | fal.ai (3 hero + 12 standard) | ~$0.16 |
| Image processing | Pillow (on Railway) | ~$0.00 |
| Voiceover | Fish Audio | ~$0.07 |
| Audio processing | FFmpeg (on Railway) | ~$0.00 |
| Caption generation | Groq Whisper | ~$0.01 |
| Video assembly | Remotion Lambda | ~$0.11 |
| Thumbnail | fal.ai | ~$0.05 |
| YouTube upload | YouTube API | Free |
| **Storage** | Cloudflare R2 | ~$0.01 |
| **Total per video** | | **~$0.49** |

Infrastructure (monthly):
- Railway backend: ~$5-10/month
- Supabase: Free tier (500 MB database)
- Cloudflare R2: Free tier (10 GB storage, no egress fees)
- AWS Lambda: Pay-per-use only (no idle cost)

---

## Build Sequence

Follow this order for a clean first deployment:

```
1. Supabase     — Create project, run migration, configure buckets
2. Cloudflare R2 — Create bucket, API token, lifecycle policy
3. AWS IAM       — Create user, attach Remotion Lambda policy
4. Remotion      — Deploy Lambda function + site bundle
5. Railway       — Deploy backend, set all env vars
6. YouTube       — Create OAuth credentials (can be last)
7. Verify        — Run post-deployment checks
8. Test          — Trigger end-to-end pipeline test
```
