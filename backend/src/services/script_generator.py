"""Script generation service — all LLM interactions in the CrimeMill pipeline.

Routes tasks to the appropriate Claude model:
- Creative tasks (script, titles) → Claude Sonnet 4
- Structured tasks (scene breakdown, image prompts, description) → Claude Haiku 4.5

Every call tracks token usage and calculates cost.  Prompt caching is enabled
on system prompts via ``cache_control`` to reduce repeat-call costs.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import anthropic
import structlog

from src.models.script import (
    APICallCost,
    BrandSettings,
    ChannelSettings,
    DescriptionResult,
    HookType,
    ImagePrompt,
    ImagePromptsResult,
    SceneBreakdown,
    SceneBreakdownResult,
    ScriptOutput,
    TitleFormula,
    TitlesResult,
    TitleVariant,
    TopicInput,
    TwistPlacement,
)

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Model routing
# ---------------------------------------------------------------------------

MODEL_SONNET: str = "claude-sonnet-4-20250514"
MODEL_HAIKU: str = "claude-haiku-4-5-20251001"

# USD per 1 M tokens
PRICING: dict[str, dict[str, Decimal]] = {
    MODEL_SONNET: {"input": Decimal("3"), "output": Decimal("15")},
    MODEL_HAIKU: {"input": Decimal("1"), "output": Decimal("5")},
}

_ONE_MILLION = Decimal("1_000_000")

# Word-count targets keyed by target video length in minutes
WORD_COUNT_TARGETS: dict[int, tuple[int, int]] = {
    10: (1_200, 1_500),
    15: (1_950, 2_250),
    20: (2_500, 3_000),
    25: (3_000, 3_500),
}

# Ordered lists used for deterministic rotation
HOOK_ROTATION: list[HookType] = list(HookType)
TITLE_ROTATION: list[TitleFormula] = list(TitleFormula)

# Maximum retry attempts for transient API errors
MAX_RETRIES: int = 3
BASE_RETRY_DELAY: float = 1.0


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ScriptGenerationError(Exception):
    """Base error for all script-generation failures."""


class RateLimitError(ScriptGenerationError):
    """Anthropic rate-limit (429) hit after retries exhausted."""


class ContentFilterError(ScriptGenerationError):
    """Content blocked by Anthropic's safety filters."""


class ModelAPIError(ScriptGenerationError):
    """Non-retryable API error from Anthropic."""


# ---------------------------------------------------------------------------
# Section 4.3 — Complete Script Generation System Prompt
# ---------------------------------------------------------------------------

