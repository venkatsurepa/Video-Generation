#!/usr/bin/env bash
# ============================================================
# Railway Setup Guide for CrimeMill
# ============================================================
# This script documents the Railway deployment steps.
# Run these commands manually via Railway dashboard or CLI.
#
# Railway is used for the FastAPI backend ONLY — orchestration,
# API, and pipeline worker. It does NOT run:
#   - Video rendering (Remotion Lambda on AWS)
#   - Image generation (fal.ai API)
#   - AI inference (Claude, Groq, Fish Audio APIs)
#
# Cost: ~$5-10/month for the orchestration backend
#        ($20/vCPU/month, but we use a fraction of a vCPU)
# ============================================================

set -euo pipefail

echo "=== CrimeMill Railway Setup ==="
echo ""
echo "This script is a documented guide. Run each section manually."
echo ""

# -------------------------------------------------------
# 1. Install Railway CLI
# -------------------------------------------------------
echo "--- Step 1: Install Railway CLI ---"
echo "  npm install -g @railway/cli"
echo ""

# -------------------------------------------------------
# 2. Login and create project
# -------------------------------------------------------
echo "--- Step 2: Login and create project ---"
echo "  railway login"
echo "  railway init --name crimemill"
echo ""

# -------------------------------------------------------
# 3. Database — NOT needed
# -------------------------------------------------------
echo "--- Step 3: Database ---"
echo "  We do NOT provision a Railway database."
echo "  All data lives in Supabase (external PostgreSQL)."
echo "  Railway connects to Supabase via SUPABASE_DB_URL."
echo ""

# -------------------------------------------------------
# 4. Set environment variables
# -------------------------------------------------------
echo "--- Step 4: Set environment variables ---"
echo "  Copy values from .env.example and fill in real credentials."
echo ""
echo "  # Database (Supabase)"
echo "  railway variables set SUPABASE_URL=https://your-project.supabase.co"
echo "  railway variables set SUPABASE_ANON_KEY=eyJ..."
echo "  railway variables set SUPABASE_SERVICE_ROLE_KEY=eyJ..."
echo "  railway variables set SUPABASE_DB_URL=postgresql://..."
echo ""
echo "  # AI Services"
echo "  railway variables set ANTHROPIC_API_KEY=sk-ant-..."
echo "  railway variables set FISH_AUDIO_API_KEY=fa-..."
echo "  railway variables set FAL_AI_API_KEY=fal-..."
echo "  railway variables set GROQ_API_KEY=gsk_..."
echo ""
echo "  # Storage (Cloudflare R2)"
echo "  railway variables set R2_ACCOUNT_ID=..."
echo "  railway variables set R2_ACCESS_KEY_ID=..."
echo "  railway variables set R2_SECRET_ACCESS_KEY=..."
echo "  railway variables set R2_BUCKET_NAME=crimemill-assets"
echo "  railway variables set R2_PUBLIC_URL=https://assets.your-domain.com"
echo ""
echo "  # Remotion Lambda"
echo "  railway variables set REMOTION_AWS_ACCESS_KEY_ID=..."
echo "  railway variables set REMOTION_AWS_SECRET_ACCESS_KEY=..."
echo "  railway variables set REMOTION_AWS_REGION=us-east-1"
echo "  railway variables set REMOTION_LAMBDA_FUNCTION_NAME=..."
echo "  railway variables set REMOTION_SERVE_URL=..."
echo ""
echo "  # YouTube"
echo "  railway variables set YOUTUBE_CLIENT_ID=..."
echo "  railway variables set YOUTUBE_CLIENT_SECRET=..."
echo ""
echo "  # Monitoring"
echo "  railway variables set HEALTHCHECKS_PING_URL=https://hc-ping.com/your-uuid"
echo ""
echo "  # App Config"
echo "  railway variables set ENVIRONMENT=production"
echo "  railway variables set LOG_LEVEL=INFO"
echo "  railway variables set MAX_CONCURRENT_JOBS=3"
echo "  railway variables set PIPELINE_POLL_INTERVAL_SECONDS=5"
echo ""

# -------------------------------------------------------
# 5. Deploy
# -------------------------------------------------------
echo "--- Step 5: Deploy ---"
echo "  railway up"
echo ""
echo "  Or connect GitHub repo for auto-deploy on push:"
echo "  Railway Dashboard → Service → Settings → Source → Connect Repo"
echo ""

# -------------------------------------------------------
# 6. Custom domain (optional)
# -------------------------------------------------------
echo "--- Step 6: Custom domain (optional) ---"
echo "  railway domain"
echo "  # Then add CNAME in your DNS provider"
echo ""

# -------------------------------------------------------
# Important notes
# -------------------------------------------------------
echo "=== IMPORTANT NOTES ==="
echo ""
echo "1. Railway is for orchestration ONLY (~\$5-10/month)"
echo "   - FastAPI REST API"
echo "   - Pipeline worker (background job processor)"
echo "   - Healthcheck endpoint"
echo ""
echo "2. Do NOT run these on Railway:"
echo "   - Video rendering → Remotion Lambda (AWS)"
echo "   - Image generation → fal.ai (external API)"
echo "   - AI inference → Claude, Groq, Fish Audio (external APIs)"
echo ""
echo "3. Railway ephemeral disk (100GB):"
echo "   - Filesystem wipes on every deploy"
echo "   - All transient files go to /tmp/crimemill/"
echo "   - Final artifacts upload to R2 immediately"
echo "   - Disable auto-deploy if mid-pipeline to prevent wipes"
echo ""
echo "4. Railway limits:"
echo "   - 15-minute HTTP request timeout (not an issue for API)"
echo "   - Background worker runs indefinitely in the same container"
echo "   - Memory: watch for OOM if processing many videos concurrently"
echo "   - Set MAX_CONCURRENT_JOBS=1 initially, increase carefully"
echo ""
echo "5. Monitoring:"
echo "   - Health endpoint: GET /health"
echo "   - Railway dashboard shows logs, metrics, deploys"
echo "   - Set up Healthchecks.io for uptime monitoring"
echo "   - Use Grafana Cloud free tier for metrics dashboard"
