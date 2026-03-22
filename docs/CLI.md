# CLI Reference

The CrimeMill CLI provides 32 commands across 10 command groups for managing channels, pipelines, analytics, and more.

## Global Options

```
--json    Output results as JSON instead of formatted tables
--help    Show help for any command
```

## Usage

```bash
python -m src.cli [OPTIONS] COMMAND [ARGS]...
```

---

## `health` - System Health Check

```bash
python -m src.cli health
```

Checks database connectivity, queue depth, and service status.

**Example Output**:
```
System Health
  Database:    connected
  Queue depth: 3 pending jobs
  Workers:     1 active
```

---

## `budget` - Budget Report

```bash
python -m src.cli budget --channel CHANNEL_NAME
```

Shows cost breakdown and budget utilization.

---

## `channel` - Channel Management

### `channel create`

```bash
python -m src.cli channel create \
  --name "CrimeMill" \
  --youtube-id "UCxxxxxxxxxxxxxxxx" \
  --handle "@crimemill" \
  --niche true_crime_general \
  --description "True crime documentaries" \
  --voice-id "" \
  --thumbnail-archetype "storyteller"
```

Creates a channel with all 4 settings table rows (channel, voice, brand, credentials).

**Niche options**: `true_crime_general`, `cold_case`, `financial_crime`, `serial_killer`, `missing_persons`

### `channel list`

```bash
python -m src.cli channel list
```

### `channel setup-voice`

```bash
python -m src.cli channel setup-voice \
  --channel "CrimeMill" \
  --sample ./voice-sample.wav
```

Clones a voice via Fish Audio from a 15-30 second audio sample.

### `channel setup-youtube-auth`

```bash
python -m src.cli channel setup-youtube-auth --channel "CrimeMill"
```

Interactive OAuth2 flow: opens browser, user authorizes, pastes auth code.

---

## `pipeline` - Pipeline Operations

### `pipeline trigger`

```bash
python -m src.cli pipeline trigger VIDEO_ID [--stage STAGE_NAME]
```

Start the full pipeline or from a specific stage.

**Example**:
```bash
python -m src.cli pipeline trigger 550e8400-e29b-41d4-a716-446655440000
python -m src.cli pipeline trigger 550e8400... --stage voiceover_generation
```

### `pipeline status`

```bash
python -m src.cli pipeline status VIDEO_ID
```

**Example Output**:
```
Pipeline Status: 550e8400...

 Stage                      Status      Duration
 script_generation          completed   12.3s
 voiceover_generation       completed   45.1s
 image_generation           completed   38.7s
 music_selection            completed   1.2s
 audio_processing           in_progress --
 image_processing           completed   8.4s
 caption_generation         completed   3.1s
 video_assembly             pending     --
 ...

Progress: 6/17 stages completed (35%)
```

### `pipeline retry`

```bash
python -m src.cli pipeline retry VIDEO_ID [--stage STAGE_NAME]
```

### `pipeline list`

```bash
python -m src.cli pipeline list \
  --channel "CrimeMill" \
  --status pending \
  --limit 20
```

---

## `review` - Review Workflow

### `review queue`

```bash
python -m src.cli review queue --channel "CrimeMill"
```

Shows videos that have completed rendering and await human review.

### `review approve`

```bash
python -m src.cli review approve VIDEO_ID
```

Marks video as approved and schedules for publishing.

### `review reject`

```bash
python -m src.cli review reject VIDEO_ID --reason "Hook needs work"
```

---

## `schedule` - Publishing Schedule

### `schedule show`

```bash
python -m src.cli schedule show --channel "CrimeMill" --days 14
```

**Example Output**:
```
Publishing Calendar: CrimeMill (next 14 days)

 Date        Time    Video                          Status
 Mon Mar 23  18:00   The Springfield Three           scheduled
 Thu Mar 26  18:00   Cold Case: Lake City            review
 Mon Mar 30  18:00   (empty slot)                    --
```

### `schedule publish-now`