SCRIPT_SYSTEM_PROMPT: str = """\
You are the head writer for a premium true-crime YouTube documentary channel.
You write scripts that are cinematic, gripping, and ruthlessly optimized for
YouTube audience retention.  Every sentence must earn its place.

# ═══════════════════════════════════════════════════════════════════════════
# STRUCTURAL RULES
# ═══════════════════════════════════════════════════════════════════════════

## Word-Count Targets (MANDATORY — match the requested video length)
- 10-minute video → 1,200 – 1,500 words
- 15-minute video → 1,950 – 2,250 words
- 20-minute video → 2,500 – 3,000 words
- 25-minute video → 3,000 – 3,500 words

Count carefully.  Going under by >10 % or over by >5 % is a failure.

## Backward-from-Reveal Construction
1. Identify the central REVEAL — the twist, the answer, the shocking truth.
2. Work backward: what must the viewer understand before the reveal lands?
3. Layer information so each section is a necessary brick in the wall.
4. By the end the viewer should feel every single detail was essential.

## Open Loops
Maintain 2 – 4 simultaneous open loops AT ALL TIMES:
- Plant the first loop inside the hook.
- Open new loops as you close old ones — the audience must always have a
  reason to keep watching.
- Never close all loops at once until the final act.

## Twist Placement
Place significant twists or reveals at these structural beats:
- **25 % mark** — First twist.  Reframes the setup.
- **50 % mark** — Midpoint reversal.  Everything changes.
- **75 % mark** — Final twist before resolution.  Darkest moment or biggest reveal.

# ═══════════════════════════════════════════════════════════════════════════
# TIMING & ANNOTATION MARKERS  (embed these inline in the script)
# ═══════════════════════════════════════════════════════════════════════════

## Structural Timing Markers
[HOOK]              — Opening hook (first 15-30 s of narration)
[PROMISE]           — Promise / thesis (what the viewer will learn)
[STAKES]            — Stakes establishment (why this matters NOW)
[PATTERN_INTERRUPT] — Pattern interrupt (change of pace, unexpected beat, humor)
[AD_BREAK]          — Natural mid-roll ad break placement
[CTA_LIGHT]         — Light call-to-action ("if you're new here, hit subscribe…")
[CTA_ENGAGE]        — Engagement CTA ("drop a comment with your theory…")
[CTA_END]           — End-screen CTA (last 20 seconds of narration)
[SILENCE: Xs]       — Dramatic silence — specify duration (e.g., [SILENCE: 3s])

## Narration Speed Markers  (wrap sections)
[FAST] … [/FAST]       — Quick, energetic delivery
[NORMAL] … [/NORMAL]   — Standard conversational pace
[SLOW] … [/SLOW]       — Deliberate, weighty delivery
[REVEAL] … [/REVEAL]   — Dramatic reveal pacing (slower than SLOW)

## Fish Audio Emotion Tags  (mark at each emotional shift)
[calm, measured tone]
[tense, ominous]
[whisper]
[urgent, breathless]
[sardonic, dry]
[solemn, respectful]
[incredulous]
[conspiratorial, low]
[cold, clinical]
[mournful]

## Scene Descriptions  (for image generation)
[SCENE: <vivid visual description of what the viewer sees>]
Place a [SCENE] tag every time the visual should change — at least once per
major narrative beat.  Describe the IMAGE, not the narration.

## Sound-Effect Annotations
[SFX: <type>]       — e.g. [SFX: door slam], [SFX: heartbeat], [SFX: phone ringing]
[SILENCE: Xs]       — X seconds of silence (used for dramatic pause AND as SFX)
[MUSIC_DROP]        — Music cuts out abruptly for dramatic effect

# ═══════════════════════════════════════════════════════════════════════════
# HOOK TYPES — ROTATE  (you will be told which type to use)
# ═══════════════════════════════════════════════════════════════════════════

1. **Cold Open / In Medias Res** — Start at the single most dramatic moment
   of the story, then smash-cut to "But to understand how we got here…"
2. **Provocative Question** — Open with a question that challenges
   assumptions.  The question itself is the hook.
3. **Shocking Statistic** — Lead with a jarring, verifiable number.  Let the
   number breathe with a [SILENCE: 2s] after it.
4. **Contradiction / Paradox** — Present two facts that seem impossible
   together: "He was a beloved pastor.  He was also a serial killer."
5. **Sensory Scene-Setting** — Drop the viewer into a hyper-specific moment:
   a sound, a smell, a detail only someone there would notice.

# ═══════════════════════════════════════════════════════════════════════════
# CONTENT RULES  (MANDATORY — violation = rejected output)
# ═══════════════════════════════════════════════════════════════════════════

## Sourcing & Attribution
- Reference court records, official documents, and verified reporting ONLY.
- Use "allegedly," "according to court documents," "prosecutors stated,"
  "investigators later determined" — always attribute.
- Never state guilt as established fact unless there is a conviction.

## Victim-Centered Framing
- Name every victim.  Humanize them BEFORE describing what happened to them.
- At least two sentences establishing who the victim was as a person.
- Never reduce a victim to just a plot device.

## EDSA Narration Structure
Frame every major narrative beat using this cycle:
  **E**ngage → **D**escribe → **S**peculate → **A**nalyze
- Engage: hook the viewer into this beat ("But here's where it gets strange…")
- Describe: lay out the facts clearly and chronologically.
- Speculate: voice what the audience is thinking ("You might be wondering…").
- Analyze: provide expert or investigative context that reframes the facts.

## Coded Language — First 30 Seconds
NEVER use "kill," "murder," "suicide," "rape," or explicit violence terms in
the first 30 seconds of narration.  Use indirect language early:
  - "what happened to" / "was found" / "disappeared" / "didn't survive"
  - "the incident" / "the events of that night"
Introduce direct language only AFTER the hook is complete.

## Demonetization Avoidance
- No glorification of violence or criminals.
- Frame everything through investigation, justice, or prevention.
- Avoid gratuitous detail about methods of violence.

# ═══════════════════════════════════════════════════════════════════════════
# ANTI-AI DETECTION RULES  (Section 4.2)
# ═══════════════════════════════════════════════════════════════════════════

## Forbidden Words — NEVER use these (instant AI-detection flags):
delve, tapestry, landscape, nuance, leverage, illuminate, moreover,
furthermore, seamlessly, multifaceted

## Also Avoid:
utilize (use "use"), facilitate (use "help" or "make possible"),
endeavor, subsequently, comprehensive, pivotal, groundbreaking,
in conclusion, it's worth noting, it's important to note,
in today's world, at the end of the day, the fact of the matter

## Style Rules (write like a HUMAN, not a language model):
- USE contractions always (it's, don't, wasn't, they'd, would've).
- USE sentence fragments for impact.  Like this.  Often.
- VARY sentence length dramatically.  Short.  Then a longer sentence that
  builds and winds and layers detail before finally landing.  Then short again.
- USE rhetorical questions to open loops ("But why would a man with
  everything to lose do something so reckless?").
- INCLUDE at least 2 moments of dark humor or sardonic observation — true
  crime audiences expect and reward dry wit.
- WRITE for the EAR, not the eye.  If a sentence sounds stiff when read
  aloud, rewrite it.
- AVOID passive voice unless used deliberately for effect ("The body was
  found" is fine; "It was determined by investigators" is not).
- START paragraphs with varied structures — never begin 3 consecutive
  paragraphs the same way.
- MIX registers: formal analysis next to colloquial asides.
- Occasionally break the fourth wall ("Yeah, I know.  It gets worse.").

# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE FORMAT
# ═══════════════════════════════════════════════════════════════════════════

Respond with a SINGLE JSON object and nothing else:

{
  "script_text": "<the complete annotated script>",
  "word_count": <integer>,
  "estimated_duration_seconds": <float>,
  "hook_type": "<cold_open|provocative_question|shocking_statistic|contradiction|sensory_scene>",
  "open_loops": ["<description of loop 1>", "…"],
  "twist_placements": [
    {"position_percent": 25, "description": "…"},
    {"position_percent": 50, "description": "…"},
    {"position_percent": 75, "description": "…"}
  ]
}

The "script_text" field contains the ENTIRE script with all markers inline.
Do NOT wrap JSON in markdown code fences.
"""


