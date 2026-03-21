# Pipeline

## Stages

| # | Stage | Service | Depends On | Timeout | Retries |
|---|-------|---------|------------|---------|---------|
| 1 | script_generation | Claude API | — | 120s | 3 |
| 2 | voiceover_generation | Fish Audio | script | 300s | 3 |
| 3 | image_generation | fal.ai | script | 600s | 3 |
| 4 | music_selection | Music API | script | 60s | 2 |
| 5 | audio_processing | pydub | voice + music | 180s | 2 |
| 6 | image_processing | Pillow | images | 120s | 2 |
| 7 | caption_generation | Groq Whisper | voice | 60s | 2 |
| 8 | video_assembly | Remotion | audio + images + captions | 300s | 2 |
| 9 | thumbnail_generation | fal.ai | script | 120s | 2 |
| 10 | youtube_upload | YouTube API | video + thumbnail | 600s | 3 |

## Parallelism

After script generation completes, four stages run **in parallel**:
- voiceover_generation
- image_generation
- music_selection
- thumbnail_generation

Then:
- audio_processing waits for voiceover + music
- image_processing waits for images
- caption_generation waits for voiceover
- video_assembly waits for audio + images + captions
- youtube_upload waits for video + thumbnail

## Video Status State Machine

```
pending
  └─▶ topic_selected
        └─▶ script_generated
              └─▶ media_generating
                    └─▶ media_complete
                          └─▶ assembling
                                └─▶ assembled
                                      └─▶ uploading
                                            └─▶ published

Any state can transition to:
  ├─▶ failed
  └─▶ cancelled
```

## Error Handling

1. Each job has a `max_retries` count (configurable per stage)
2. On failure, the job's `retry_count` increments
3. The `visible_at` timestamp is set to `now() + 2^retry_count minutes` (exponential backoff)
4. The job returns to `pending` status and becomes eligible for pickup after `visible_at`
5. If `retry_count >= max_retries`, the job moves to `dead_letter` status
6. Dead-letter jobs can be manually retried via `POST /api/v1/pipeline/retry/{video_id}`
