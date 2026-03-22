# Monitoring

## Overview

CrimeMill uses two monitoring systems:

- **Healthchecks.io** — heartbeat monitoring for pipeline job execution
- **Grafana Cloud** — dashboards and alerts from PostgreSQL + structured logs

## Healthchecks.io Setup

1. Create a free account at [healthchecks.io](https://healthchecks.io)
2. Create a new check (or one per pipeline stage for granular monitoring)
3. Copy the ping URL (e.g., `https://hc-ping.com/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
4. Set in your `.env`:

```
HEALTHCHECKS_PING_URL=https://hc-ping.com/your-uuid-here
```

### How it works

The `HealthMonitor` service (injected into the pipeline worker) sends pings at three points:

| Endpoint | When | Purpose |
|----------|------|---------|
| `GET /start` | Job claimed from queue | Detect jobs that started but never finished |
| `GET /` | Job completed successfully | Confirm healthy pipeline operation |
| `POST /fail` | Job failed or dead-lettered | Trigger failure alerts (error in body) |

Pings are fire-and-forget — a monitoring failure never blocks the pipeline.

### Recommended check settings

- **Period**: 15 minutes (expect at least one job every 15 min during active processing)
- **Grace**: 30 minutes (allow for long-running stages like video assembly)
- **Notifications**: Email + Slack/Discord webhook

## Grafana Cloud Setup

1. Create a free Grafana Cloud account at [grafana.com](https://grafana.com)
2. Add a **PostgreSQL** data source pointing to your Supabase database:
   - Host: `db.glbimgqwcamqldcyvovv.supabase.co:5432`
   - Database: `postgres`
   - User: `postgres`
   - Password: your Supabase DB password
   - SSL Mode: require
3. Import dashboard queries from `backend/src/monitoring/grafana_queries.sql`

### Dashboard Panels

| Panel | Query | Refresh |
|-------|-------|---------|
| Videos produced per day | `SELECT DATE(published_at)...` | 5 min |
| Pipeline success rate | Stage-level completed vs dead_letter | 5 min |
| Average cost per video | Cost grouped by day | 15 min |
| Cost breakdown by stage | Costs grouped by stage | 15 min |
| Queue depth | Current pending/in_progress/dead_letter | 30 sec |
| Per-video cost summary | Last 50 published videos | 5 min |
| Channel performance | Videos per channel | 15 min |

### Alerts

Configure these Grafana alerts:

1. **Dead letter jobs**: Fire when `dead_letter` count > 0 in last 24h
2. **No output**: Fire when published video count = 0 in last 24h
3. **Cost spike**: Fire when a video's total cost exceeds 2× the running average

### Structured Log Metrics

The pipeline worker emits structured log lines with `event=metric`:

```json
{"event": "metric", "metric_name": "job_duration_seconds.script_generation", "value": 12.5}
{"event": "metric", "metric_name": "job_cost_usd.image_generation", "value": 0.16}
{"event": "metric", "metric_name": "queue_depth_pending", "value": 3.0}
```

If using Grafana Cloud Logs (Loki), you can query these with:

```logql
{app="crimemill"} |= "metric" | json | metric_name = "job_duration_seconds.script_generation"
```