# ---------------------------------------------------------------------------
# Scene Breakdown System Prompt
# ---------------------------------------------------------------------------

SCENE_BREAKDOWN_SYSTEM_PROMPT: str = """\
You are a post-production editor breaking a crime-documentary script into
timed scenes for automated video assembly.

Given a narration script with inline markers ([SCENE], [SFX], [SILENCE],
speed markers, emotion tags, [AD_BREAK], [PATTERN_INTERRUPT], etc.), produce
a frame-accurate scene breakdown as a JSON array.

## Rules
- Split on every [SCENE: …] marker in the script.
- Calculate timing assuming ~150 words per minute at [NORMAL] speed,
  ~180 wpm at [FAST], ~120 wpm at [SLOW], and ~100 wpm at [REVEAL].
- Add [SILENCE: Xs] durations to the running clock.
- Distribute scenes to fill the total target duration evenly.
- Preserve the EXACT narration text for each scene (strip markers but keep
  the spoken words).
- Extract the emotion tag active at the start of each scene.
- Extract all [SFX: …] annotations within the scene.
- Flag scenes that contain [AD_BREAK] or [PATTERN_INTERRUPT].

## Response Format
Respond with a single JSON array (no wrapper object, no markdown fences):
[
  {
    "scene_number": 1,
    "start_time_seconds": 0.0,
    "end_time_seconds": 25.5,
    "narration_text": "…",
    "scene_description": "…",
    "emotion_tag": "calm, measured tone",
    "narration_speed": "NORMAL",
    "sfx_annotations": ["door slam", "heartbeat"],
    "is_ad_break": false,
    "is_pattern_interrupt": false
  },
  …
]
"""


# ---------------------------------------------------------------------------
# Image Prompt System Prompt
# ---------------------------------------------------------------------------

IMAGE_PROMPT_SYSTEM_PROMPT: str = """\
You are a cinematic image-prompt engineer for a true-crime YouTube channel.

Given a list of scene descriptions from a documentary script, generate one
high-quality image-generation prompt per scene.  Each prompt must produce a
photorealistic, cinematic still that matches the scene's mood and content.

## Rules
- Write each prompt as a single dense paragraph — no line breaks inside.
- Start with the subject, then setting, then cinematic details (lighting,
  camera angle, color grade, atmosphere).
- The channel's master prompt suffix will be appended automatically — do NOT
  repeat it.
- Include mood-appropriate lighting cues.
- NEVER include text, watermarks, or UI elements in prompts.
- NEVER depict identifiable real people — use generic descriptions
  ("a middle-aged man," "a woman in her 30s").
- Aspect ratio is 16:9.  Compose for widescreen.

## Response Format
Respond with a single JSON array (no wrapper, no fences):
[
  {
    "scene_number": 1,
    "prompt": "…",
    "lighting": "low-key side lighting with blue fill",
    "mood": "ominous, foreboding"
  },
  …
]
"""


# ---------------------------------------------------------------------------
# Title Generation System Prompt
# ---------------------------------------------------------------------------

TITLE_SYSTEM_PROMPT: str = """\
You are a YouTube title specialist for a true-crime documentary channel.
Your titles are engineered for maximum CTR while staying honest and
non-clickbait.

## Title Formulas (use the ones assigned in the user message)
1. **adjective_case**  — "The [Adjective] Case of [Name/Place]"
2. **how_person**      — "How [Person/Group] [Shocking Verb Phrase]"
3. **nobody_talks**    — "[Subject]: The [Adjective] [Story/Truth/Secret] Nobody Talks About"
4. **why_question**    — "Why [Unexpected Statement]?"
5. **truth_behind**    — "The [Adjective] Truth Behind [Event/Case]"
6. **what_happened**   — "What Really Happened to [Person/Place]"

## Validation Rules (HARD CONSTRAINTS)
- 50 – 60 characters (including spaces).
- 5 – 9 words.
- 1 – 2 power words maximum (e.g., shocking, terrifying, bizarre, chilling,
  disturbing, deadly, twisted, haunting, sinister, infamous).
- Front-load the primary keyword in the first 3 words where possible.
- No ALL CAPS words.  No excessive punctuation.  One question mark max.

## Response Format
Respond with a single JSON array of exactly 5 objects, ranked best-first:
[
  {
    "title": "…",
    "formula": "adjective_case",
    "word_count": 7,
    "char_count": 54,
    "power_words": ["chilling"],
    "estimated_ctr_rank": 1
  },
  …
]
"""


# ---------------------------------------------------------------------------
# Description Generation System Prompt
# ---------------------------------------------------------------------------

