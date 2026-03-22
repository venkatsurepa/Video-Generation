# API Reference

Base URL: `http://localhost:8000` (development) or your production URL.

Full interactive documentation available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

## Authentication

All endpoints currently rely on Supabase service role key passed via the `Authorization` header or configured in the backend environment. No public-facing auth is exposed.

## Health

### `GET /health`

System health check including database connectivity and queue depth.

**Response** `200 OK`:
```json
{
  "status": "healthy",
  "database": "connected",
  "queue_depth": 3,
  "version": "1.0.0"
}
```

---

## Videos

### `POST /api/v1/videos`

Create a new video record.

**Request Body**:
```json
{
  "channel_id": "uuid",
  "title": "The Disappearance of Jane Doe",
  "topic": "Missing persons cold case from 1998",
  "video_length_seconds": 900
}
```

**Response** `201 Created`: `VideoResponse`

### `GET /api/v1/videos`

List videos with optional filters.

**Query Parameters**:
- `channel_id` (uuid, optional)
- `status` (string, optional): `draft`, `processing`, `review`, `published`
- `limit` (int, default 20)
- `offset` (int, default 0)

**Response** `200 OK`: `PaginatedResponse[VideoResponse]`

### `GET /api/v1/videos/{video_id}`

Get a single video by ID.

**Response** `200 OK`: `VideoResponse`

### `PATCH /api/v1/videos/{video_id}`

Update video metadata.

**Request Body** (partial):
```json
{
  "title": "Updated Title",
  "status": "review"
}
```

**Response** `200 OK`: `VideoResponse`

---

## Channels

### `POST /api/v1/channels`

Create a new channel.

**Request Body**:
```json
{
  "name": "CrimeMill",
  "youtube_channel_id": "UCxxxxxxxxxxxxxxxx",
  "handle": "@crimemill",
  "description": "True crime documentaries powered by AI."
}
```

**Response** `201 Created`: `ChannelResponse`

### `GET /api/v1/channels`

List all channels.

**Response** `200 OK`: `list[ChannelResponse]`

### `GET /api/v1/channels/{channel_id}`

Get a single channel.

**Response** `200 OK`: `ChannelResponse`

---

## Pipeline

### `POST /api/v1/pipeline/trigger/{video_id}`

Trigger the pipeline for a video. Creates pipeline jobs for all 17 stages.

**Query Parameters**:
- `start_stage` (string, optional): Start from a specific stage instead of the beginning.

**Response** `202 Accepted`:
```json
{
  "video_id": "uuid",
  "jobs_created": 17,
  "status": "queued"
}
```

### `GET /api/v1/pipeline/status/{video_id}`

Get pipeline status for a video.

**Response** `200 OK`: `PipelineStatusResponse`
```json
{
  "video_id": "uuid",
  "stages": {
    "script_generation": {"status": "completed", "started_at": "...", "completed_at": "..."},
    "voiceover_generation": {"status": "in_progress", "started_at": "..."},
    "image_generation": {"status": "pending"}
  },
  "overall_status": "in_progress",
  "progress_pct": 35
}
```

### `POST /api/v1/pipeline/retry/{video_id}`

Retry failed stages for a video.

**Query Parameters**:
- `stage` (string, optional): Retry a specific stage only.

**Response** `200 OK`:
```json
{
  "retried_stages": ["voiceover_generation"],
  "status": "queued"
}
```

---

## Topics

### `GET /api/v1/topics`

List discovered topics.

**Query Parameters**:
- `channel_id` (uuid, optional)
- `min_score` (float, optional)
- `limit` (int, default 20)
- `offset` (int, default 0)

**Response** `200 OK`: `PaginatedResponse[TopicResponse]`

### `GET /api/v1/topics/{topic_id}`

Get a single topic with full scoring details.

**Response** `200 OK`: `TopicResponse`

### `POST /api/v1/topics/discover`

Trigger topic discovery pipeline.

**Query Parameters**:
- `channel_id` (uuid, required)

