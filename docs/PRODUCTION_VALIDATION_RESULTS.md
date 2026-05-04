# CrimeMill Production Validation Results

Generated: 2026-05-03 18:32:24

## Summary

- **Total tests:** 8
- **Passed:** 3
- **Failed:** 4
- **Skipped:** 1
- **Total time:** 9.0 min (542s)
- **Total API cost:** $0.077169

## Per-test results

| # | Test | Status | Duration | Cost | Details |
|---|---|---|---|---|---|
| 1 | Railway /health | FAIL | 15.6s | $0 | HTTP request failed: ReadTimeout: ReadTimeout('') |
| 2 | Railway -> Supabase | FAIL | 15.4s | $0 | HTTP request failed: ReadTimeout: ReadTimeout('') |
| 3 | Remotion Lambda render | FAIL | 303.5s | $0 | Remotion render exited with code 1 |
| 4 | Street Level travel script | FAIL | 84.8s | $0 | 'Street Level' brand not found in output |
| 5 | CrimeMill crime script | PASS | 119.9s | $0.077169 | word_count=3247, hook_type=cold_open, open_loops=4 |
| 6 | R2 round-trip | PASS | 1.1s | $0 | bucket=crimemill-assets, key=_validation/f674d07a019b4f67a45f86caf2f069a6.txt, payload_bytes=50 |
| 7 | DB CRUD via pooler | PASS | 0.8s | $0 | ops=['CONNECT', 'INSERT', 'SELECT', 'DELETE'], channel_id=3fa58beb-c654-4930-a3bb-5efaa497954c, name=__validation_test__ |
| 8 | E2E pipeline trigger | SKIP | 0.5s | $0 | POST /api/v1/pipeline/trigger (no video_id) not wired |

## Detailed output

### Test 1: Railway /health

**Status:** FAIL  
**Duration:** 15.6s  
**Cost:** $0

```json
{
  "url": "https://travel-street-level-production.up.railway.app/health"
}
```
**Error:**
```
HTTP request failed: ReadTimeout: ReadTimeout('')
```
**Suggested fix:** Check that RAILWAY_URL is correct and Railway deployment is live

### Test 2: Railway -> Supabase

**Status:** FAIL  
**Duration:** 15.4s  
**Cost:** $0

```json
{
  "url": "https://travel-street-level-production.up.railway.app/health"
}
```
**Error:**
```
HTTP request failed: ReadTimeout: ReadTimeout('')
```
**Suggested fix:** Railway not reachable

### Test 3: Remotion Lambda render

**Status:** FAIL  
**Duration:** 303.5s  
**Cost:** $0

```json
{
  "duration_s": 302.5,
  "stdout_tail": "\u001b[90mRemotion root directory:\u001b[39m \u001b[90mC:\\Users\\Varun\\crimemill\\video\u001b[39m\n\u001b[90mApplied configuration from C:\\Users\\Varun\\crimemill\\video\\remotion.config.ts.\u001b[39m\n\u001b[31mAn error occurred:\u001b[39m\n\n",
  "stderr_tail": ""
}
```
**Error:**
```
Remotion render exited with code 1
```
**Suggested fix:** Check stdout_tail/stderr_tail below for the underlying Lambda error. Common causes: bad serve URL, missing Lambda function, IAM policy gap, composition rendering error (often: missing required props), Lambda timeout.

### Test 4: Street Level travel script

**Status:** FAIL  
**Duration:** 84.8s  
**Cost:** $0

```json
{
  "word_count": 2027,
  "stdout_tail": "IPTION\r\n----------------------------------------------------------------------\r\nRoad No. 14 in Banjara Hills looks upscale and feels safe\u2014but the real threats to travelers here aren't what you'd expect. This video breaks down the actual safety data for this Hyderabad location, cuts through the hype, and shows you exactly what to watch out for and how to protect yourself.\r\n\r\n**Key Takeaways**\r\n\u2022 Road traffic is the #1 physical danger\u2014zero sidewalk coverage means you need to use ride-shares, not walk major roads\r\n\u2022 Air pollution runs 3\u20134\u00d7 WHO safety levels; bring N95 masks and avoid peak pollution hours if you have respiratory conditions\r\n\u2022 Crime here is opportunistic (pickpocketing, taxi scams, ATM skimming), not violent\u2014use hotel ATMs and stick to Ola/Uber\r\n\u2022 Banjara Hills has one of India's lowest crime rates and excellent medical facilities within 10 minutes\r\n\u2022 Business travelers should be cautious of unsolicited offers and honey-trap schemes in upscale hotels\r\n\r\nSpecial thanks to Rhyo Security Solutions for providing the safety intelligence data used in this video. Learn more at rhyo.com.\r\n\r\nTimestamps: (auto-generated after upload)\r\n\r\n#HyderabadTravel #TravelSafety\r\n======================================================================\r\nDESTINATIONS\r\n----------------------------------------------------------------------\r\n  [primary  ] Banjara Hills, Hyderabad, Telangana, IN  tags=['safety_briefing']\r\n======================================================================\r\n"
}
```
**Error:**
```
'Street Level' brand not found in output
```
**Suggested fix:** Check travel_safety prompts: brand should be 'Street Level', narration must not mention 'Rhyo'

### Test 5: CrimeMill crime script

**Status:** PASS  
**Duration:** 119.9s  
**Cost:** $0.077169

```json
{
  "word_count": 3247,
  "hook_type": "cold_open",
  "open_loops": 4,
  "twists": 3,
  "script_head": "[HOOK]\n\n[SCENE: Sleek glass towers of Munich's financial district at dawn, mist rolling between buildings]\n\n[cold, clinical] June eighteenth, 2020. Munich. The sirens weren't for a murder. They were f"
}
```

### Test 6: R2 round-trip

**Status:** PASS  
**Duration:** 1.1s  
**Cost:** $0

```json
{
  "bucket": "crimemill-assets",
  "key": "_validation/f674d07a019b4f67a45f86caf2f069a6.txt",
  "payload_bytes": 50,
  "head_latency_ms": 281
}
```

### Test 7: DB CRUD via pooler

**Status:** PASS  
**Duration:** 0.8s  
**Cost:** $0

```json
{
  "ops": [
    "CONNECT",
    "INSERT",
    "SELECT",
    "DELETE"
  ],
  "channel_id": "3fa58beb-c654-4930-a3bb-5efaa497954c",
  "name": "__validation_test__",
  "db_url": "postgresql://postgres.qflkctgemkwochgkzqzj:***@aws-1-us-east-1.pooler.supabase.com:6543/postgres",
  "note": "channels table has no `niche` column; recorded as description"
}
```

### Test 8: E2E pipeline trigger

**Status:** SKIP  
**Duration:** 0.5s  
**Cost:** $0

```json
{
  "reason": "POST /api/v1/pipeline/trigger (no video_id) not wired"
}
```
**Suggested fix:** Only POST /api/v1/pipeline/trigger/{video_id} exists. There is no public endpoint that creates a video from a Rhyo fixture path; that requires internal orchestration. Add a niche-level trigger route to enable Test 8.