DESCRIPTION_SYSTEM_PROMPT: str = """\
You are a YouTube SEO specialist writing video descriptions for a true-crime
documentary channel.

## Structure
1. **Hook line** (first 150 chars — visible before "Show more"): a
   compelling one-liner that complements the title without repeating it.
2. **Synopsis** (2-3 sentences): what the video covers, with natural keyword
   integration.
3. **Timestamps** placeholder: output the literal text "[TIMESTAMPS]" — the
   pipeline fills these in after caption generation.
4. **Affiliate / resource links**: insert any provided links with labels.
5. **Channel boilerplate**: subscribe CTA, social links placeholder, credits.
6. **Tags line**: 5-8 comma-separated tags for YouTube search (lowercase).

## Rules
- Natural language — no keyword stuffing.
- Include 2-3 relevant long-tail keywords organically.
- Never spoil the main twist.
- Total length: 800 – 1,500 characters.

## Response Format
Return ONLY the raw description text (no JSON, no fences).  The description
should be ready to paste directly into YouTube.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    is_batch: bool = False,
) -> Decimal:
    """Return USD cost for a single API call based on published pricing.

    Parameters
    ----------
    is_batch:
        If ``True``, applies the Anthropic Message Batches API 50 % discount
        on both input and output tokens.
    """
    prices = PRICING.get(model)
    if prices is None:
        logger.warning("unknown_model_pricing", model=model)
        return Decimal("0")

    batch_discount = Decimal("0.5") if is_batch else Decimal("1")

    # Cached input tokens are billed at 90 % discount on Anthropic
    billable_input = input_tokens - cached_input_tokens
    cached_cost = (
        Decimal(cached_input_tokens)
        * prices["input"]
        * Decimal("0.1")
        * batch_discount
        / _ONE_MILLION
    )
    input_cost = Decimal(billable_input) * prices["input"] * batch_discount / _ONE_MILLION
    output_cost = Decimal(output_tokens) * prices["output"] * batch_discount / _ONE_MILLION
    return (input_cost + cached_cost + output_cost).quantize(Decimal("0.000001"))


def _select_hook(topic_input: TopicInput) -> HookType:
    """Deterministically select a hook type via rotation index or explicit override."""
    if topic_input.hook_type is not None:
        return topic_input.hook_type
    return HOOK_ROTATION[topic_input.rotation_index % len(HOOK_ROTATION)]


def _select_title_formulas(rotation_index: int, count: int = 5) -> list[TitleFormula]:
    """Pick *count* distinct title formulas, rotating which one is excluded."""
    n = len(TITLE_ROTATION)
    excluded_idx = rotation_index % n
    pool = [f for i, f in enumerate(TITLE_ROTATION) if i != excluded_idx]
    # If we need more than pool size, wrap around (shouldn't happen with 6 choose 5)
    return (pool * ((count // len(pool)) + 1))[:count]


def _strip_json_fences(text: str) -> str:
    """Strip optional markdown code fences from a JSON response."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


# ---------------------------------------------------------------------------
# ScriptGenerator
# ---------------------------------------------------------------------------