**Response** `202 Accepted`:
```json
{
  "discovered": 15,
  "above_threshold": 8
}
```

---

## Analytics

### `GET /api/v1/analytics/channel/{channel_id}/summary`

Daily channel performance summary.

**Query Parameters**:
- `days` (int, default 30)

**Response** `200 OK`: `ChannelDailySummary`

### `GET /api/v1/analytics/video/{video_id}/retention`

Video retention curve data.

**Response** `200 OK`:
```json
{
  "video_id": "uuid",
  "retention_curve": [100, 95, 88, 82, 75, ...],
  "avg_view_duration_seconds": 540
}
```

### `GET /api/v1/analytics/video/{video_id}/profitability`

Video cost vs revenue analysis.

**Response** `200 OK`: `VideoProfitability`

### `GET /api/v1/analytics/channel/{channel_id}/top-videos`

Top performing videos for a channel.

**Query Parameters**:
- `limit` (int, default 10)
- `sort_by` (string, default "views"): `views`, `revenue`, `ctr`

**Response** `200 OK`: `list[VideoPerformanceScore]`

### `POST /api/v1/analytics/collect`

Trigger analytics collection for a channel.

**Query Parameters**:
- `channel_id` (uuid, required)

**Response** `200 OK`: `CollectionResult`

### `POST /api/v1/analytics/collect/realtime`

Collect real-time analytics for recently published videos.

**Response** `200 OK`: `CollectionResult`

---

## Schedule

### `GET /api/v1/schedule/calendar`

View the publishing calendar.

**Query Parameters**:
- `channel_id` (uuid, required)
- `days` (int, default 14)

**Response** `200 OK`: `list[ScheduleSlot]`

### `GET /api/v1/schedule/review-queue`

List videos awaiting review before publishing.

**Query Parameters**:
- `channel_id` (uuid, required)

**Response** `200 OK`: `list[VideoResponse]`

### `POST /api/v1/schedule/approve/{video_id}`

Approve a video for scheduled publishing.

**Response** `200 OK`:
```json
{
  "video_id": "uuid",
  "scheduled_for": "2026-03-25T18:00:00Z",
  "status": "scheduled"
}
```

### `POST /api/v1/schedule/reject/{video_id}`

Reject a video from publishing.

**Request Body**:
```json
{
  "reason": "Hook needs to be stronger"
}
```

**Response** `200 OK`

### `POST /api/v1/schedule/reschedule/{video_id}`

Reschedule a video to a different time slot.

**Request Body**:
```json
{
  "new_datetime": "2026-03-26T20:00:00Z"
}
```

**Response** `200 OK`

### `GET /api/v1/schedule/next-slot/{channel_id}`

Get the next available publishing slot.

**Response** `200 OK`: `ScheduleSlot`

---

## Series

### `POST /api/v1/series`

Create a new multi-part series.

**Request Body**: `SeriesInput`
```json
{
  "channel_id": "uuid",
  "title": "The Vanishing",
  "series_type": "sequential",
  "planned_episodes": 5,
  "description": "A five-part deep dive into..."
}
```

**Response** `201 Created`: `SeriesResponse`

### `GET /api/v1/series`

List series with pagination.

**Query Parameters**:
- `channel_id` (uuid, optional)
- `status` (string, optional)
- `limit` (int, default 20)
- `offset` (int, default 0)

**Response** `200 OK`: `PaginatedResponse[SeriesResponse]`

### `GET /api/v1/series/{series_id}`

Get series details with episodes.

**Response** `200 OK`: `SeriesResponse`

### `POST /api/v1/series/{series_id}/plan`

Generate a narrative arc plan using Claude.

**Response** `200 OK`: `SeriesArc`

### `GET /api/v1/series/{series_id}/analytics`

Series performance analytics.

**Response** `200 OK`: `SeriesAnalytics`

### `POST /api/v1/series/{series_id}/playlist`

Auto-create a YouTube playlist for the series.

**Response** `200 OK`:
```json
{
  "playlist_id": "PLxxxxxxxxxxxxxxxx"
}
```