```bash
python -m src.cli schedule publish-now VIDEO_ID
```

Immediately publishes a video, bypassing the schedule.

---

## `analytics` - Performance Analytics

### `analytics daily`

```bash
python -m src.cli analytics daily --channel "CrimeMill" --days 30
```

### `analytics top-videos`

```bash
python -m src.cli analytics top-videos --channel "CrimeMill" --limit 10
```

### `analytics costs`

```bash
python -m src.cli analytics costs --days 30
```

Shows per-video and per-stage cost breakdown.

---

## `topics` - Topic Discovery

### `topics discover`

```bash
python -m src.cli topics discover --channel "CrimeMill"
```

Runs the topic discovery pipeline (GDELT, Reddit, trending analysis).

### `topics list`

```bash
python -m src.cli topics list --channel "CrimeMill" --min-score 70
```

---

## `music` - Music Library

### `music library`

```bash
python -m src.cli music library
```

**Example Output**:
```
Music Library Status

 Mood Category               Tracks   Duration
 suspenseful_investigation   6        18.3 min
 emotional_reflective        5        15.1 min
 dramatic_reveal             4        12.0 min
 establishing_neutral        5        16.2 min
 eerie_dark_ambient          4        14.5 min

Total: 24 tracks, 76.1 minutes
```

### `music add`

```bash
python -m src.cli music add \
  --file ./dark-ambience.wav \
  --mood eerie_dark_ambient \
  --bpm 65 \
  --title "Dark Ambience" \
  --artist "Epidemic Sound"
```

---

## `series` - Series Management

### `series create`

```bash
python -m src.cli series create \
  --channel "CrimeMill" \
  --title "The Vanishing" \
  --type sequential \
  --episodes 5
```

**Series types**: `sequential`, `anthology`, `investigation`

### `series plan`

```bash
python -m src.cli series plan SERIES_ID
```

Uses Claude to generate a full narrative arc with per-episode breakdowns.

### `series status`

```bash
python -m src.cli series status --channel "CrimeMill"
```

### `series analytics`

```bash
python -m src.cli series analytics SERIES_ID
```

---

## `research` - Research & FOIA

### `research search`

```bash
python -m src.cli research search "cold case disappearance 1998"
```

Full-text search across all collected research sources.

### `research collect`

```bash
python -m src.cli research collect --topic "Doe v. State 2015"
```

### `research cases`

```bash
python -m src.cli research cases --limit 20
```

### `research case-build`

```bash
python -m src.cli research case-build \
  --title "The Springfield Three" \
  --category missing_persons
```

### `research foia-file`

```bash
python -m src.cli research foia-file \
  --agency "FBI" \
  --subject "Case #12345" \
  --description "Requesting all documents..."
```

### `research foia-list`

```bash
python -m src.cli research foia-list --status pending
```

### `research foia-update`

```bash
python -m src.cli research foia-update FOIA_ID --status acknowledged
```

---

## `community` - Community Ecosystem

### `community submissions list`

```bash
python -m src.cli community submissions list
```

### `community submissions review`

```bash
python -m src.cli community submissions review SUBMISSION_ID --action accept
```

### `community discord-notify`

```bash
python -m src.cli community discord-notify \
  --channel "CrimeMill" \
  --message "New video: The Springfield Three"
```

### `community patreon-sync`

```bash
python -m src.cli community patreon-sync
```

### `community metrics`

```bash
python -m src.cli community metrics --channel "CrimeMill"
```

---

## `optimize` - A/B Testing

### `optimize thumbnails`

```bash
python -m src.cli optimize thumbnails VIDEO_ID --variants 3
```

### `optimize titles`

```bash
python -m src.cli optimize titles VIDEO_ID --variants 5
```

### `optimize report`

```bash
python -m src.cli optimize report --channel "CrimeMill"
```

---

## JSON Output

All commands support `--json` for machine-readable output:

```bash
python -m src.cli --json pipeline status VIDEO_ID
python -m src.cli --json analytics daily --channel "CrimeMill"
```