class ScriptGenerator:
    """Handles ALL LLM interactions in the CrimeMill pipeline.

    Routes tasks to the optimal Claude model:
    - **Creative** (script writing, title ideation) → Claude Sonnet 4
    - **Structured** (scene breakdown, image prompts, description) → Claude Haiku 4.5

    Prompt caching is enabled on every system prompt to amortise cost across
    repeated calls within the same channel or session.

    Parameters
    ----------
    settings:
        Application settings (must contain ``anthropic.api_key``).
    http_client:
        Shared ``httpx.AsyncClient`` — unused by this service (the Anthropic
        SDK manages its own transport) but accepted for interface consistency
        with other pipeline services.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic.api_key)

    # ------------------------------------------------------------------
    # Internal: unified Claude caller with retry + cost tracking
    # ------------------------------------------------------------------

    async def _call_claude(
        self,
        *,
        model: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4_096,
        temperature: float = 1.0,
        batch_eligible: bool = False,
    ) -> tuple[str, APICallCost]:
        """Send a single message to Claude and return (text, cost).

        Retries up to ``MAX_RETRIES`` times on transient errors with
        exponential back-off.  Raises structured exceptions on permanent
        failures.

        Parameters
        ----------
        model:
            Anthropic model ID (``MODEL_SONNET`` or ``MODEL_HAIKU``).
        system_prompt:
            System-level instructions.  Sent with ``cache_control`` to enable
            prompt caching.
        user_message:
            The user-turn content.
        max_tokens:
            Maximum tokens in the response.
        temperature:
            Sampling temperature (0.0 – 1.0).
        batch_eligible:
            If ``True`` the call is flagged as non-urgent.  Currently logged
            only; the Anthropic Message Batches API can be integrated here for
            50 % cost savings on batch-eligible calls.
        """
        if batch_eligible:
            await logger.ainfo("batch_eligible_call", model=model)

        last_exc: BaseException | None = None

        for attempt in range(MAX_RETRIES):
            t0 = time.monotonic()
            try:
                response = await self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": user_message}],
                )
                latency_ms = int((time.monotonic() - t0) * 1_000)

                text = response.content[0].text  # type: ignore[union-attr]
                usage = response.usage

                input_tokens = usage.input_tokens
                output_tokens = usage.output_tokens
                cached_input = getattr(usage, "cache_creation_input_tokens", 0) + getattr(
                    usage, "cache_read_input_tokens", 0
                )
                cost_usd = _calculate_cost(model, input_tokens, output_tokens, cached_input)

                cost = APICallCost(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    cached_input_tokens=cached_input,
                )

                await logger.ainfo(
                    "claude_call_complete",
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cached_input,
                    cost_usd=str(cost_usd),
                    latency_ms=latency_ms,
                    attempt=attempt + 1,
                )
                return text, cost

            except anthropic.RateLimitError as exc:
                last_exc = exc
                await logger.awarning(
                    "rate_limit_hit",
                    model=model,
                    attempt=attempt + 1,
                    max_retries=MAX_RETRIES,
                )
            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500:
                    last_exc = exc
                    await logger.awarning(
                        "server_error",
                        model=model,
                        status=exc.status_code,
                        attempt=attempt + 1,
                    )
                elif exc.status_code == 400 and "content" in str(exc.message).lower():
                    raise ContentFilterError(
                        f"Content filtered by Anthropic: {exc.message}"
                    ) from exc
                else:
                    raise ModelAPIError(
                        f"Anthropic API error {exc.status_code}: {exc.message}"
                    ) from exc
            except anthropic.APIConnectionError as exc:
                last_exc = exc
                await logger.awarning(
                    "connection_error",
                    model=model,
                    attempt=attempt + 1,
                    error=str(exc),
                )

            # Exponential back-off with jitter
            if attempt < MAX_RETRIES - 1:
                delay = min(BASE_RETRY_DELAY * (2**attempt), 60.0)
                await asyncio.sleep(delay)

        # All retries exhausted
        if isinstance(last_exc, anthropic.RateLimitError):
            raise RateLimitError(f"Rate limit exceeded after {MAX_RETRIES} attempts") from last_exc
        raise ModelAPIError(
            f"API call failed after {MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # 1. Script Generation  (Sonnet — creative)
    # ------------------------------------------------------------------

    async def generate_script(
        self,
        topic: TopicInput,
        channel_settings: ChannelSettings,
    ) -> ScriptOutput:
        """Generate a complete, marked-up documentary script.

        Uses Claude Sonnet 4 for maximum creative quality.  The full Section
        4.3 system prompt is sent with prompt caching enabled so that
        subsequent calls within the same session reuse the cached prefix.

        Parameters
        ----------
        topic:
            The crime topic, target length, optional angle/region/era, and
            rotation index for hook selection.
        channel_settings:
            Channel name, tone, audience, and content rating that shape the
            script's voice.

        Returns
        -------
        ScriptOutput
            The annotated script, word count, timing, hook metadata, open-loop
            descriptions, twist placements, and API call cost.

        Raises
        ------
        ScriptGenerationError
            On any unrecoverable failure (content filter, API error, bad
            response format).
        """
        hook = _select_hook(topic)
        wc_min, wc_max = WORD_COUNT_TARGETS[topic.video_length_minutes]

        # Build the user message with all context
        parts: list[str] = [
            "## Assignment",
            f"Write a {topic.video_length_minutes}-minute true-crime documentary "
            f"script about the following topic.",
            "",
            f"**Topic:** {topic.topic}",
        ]
        if topic.angle:
            parts.append(f"**Angle:** {topic.angle}")
        if topic.region:
            parts.append(f"**Region:** {topic.region}")
        if topic.era:
            parts.append(f"**Era:** {topic.era}")

        parts += [
            "",
            "## Constraints",
            f"- **Hook type to use:** {hook.value} (#{HOOK_ROTATION.index(hook) + 1})",
            f"- **Word count:** {wc_min} – {wc_max} words",
            f"- **Channel:** {channel_settings.channel_name}",
            f"- **Tone:** {channel_settings.tone}",
            f"- **Audience:** {channel_settings.target_audience}",
            f"- **Content rating:** {channel_settings.content_rating}",
        ]

        user_message = "\n".join(parts)

        text, cost = await self._call_claude(
            model=MODEL_SONNET,
            system_prompt=SCRIPT_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=8_192,
            temperature=1.0,
        )

        try:
            data = json.loads(_strip_json_fences(text))
        except json.JSONDecodeError as exc:
            raise ScriptGenerationError(f"Claude returned non-JSON response: {text[:200]}") from exc

        try:
            return ScriptOutput(
                script_text=data["script_text"],
                word_count=data["word_count"],
                estimated_duration_seconds=data["estimated_duration_seconds"],
                hook_type=HookType(data["hook_type"]),
                open_loops=data.get("open_loops", []),
                twist_placements=[TwistPlacement(**tp) for tp in data.get("twist_placements", [])],
                cost=cost,
            )
        except (KeyError, ValueError) as exc:
            raise ScriptGenerationError(f"Unexpected script response structure: {exc}") from exc

    # ------------------------------------------------------------------
    # 2. Scene Breakdown  (Haiku — structured JSON)
    # ------------------------------------------------------------------

    async def generate_scene_breakdown(
        self,
        script: str,
        video_length_minutes: int,
    ) -> SceneBreakdownResult:
        """Break a marked-up script into timed scenes for video assembly.

        Uses Claude Haiku 4.5 for fast, structured JSON output.  The scene
        breakdown includes narration text, image-generation descriptions,
        emotion tags, speed markers, SFX cues, and ad-break flags.

        Parameters
        ----------
        script:
            The full annotated script text (output of ``generate_script``).
        video_length_minutes:
            Target video duration — used by the model to calibrate timing.

        Returns
        -------
        SceneBreakdownResult
            A list of ``SceneBreakdown`` objects with their API call cost.
        """
        user_message = (
            f"Break the following {video_length_minutes}-minute documentary "
            f"script into timed scenes.\n\n"
            f"Target total duration: {video_length_minutes * 60} seconds.\n\n"
            f"---\n\n{script}"
        )

        text, cost = await self._call_claude(
            model=MODEL_HAIKU,
            system_prompt=SCENE_BREAKDOWN_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=8_192,
            temperature=0.0,
        )

        try:
            raw_scenes = json.loads(_strip_json_fences(text))
        except json.JSONDecodeError as exc:
            raise ScriptGenerationError(f"Scene breakdown returned non-JSON: {text[:200]}") from exc

        if not isinstance(raw_scenes, list):
            raise ScriptGenerationError(
                f"Expected JSON array for scenes, got {type(raw_scenes).__name__}"
            )

        scenes = [SceneBreakdown.model_validate(s) for s in raw_scenes]
        return SceneBreakdownResult(scenes=scenes, cost=cost)

    # ------------------------------------------------------------------
    # 3. Image Prompt Generation  (Haiku — structured)
    # ------------------------------------------------------------------

    async def generate_image_prompts(
        self,
        scenes: list[SceneBreakdown],
        channel_brand: BrandSettings,
    ) -> ImagePromptsResult:
        """Generate one image prompt per scene, styled to the channel brand.

        Uses Claude Haiku 4.5.  The channel's ``master_prompt_suffix`` is
        appended to every prompt after generation, and the
        ``negative_prompt`` is passed through for SD-based renderers.

        Parameters
        ----------
        scenes:
            Ordered scene breakdowns from ``generate_scene_breakdown``.
        channel_brand:
            Visual brand settings (prompt suffix, negative prompt, lighting,
            palette, mood).

        Returns
        -------
        ImagePromptsResult
            One ``ImagePrompt`` per scene with cost tracking.
        """
        scene_descriptions = [
            {
                "scene_number": s.scene_number,
                "scene_description": s.scene_description,
                "emotion_tag": s.emotion_tag,
                "narration_speed": s.narration_speed,
            }
            for s in scenes
        ]

        user_message = (
            f"Generate image prompts for the following {len(scenes)} scenes.\n\n"
            f"## Channel Brand\n"
            f"- Lighting: {channel_brand.lighting_style}\n"
            f"- Color palette: {channel_brand.color_palette}\n"
            f"- Mood: {channel_brand.mood}\n"
            f"- Aspect ratio: {channel_brand.aspect_ratio}\n\n"
            f"## Scenes\n{json.dumps(scene_descriptions, indent=2)}"
        )

        text, cost = await self._call_claude(
            model=MODEL_HAIKU,
            system_prompt=IMAGE_PROMPT_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=4_096,
            temperature=0.0,
        )

        try:
            raw_prompts = json.loads(_strip_json_fences(text))
        except json.JSONDecodeError as exc:
            raise ScriptGenerationError(f"Image prompts returned non-JSON: {text[:200]}") from exc

        if not isinstance(raw_prompts, list):
            raise ScriptGenerationError(
                f"Expected JSON array for image prompts, got {type(raw_prompts).__name__}"
            )

        prompts: list[ImagePrompt] = []
        for rp in raw_prompts:
            # Append the channel's master suffix to each prompt
            full_prompt = f"{rp['prompt']}, {channel_brand.master_prompt_suffix}"
            prompts.append(
                ImagePrompt(
                    scene_number=rp["scene_number"],
                    prompt=full_prompt,
                    negative_prompt=channel_brand.negative_prompt,
                    aspect_ratio=channel_brand.aspect_ratio,
                    lighting=rp.get("lighting", channel_brand.lighting_style),
                    mood=rp.get("mood", channel_brand.mood),
                    reference_scene_description=next(
                        (
                            s.scene_description
                            for s in scenes
                            if s.scene_number == rp["scene_number"]
                        ),
                        "",
                    ),
                )
            )

        return ImagePromptsResult(prompts=prompts, cost=cost)

    # ------------------------------------------------------------------
    # 4. Title Generation  (Sonnet — creative)
    # ------------------------------------------------------------------

    async def generate_titles(
        self,
        topic: TopicInput,
        script_summary: str,
    ) -> TitlesResult:
        """Generate 5 title variants, each using a different formula.

        Uses Claude Sonnet 4 for creative ideation.  The rotation index
        determines which 5 of the 6 formulas are used (one is excluded per
        rotation to ensure variety across videos).

        Each title is validated against hard constraints:
        - 50–60 characters
        - 5–9 words
        - 1–2 power words maximum
        - Primary keyword front-loaded

        Titles that fail validation are filtered out and logged.

        Parameters
        ----------
        topic:
            Original topic input (used for keyword context and rotation).
        script_summary:
            A short summary of the generated script (2-3 sentences).

        Returns
        -------
        TitlesResult
            Up to 5 ``TitleVariant`` objects ranked by estimated CTR, with
            cost tracking.
        """
        formulas = _select_title_formulas(topic.rotation_index, count=5)
        formula_instructions = "\n".join(
            f"  {i + 1}. Use the **{f.value}** formula" for i, f in enumerate(formulas)
        )

        user_message = (
            f"## Topic\n{topic.topic}\n\n"
            f"## Script Summary\n{script_summary}\n\n"
            f"## Instructions\n"
            f"Generate exactly 5 title variants.  Each must use a different "
            f"formula as assigned below:\n{formula_instructions}\n\n"
            f"Rank them 1 (best) to 5 by estimated CTR.  Validate every title "
            f"against the hard constraints before including it."
        )

        text, cost = await self._call_claude(
            model=MODEL_SONNET,
            system_prompt=TITLE_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=2_048,
            temperature=1.0,
        )

        try:
            raw_titles = json.loads(_strip_json_fences(text))
        except json.JSONDecodeError as exc:
            raise ScriptGenerationError(
                f"Title generation returned non-JSON: {text[:200]}"
            ) from exc

        if not isinstance(raw_titles, list):
            raise ScriptGenerationError(
                f"Expected JSON array for titles, got {type(raw_titles).__name__}"
            )

        variants: list[TitleVariant] = []
        for rt in raw_titles:
            title_text: str = rt["title"]
            char_count = len(title_text)
            word_count = len(title_text.split())
            power_words: list[str] = rt.get("power_words", [])

            # Validate hard constraints
            if not (50 <= char_count <= 60):
                await logger.awarning(
                    "title_char_count_violation",
                    title=title_text,
                    char_count=char_count,
                )
                continue
            if not (5 <= word_count <= 9):
                await logger.awarning(
                    "title_word_count_violation",
                    title=title_text,
                    word_count=word_count,
                )
                continue
            if len(power_words) > 2:
                await logger.awarning(
                    "title_power_word_violation",
                    title=title_text,
                    power_words=power_words,
                )
                continue

            variants.append(
                TitleVariant(
                    title=title_text,
                    formula=TitleFormula(rt["formula"]),
                    word_count=word_count,
                    char_count=char_count,
                    power_words=power_words,
                    estimated_ctr_rank=rt.get("estimated_ctr_rank", len(variants) + 1),
                )
            )

        # Sort by estimated CTR rank
        variants.sort(key=lambda v: v.estimated_ctr_rank)

        if not variants:
            raise ScriptGenerationError("All generated titles failed validation constraints")

        return TitlesResult(variants=variants, cost=cost)

    # ------------------------------------------------------------------
    # 5. Description Generation  (Haiku — structured)
    # ------------------------------------------------------------------

    async def generate_description(
        self,
        title: str,
        script_summary: str,
        affiliate_links: dict[str, str] | None = None,
    ) -> DescriptionResult:
        """Generate a YouTube video description optimised for SEO.

        Uses Claude Haiku 4.5 for fast, structured output.  The description
        follows a fixed structure: hook line, synopsis, timestamps
        placeholder, affiliate links, channel boilerplate, and tags.

        Parameters
        ----------
        title:
            The chosen video title.
        script_summary:
            A 2-3 sentence summary of the video's content.
        affiliate_links:
            Optional mapping of ``{label: url}`` to embed in the description.

        Returns
        -------
        DescriptionResult
            The raw description text and API call cost.
        """
        links_section = ""
        if affiliate_links:
            links_section = "\n## Affiliate Links to Include\n"
            links_section += "\n".join(
                f"- {label}: {url}" for label, url in affiliate_links.items()
            )

        user_message = (
            f"## Video Title\n{title}\n\n## Script Summary\n{script_summary}\n{links_section}"
        )

        text, cost = await self._call_claude(
            model=MODEL_HAIKU,
            system_prompt=DESCRIPTION_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=2_048,
            temperature=0.2,
        )

        description = text.strip()
        return DescriptionResult(description=description, cost=cost)

    # ------------------------------------------------------------------
    # 6. Batch API  (50 % cost reduction for non-urgent generation)
    # ------------------------------------------------------------------

    async def generate_script_batch(
        self,
        requests: list[dict[str, Any]],
    ) -> str:
        """Submit multiple script generation requests as a single batch.

        Uses the Anthropic Message Batches API (``POST /v1/messages/batches``)
        for a 50 % cost reduction.  Batches complete within 24 hours; the
        caller should poll with ``poll_batch_status()`` and then retrieve
        results with ``retrieve_batch_results()``.

        Parameters
        ----------
        requests:
            A list of request dicts, each containing:
            - ``custom_id``: unique string identifier for the request
            - ``topic``: TopicInput-like dict
            - ``channel_settings``: ChannelSettings-like dict

        Returns
        -------
        str
            The batch ID (``batch_xxx``) to use for polling and retrieval.
        """
        batch_requests: list[anthropic.types.messages.batch_create_params.Request] = []

        for req in requests:
            custom_id = req.get("custom_id", str(uuid.uuid4()))
            topic_data = req["topic"]
            channel_data = req["channel_settings"]
            hook_type = topic_data.get("hook_type")
            rotation_index = topic_data.get("rotation_index", 0)

            # Determine hook
            if hook_type:
                hook = HookType(hook_type)
            else:
                hook = HOOK_ROTATION[rotation_index % len(HOOK_ROTATION)]

            video_length = topic_data.get("video_length_minutes", 15)
            wc_min, wc_max = WORD_COUNT_TARGETS[video_length]

            parts: list[str] = [
                "## Assignment",
                f"Write a {video_length}-minute true-crime documentary "
                f"script about the following topic.",
                "",
                f"**Topic:** {topic_data['topic']}",
            ]
            if topic_data.get("angle"):
                parts.append(f"**Angle:** {topic_data['angle']}")
            if topic_data.get("region"):
                parts.append(f"**Region:** {topic_data['region']}")
            if topic_data.get("era"):
                parts.append(f"**Era:** {topic_data['era']}")

            parts += [
                "",
                "## Constraints",
                f"- **Hook type to use:** {hook.value} (#{HOOK_ROTATION.index(hook) + 1})",
                f"- **Word count:** {wc_min} – {wc_max} words",
                f"- **Channel:** {channel_data.get('channel_name', '')}",
                f"- **Tone:** {channel_data.get('tone', 'dark, measured, cinematic')}",
                f"- **Audience:** {channel_data.get('target_audience', 'true crime enthusiasts, 25-45')}",
                f"- **Content rating:** {channel_data.get('content_rating', 'TV-14')}",
            ]

            batch_requests.append(
                {
                    "custom_id": custom_id,
                    "params": {
                        "model": MODEL_SONNET,
                        "max_tokens": 8_192,
                        "temperature": 1.0,
                        "system": [
                            {
                                "type": "text",
                                "text": SCRIPT_SYSTEM_PROMPT,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                        "messages": [{"role": "user", "content": "\n".join(parts)}],
                    },
                }
            )

        batch = await self._client.messages.batches.create(requests=batch_requests)

        await logger.ainfo(
            "batch_submitted",
            batch_id=batch.id,
            request_count=len(batch_requests),
        )
        return batch.id

    async def poll_batch_status(self, batch_id: str) -> dict[str, Any]:
        """Poll the status of a message batch.

        Parameters
        ----------
        batch_id:
            The batch ID returned by ``generate_script_batch()``.

        Returns
        -------
        dict
            Contains ``status`` (``in_progress``, ``ended``, ``canceling``,
            ``canceled``, ``expired``), ``request_counts`` with totals, and
            ``ended_at`` if complete.
        """
        batch = await self._client.messages.batches.retrieve(batch_id)

        result = {
            "batch_id": batch.id,
            "status": batch.processing_status,
            "request_counts": {
                "processing": batch.request_counts.processing,
                "succeeded": batch.request_counts.succeeded,
                "errored": batch.request_counts.errored,
                "canceled": batch.request_counts.canceled,
                "expired": batch.request_counts.expired,
            },
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "ended_at": batch.ended_at.isoformat() if batch.ended_at else None,
        }

        await logger.ainfo("batch_status_polled", **result)
        return result

    async def retrieve_batch_results(
        self,
        batch_id: str,
    ) -> list[dict[str, Any]]:
        """Retrieve results from a completed batch.

        Streams the JSONL results file and parses each line into a
        ``ScriptOutput`` (for successes) or an error dict.

        Parameters
        ----------
        batch_id:
            The batch ID of a completed batch.

        Returns
        -------
        list[dict]
            Each dict contains ``custom_id``, ``status`` (``succeeded`` or
            ``errored``), and either ``result`` (a ``ScriptOutput.model_dump()``)
            or ``error``.
        """
        results: list[dict[str, Any]] = []

        async for raw_result in await self._client.messages.batches.results(batch_id):
            custom_id = raw_result.custom_id
            result_type = raw_result.result.type

            if result_type == "succeeded" and hasattr(raw_result.result, "message"):
                message = raw_result.result.message
                text = "".join(
                    block.text for block in message.content if hasattr(block, "text")
                )
                usage = message.usage

                input_tokens = usage.input_tokens
                output_tokens = usage.output_tokens
                cached_input = getattr(usage, "cache_creation_input_tokens", 0) + getattr(
                    usage, "cache_read_input_tokens", 0
                )
                cost_usd = _calculate_cost(
                    MODEL_SONNET,
                    input_tokens,
                    output_tokens,
                    cached_input,
                    is_batch=True,
                )

                cost = APICallCost(
                    model=MODEL_SONNET,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    cached_input_tokens=cached_input,
                )

                try:
                    data = json.loads(_strip_json_fences(text))
                    script_output = ScriptOutput(
                        script_text=data["script_text"],
                        word_count=data["word_count"],
                        estimated_duration_seconds=data["estimated_duration_seconds"],
                        hook_type=HookType(data["hook_type"]),
                        open_loops=data.get("open_loops", []),
                        twist_placements=[
                            TwistPlacement(**tp) for tp in data.get("twist_placements", [])
                        ],
                        cost=cost,
                    )
                    results.append(
                        {
                            "custom_id": custom_id,
                            "status": "succeeded",
                            "result": script_output.model_dump(),
                        }
                    )
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    results.append(
                        {
                            "custom_id": custom_id,
                            "status": "errored",
                            "error": f"Parse error: {exc}",
                            "raw_text": text[:500],
                            "cost": cost.model_dump(),
                        }
                    )
            else:
                # errored, canceled, or expired
                error_info = getattr(raw_result.result, "error", None)
                results.append(
                    {
                        "custom_id": custom_id,
                        "status": result_type,
                        "error": str(error_info)
                        if error_info
                        else f"Batch result type: {result_type}",
                    }
                )

        await logger.ainfo(
            "batch_results_retrieved",
            batch_id=batch_id,
            total=len(results),
            succeeded=sum(1 for r in results if r["status"] == "succeeded"),
            errored=sum(1 for r in results if r["status"] != "succeeded"),
        )
        return results