### `POST /api/v1/series/suggest/{channel_id}`

AI-generated series suggestions based on channel performance.

**Response** `200 OK`: `SeriesSuggestionResult`

---

## Community

### `GET /api/v1/community/submissions`

List topic submissions from the community.

**Query Parameters**:
- `status` (string, optional): `pending`, `accepted`, `rejected`
- `limit` (int, default 20)
- `offset` (int, default 0)

**Response** `200 OK`: `PaginatedResponse[TopicSubmission]`

### `GET /api/v1/community/submissions/count`

Count submissions by status.

**Response** `200 OK`:
```json
{
  "pending": 12,
  "accepted": 45,
  "rejected": 8
}
```

### `GET /api/v1/community/submissions/{submission_id}`

Get a single submission.

**Response** `200 OK`: `TopicSubmission`

### `POST /api/v1/community/submissions`

Submit a topic suggestion.

**Request Body**:
```json
{
  "case_name": "The Springfield Three",
  "description": "Three women vanished from a home in 1992...",
  "source_url": "https://...",
  "submitter_name": "Anonymous"
}
```

**Response** `201 Created`: `TopicSubmission`

### `PATCH /api/v1/community/submissions/{submission_id}`

Accept or reject a submission.

**Request Body**:
```json
{
  "status": "accepted",
  "reviewer_notes": "Great suggestion, adding to queue."
}
```

**Response** `200 OK`: `TopicSubmission`

---

## Research

### `GET /api/v1/research/search`

Full-text search across research sources.

**Query Parameters**:
- `q` (string, required): Search query
- `source_type` (string, optional): `news`, `court_record`, `academic`, `government`
- `limit` (int, default 20)

**Response** `200 OK`: `list[ResearchSourceResponse]`

### `GET /api/v1/research/cases`

List case files.

**Query Parameters**:
- `category` (string, optional)
- `limit` (int, default 20)
- `offset` (int, default 0)

**Response** `200 OK`: `PaginatedResponse[CaseFileResponse]`

### `GET /api/v1/research/cases/{case_id}`

Get a single case file with all sources.

**Response** `200 OK`: `CaseFileResponse`

### `POST /api/v1/research/cases`

Create a new case file.

**Request Body**:
```json
{
  "title": "The Springfield Three",
  "category": "missing_persons",
  "summary": "..."
}
```

**Response** `201 Created`: `CaseFileResponse`

### `POST /api/v1/research/collect`

Trigger research collection for a topic.

**Request Body**:
```json
{
  "topic": "Springfield Three disappearance",
  "source_types": ["news", "court_record"]
}
```

**Response** `200 OK`: `CollectionResult`

### `GET /api/v1/research/foia`

List FOIA requests.

**Query Parameters**:
- `status` (string, optional): `drafted`, `sent`, `acknowledged`, `fulfilled`, `denied`, `appealed`

**Response** `200 OK`: `list[FOIAResponse]`

### `POST /api/v1/research/foia`

File a new FOIA request.

**Request Body**:
```json
{
  "agency": "FBI",
  "subject": "Case file #12345",
  "description": "Requesting all documents related to..."
}
```

**Response** `201 Created`: `FOIAResponse`

### `PATCH /api/v1/research/foia/{foia_id}`

Update FOIA request status.

**Request Body**:
```json
{
  "status": "acknowledged",
  "notes": "Received confirmation email on 2026-03-20"
}
```

**Response** `200 OK`: `FOIAResponse`

---

## Error Responses

All errors follow a consistent format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

| Status Code | Meaning |
|-------------|---------|
| `400` | Bad request (validation error) |
| `404` | Resource not found |
| `409` | Conflict (duplicate, already exists) |
| `422` | Unprocessable entity (Pydantic validation) |
| `429` | Rate limit exceeded |
| `500` | Internal server error |

## Rate Limiting

API endpoints are rate-limited via `slowapi`:
- Default: 60 requests/minute per IP
- Analytics collection: 10 requests/minute
- Pipeline trigger: 20 requests/minute
