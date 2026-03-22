"""Localization pipeline — produces localized versions of completed English videos.

Same visuals, translated script, new voiceover. Near-zero marginal cost per
localization (~$0.46 vs $0.60-1.00 for the original English video).

Pipeline stages:
    1. Translate script (Claude Sonnet — creative, preserves narrative voice)
    2. Generate localized voiceover (Fish Audio S2 — 80+ languages)
    3. Generate localized captions (Groq Whisper — auto-detects language)
    4. Translate title + description (Claude Haiku — structured)
    5. Re-render thumbnail text overlay (Pillow — local, ~$0)
    6. Assemble localized video (Remotion Lambda — same images, new audio)
    7. Upload to target language channel
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import structlog

from src.models.localization import (
    ALL_SUPPORTED_LANGUAGES,
    PRIORITY_LANGUAGES,
    CostEstimate,
    LanguageConfig,
    LocalizationConfigRow,
    LocalizationResult,
    TranslatedMetadata,
    TranslatedScript,
)
from src.services.script_generator import MODEL_HAIKU, MODEL_SONNET, PRICING

if TYPE_CHECKING:
    from uuid import UUID

    import httpx
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings
    from src.services.caption_generator import CaptionGenerator
    from src.services.script_generator import ScriptGenerator
    from src.services.video_assembler import VideoAssembler
    from src.services.voiceover_generator import VoiceoverGenerator

logger = structlog.get_logger()

# psycopg pool is configured with dict_row at runtime, but mypy infers
# AsyncConnection[tuple[Any, ...]].  This alias + cast keeps row access safe.
Row = dict[str, Any]

_ONE_MILLION = Decimal("1_000_000")

# Fish Audio cost per character (Plus plan)
_FISH_COST_PER_CHAR = Decimal("0.0000647")

# Groq Whisper cost per minute
_GROQ_COST_PER_MINUTE = Decimal("0.00067")

# Remotion Lambda cost per render
_REMOTION_COST_PER_RENDER = Decimal("0.11")

# Average words-per-minute for narration pacing estimate
_NARRATION_WPM = 150

# ---------------------------------------------------------------------------
# SQL queries (localization-specific)
# ---------------------------------------------------------------------------

GET_SOURCE_VIDEO: str = """
SELECT
    v.id, v.channel_id, v.title, v.description, v.tags, v.topic,
    v.status, v.script_word_count, v.video_length_seconds,
    v.youtube_video_id, v.language,
    c.name AS channel_name
FROM videos v
JOIN channels c ON c.id = v.channel_id
WHERE v.id = %(video_id)s;
"""

GET_SOURCE_SCRIPT: str = """
SELECT result->>'script_text' AS script_text,
       result->>'word_count' AS word_count
FROM pipeline_jobs
WHERE video_id = %(video_id)s
  AND stage = 'script_generation'
  AND status = 'completed'
ORDER BY completed_at DESC
LIMIT 1;
"""

GET_SOURCE_IMAGES: str = """
SELECT result->>'image_storage_paths' AS image_paths
FROM pipeline_jobs
WHERE video_id = %(video_id)s
  AND stage = 'image_processing'
  AND status = 'completed'
ORDER BY completed_at DESC
LIMIT 1;
"""

GET_SOURCE_THUMBNAIL_BG: str = """
SELECT result->>'background_r2_key' AS background_key
FROM pipeline_jobs
WHERE video_id = %(video_id)s
  AND stage = 'thumbnail_generation'
  AND status = 'completed'
ORDER BY completed_at DESC
LIMIT 1;
"""

GET_LOCALIZATION_CONFIG: str = """
SELECT source_channel_id, target_channel_id, target_language,
       voice_id, font_family, auto_localize
FROM localization_config
WHERE source_channel_id = %(source_channel_id)s
  AND target_language = %(target_language)s;
"""

INSERT_LOCALIZED_VIDEO: str = """
INSERT INTO videos
    (channel_id, title, description, tags, topic, status, parent_video_id, language)
VALUES
    (%(channel_id)s, %(title)s, %(description)s, %(tags)s, %(topic)s,
     'pending', %(parent_video_id)s, %(language)s)
RETURNING id;
"""

GET_AUTO_LOCALIZE_CONFIGS: str = """
SELECT source_channel_id, target_channel_id, target_language,
       voice_id, font_family, auto_localize
FROM localization_config
WHERE source_channel_id = %(source_channel_id)s
  AND auto_localize = true;
"""

# ---------------------------------------------------------------------------
# Translation prompts
# ---------------------------------------------------------------------------

SCRIPT_TRANSLATION_SYSTEM: str = """You are a professional translator specializing in crime \
documentary narration. Translate the following script from {source} to {target}. Preserve:
- All timing markers [HOOK], [AD_BREAK], [SCENE:], [SFX:], [SILENCE:], [PROMISE], \
[STAKES], [PATTERN_INTERRUPT], [CTA_LIGHT], [CTA_ENGAGE], [CTA_END]
- All emotion tags in brackets like [calm, measured tone]
- Narrative tension and pacing
- Dark humor and editorial voice
- Cultural references should be adapted, not literally translated
- Legal terminology should use the target country's equivalents
Do NOT translate the marker names themselves — keep them in English.
Adjust word count for natural {target} narration pacing — target approximately \
{word_adjustment:.0%} of the English word count.
Return ONLY the translated script text. Do not add commentary."""

METADATA_TRANSLATION_SYSTEM: str = """You are a YouTube SEO specialist for true-crime content.
Translate the following video metadata from English to {target}.
Rules:
- Title: adapt for {target} search patterns (max 100 characters)
- Description: translate naturally, keep affiliate links unchanged (Geniuslink auto-localizes), \
  keep English case names in parentheses after the translated name
- Tags: translate existing + add 3-5 {target}-language crime keywords
Return ONLY valid JSON: {{"title": "...", "description": "...", "tags": ["..."]}}"""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class Localizer:
    """Produces localized versions of completed English videos."""

    def __init__(
        self,
        settings: Settings,
        script_generator: ScriptGenerator,
        voiceover_generator: VoiceoverGenerator,
        caption_generator: CaptionGenerator,
        video_assembler: VideoAssembler,
        http_client: httpx.AsyncClient,
        db_pool: AsyncConnectionPool,
    ) -> None:
        self._settings = settings
        self._script_gen = script_generator
        self._voiceover_gen = voiceover_generator
        self._caption_gen = caption_generator
        self._assembler = video_assembler
        self._http = http_client
        self._db_pool = db_pool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def localize_video(
        self,
        source_video_id: UUID,
        target_language: str,
        target_channel_id: UUID,
    ) -> LocalizationResult:
        """Full localization pipeline for one language.

        Near-zero marginal cost per localization:
        - Script translation: ~$0.02 (Sonnet creative)
        - Voiceover: ~$0.30 (Fish Audio, same as English)
        - Captions: ~$0.013 (Groq Whisper)
        - Video assembly: ~$0.11 (Remotion Lambda)
        - Thumbnail text: ~$0.00 (Pillow, local)
        - Total: ~$0.46/localized video
        """
        if target_language not in ALL_SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {target_language}")

        log = logger.bind(
            source_video_id=str(source_video_id),
            target_language=target_language,
            target_channel_id=str(target_channel_id),
        )
        log.info("localization.start")

        lang_config = self._get_language_config(target_language)

        # Fetch source data
        source = await self._get_source_data(source_video_id)
        source_script = source["script_text"]
        source_title = source["title"]
        source_description = source["description"] or ""
        source_tags = source["tags"] or []

        # Fetch voice_id from localization_config or use default
        loc_config = await self._get_loc_config(source["channel_id"], target_language)
        voice_id = loc_config.voice_id if loc_config else ""
        if not voice_id:
            raise ValueError(
                f"No voice_id configured for language '{target_language}' "
                f"on channel {source['channel_id']}"
            )

        _font_family = (  # noqa: F841 — used by subtitle renderer (upcoming)
            loc_config.font_family
            if loc_config and loc_config.font_family
            else lang_config.font_family
        )

        # ---- Step 1: Translate script ----
        translated_script = await self.translate_script(source_script, "en", target_language)
        log.info(
            "localization.script_translated",
            source_words=translated_script.source_word_count,
            translated_words=translated_script.translated_word_count,
            ratio=round(translated_script.word_count_ratio, 3),
        )

        # ---- Step 2: Generate localized voiceover ----
        voiceover_result = await self._voiceover_gen.generate_voiceover(
            script_text=translated_script.translated_text,
            voice_id=voice_id,
        )
        log.info(
            "localization.voiceover_generated",
            duration=voiceover_result.duration_seconds,
            cost=str(voiceover_result.cost_usd),
        )

        # ---- Step 3: Generate localized captions ----
        caption_result = await self._caption_gen.generate_srt(
            audio_path=voiceover_result.file_path,
            language=target_language,
        )
        log.info(
            "localization.captions_generated",
            words=caption_result.total_words,
            cost=str(caption_result.cost_usd),
        )

        # ---- Step 4: Translate title + description ----
        translated_meta = await self.translate_metadata(
            title=source_title,
            description=source_description,
            tags=source_tags if isinstance(source_tags, list) else json.loads(source_tags),
            target_lang=target_language,
        )
        log.info("localization.metadata_translated")

        # ---- Step 5: Thumbnail — reuse background, re-render text ----
        # The thumbnail background image is the same; only text changes.
        # This is handled downstream when the localized video enters
        # the thumbnail_generation stage with the translated title and
        # language-specific font.

        # ---- Step 6: Create DB record for localized video ----
        topic = source.get("topic", {})
        if isinstance(topic, str):
            topic = json.loads(topic)
        topic["localized_from"] = str(source_video_id)
        topic["language"] = target_language

        localized_video_id = await self._create_localized_record(
            channel_id=target_channel_id,
            title=translated_meta.title,
            description=translated_meta.description,
            tags=translated_meta.tags,
            topic=topic,
            parent_video_id=source_video_id,
            language=target_language,
        )

        # ---- Step 7: Assemble localized video ----
        # Reuse scene images from source video, swap audio + captions
        assembly_result = await self._assemble_localized(
            localized_video_id=localized_video_id,
            target_channel_id=target_channel_id,
            source_video_id=source_video_id,
            voiceover_path=voiceover_result.file_path,
            caption_result=caption_result,
        )

        # Aggregate costs
        translation_cost = translated_script.cost + translated_meta.cost
        voiceover_cost = voiceover_result.cost_usd
        caption_cost = caption_result.cost_usd
        assembly_cost = Decimal(str(assembly_result.cost_usd))
        total_cost = translation_cost + voiceover_cost + caption_cost + assembly_cost

        result = LocalizationResult(
            source_video_id=source_video_id,
            localized_video_id=localized_video_id,
            source_channel_id=source["channel_id"],
            target_channel_id=target_channel_id,
            target_language=target_language,
            title=translated_meta.title,
            translated_word_count=translated_script.translated_word_count,
            voiceover_duration_seconds=voiceover_result.duration_seconds,
            file_path=assembly_result.file_path,
            file_url=assembly_result.file_url,
            file_size_bytes=assembly_result.file_size_bytes,
            translation_cost=translation_cost,
            voiceover_cost=voiceover_cost,
            caption_cost=caption_cost,
            assembly_cost=assembly_cost,
            total_cost_usd=total_cost,
        )

        log.info(
            "localization.complete",
            localized_video_id=str(localized_video_id),
            total_cost=str(total_cost),
            duration=voiceover_result.duration_seconds,
        )
        return result

    # ------------------------------------------------------------------
    # Step 1: Creative script translation
    # ------------------------------------------------------------------

    async def translate_script(
        self,
        script: str,
        source_lang: str,
        target_lang: str,
    ) -> TranslatedScript:
        """Translate script via Claude Sonnet (creative task).

        Preserves ALL timing markers, emotion tags, and narrative voice.
        Adjusts word count for target language pacing.
        """
        lang_config = self._get_language_config(target_lang)
        source_name = self._get_language_config(source_lang).name
        target_name = lang_config.name

        system_prompt = SCRIPT_TRANSLATION_SYSTEM.format(
            source=source_name,
            target=target_name,
            word_adjustment=lang_config.word_count_adjustment,
        )

        text, cost = await self._script_gen._call_claude(
            model=MODEL_SONNET,
            system_prompt=system_prompt,
            user_message=script,
            max_tokens=8_192,
            temperature=0.7,
        )

        source_word_count = len(script.split())
        translated_word_count = len(text.split())
        ratio = translated_word_count / max(source_word_count, 1)

        # Verify markers are preserved
        markers_ok = _verify_markers_preserved(script, text)
        if not markers_ok:
            logger.warning(
                "localization.markers_missing",
                source_lang=source_lang,
                target_lang=target_lang,
            )

        return TranslatedScript(
            source_language=source_lang,
            target_language=target_lang,
            translated_text=text,
            source_word_count=source_word_count,
            translated_word_count=translated_word_count,
            word_count_ratio=round(ratio, 4),
            markers_preserved=markers_ok,
            cost=cost.cost_usd,
            model=cost.model,
        )

    # ------------------------------------------------------------------
    # Step 4: Metadata translation
    # ------------------------------------------------------------------

    async def translate_metadata(
        self,
        title: str,
        description: str,
        tags: list[str],
        target_lang: str,
    ) -> TranslatedMetadata:
        """Translate video metadata for YouTube SEO via Claude Haiku."""
        lang_config = self._get_language_config(target_lang)

        system_prompt = METADATA_TRANSLATION_SYSTEM.format(
            target=lang_config.name,
        )

        user_message = json.dumps(
            {"title": title, "description": description, "tags": tags},
            ensure_ascii=False,
        )

        text, cost = await self._script_gen._call_claude(
            model=MODEL_HAIKU,
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=4_096,
            temperature=0.3,
        )

        parsed = json.loads(text)

        return TranslatedMetadata(
            title=parsed["title"][:100],
            description=parsed["description"],
            tags=parsed.get("tags", tags),
            target_language=target_lang,
            cost=cost.cost_usd,
        )

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    async def get_localization_cost_estimate(
        self,
        source_video_id: UUID,
        target_language: str,
    ) -> CostEstimate:
        """Estimate localization cost before committing."""
        source = await self._get_source_data(source_video_id)
        source_script = source["script_text"]
        source_word_count = len(source_script.split())

        lang_config = self._get_language_config(target_language)
        estimated_words = int(source_word_count * lang_config.word_count_adjustment)

        # Rough char estimate: ~5 chars/word average
        estimated_chars = estimated_words * 5
        estimated_duration_min = estimated_words / _NARRATION_WPM

        # Translation cost (Sonnet for script + Haiku for metadata)
        # Script: ~2000 words input → ~800 input tokens, ~1000 output tokens
        input_tokens_script = Decimal(source_word_count) * Decimal("0.75")  # ~0.75 tokens/word
        output_tokens_script = Decimal(estimated_words) * Decimal("0.75")
        translation_cost = (
            input_tokens_script * PRICING[MODEL_SONNET]["input"]
            + output_tokens_script * PRICING[MODEL_SONNET]["output"]
        ) / _ONE_MILLION
        # Add metadata translation (Haiku — small)
        translation_cost += Decimal("0.002")

        # Voiceover cost (Fish Audio)
        voiceover_cost = Decimal(estimated_chars) * _FISH_COST_PER_CHAR

        # Caption cost (Groq Whisper)
        caption_cost = Decimal(str(estimated_duration_min)) * _GROQ_COST_PER_MINUTE

        # Assembly cost (Remotion Lambda)
        assembly_cost = _REMOTION_COST_PER_RENDER

        total = translation_cost + voiceover_cost + caption_cost + assembly_cost

        return CostEstimate(
            source_video_id=source_video_id,
            target_language=target_language,
            source_word_count=source_word_count,
            estimated_translated_words=estimated_words,
            estimated_voiceover_chars=estimated_chars,
            estimated_voiceover_duration_minutes=round(float(estimated_duration_min), 2),
            translation_cost=translation_cost.quantize(Decimal("0.001")),
            voiceover_cost=voiceover_cost.quantize(Decimal("0.001")),
            caption_cost=caption_cost.quantize(Decimal("0.00001")),
            assembly_cost=assembly_cost,
            thumbnail_cost=Decimal("0"),
            total_estimated_usd=total.quantize(Decimal("0.001")),
        )

    # ------------------------------------------------------------------
    # Auto-localize trigger (called after English publish)
    # ------------------------------------------------------------------

    async def get_auto_localize_targets(
        self,
        source_channel_id: UUID,
    ) -> list[LocalizationConfigRow]:
        """Return all auto-localize configs for a channel."""
        async with self._db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                GET_AUTO_LOCALIZE_CONFIGS,
                {"source_channel_id": str(source_channel_id)},
            )
            rows = await cur.fetchall()
            return [LocalizationConfigRow.from_row(cast("Row", r)) for r in rows]

    # ------------------------------------------------------------------
    # Language config
    # ------------------------------------------------------------------

    def _get_language_config(self, language: str) -> LanguageConfig:
        """Per-language configuration with pacing adjustments and fonts."""
        if language in PRIORITY_LANGUAGES:
            info: dict[str, Any] = PRIORITY_LANGUAGES[language]
            return LanguageConfig(
                code=language,
                name=str(info["name"]),
                word_count_adjustment=float(info["word_adjustment"]),
                font_family=str(info["font"]),
            )

        # Defaults for non-priority languages
        extended: dict[str, tuple[str, float]] = {
            "de": ("German", 1.10),
            "it": ("Italian", 1.15),
            "ja": ("Japanese", 0.70),
            "ko": ("Korean", 0.80),
            "zh": ("Chinese", 0.65),
            "ar": ("Arabic", 0.95),
            "ru": ("Russian", 1.05),
            "tr": ("Turkish", 1.10),
            "pl": ("Polish", 1.08),
            "nl": ("Dutch", 1.05),
            "id": ("Indonesian", 1.10),
            "th": ("Thai", 0.85),
            "vi": ("Vietnamese", 1.00),
            "en": ("English", 1.00),
        }

        if language in extended:
            name, adj = extended[language]
            return LanguageConfig(
                code=language,
                name=name,
                word_count_adjustment=adj,
            )

        # Unknown language — use neutral defaults
        return LanguageConfig(
            code=language,
            name=language,
            word_count_adjustment=1.0,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_source_data(self, video_id: UUID) -> dict[str, Any]:
        """Fetch source video metadata and script."""
        async with self._db_pool.connection() as conn, conn.cursor() as cur:
            # Video metadata
            await cur.execute(GET_SOURCE_VIDEO, {"video_id": str(video_id)})
            video = cast("Row | None", await cur.fetchone())
            if not video:
                raise ValueError(f"Source video {video_id} not found")
            if video["status"] != "published":
                raise ValueError(
                    f"Source video {video_id} is not published (status: {video['status']})"
                )

            # Script text from completed pipeline job
            await cur.execute(GET_SOURCE_SCRIPT, {"video_id": str(video_id)})
            script_row = cast("Row | None", await cur.fetchone())
            if not script_row or not script_row["script_text"]:
                raise ValueError(f"No completed script found for video {video_id}")

            return {
                **dict(video),
                "script_text": script_row["script_text"],
                "source_word_count": int(script_row.get("word_count", 0) or 0),
            }

    async def _get_loc_config(
        self, source_channel_id: UUID, target_language: str
    ) -> LocalizationConfigRow | None:
        """Fetch localization config for a channel + language pair."""
        async with self._db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                GET_LOCALIZATION_CONFIG,
                {
                    "source_channel_id": str(source_channel_id),
                    "target_language": target_language,
                },
            )
            row = cast("Row | None", await cur.fetchone())
            return LocalizationConfigRow.from_row(row) if row else None

    async def _create_localized_record(
        self,
        channel_id: UUID,
        title: str,
        description: str,
        tags: list[str],
        topic: dict[str, Any],
        parent_video_id: UUID,
        language: str,
    ) -> UUID:
        """Insert a new video record for the localized version."""
        async with self._db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                INSERT_LOCALIZED_VIDEO,
                {
                    "channel_id": str(channel_id),
                    "title": title,
                    "description": description,
                    "tags": json.dumps(tags),
                    "topic": json.dumps(topic),
                    "parent_video_id": str(parent_video_id),
                    "language": language,
                },
            )
            row = cast("Row | None", await cur.fetchone())
            await conn.commit()
            assert row is not None
            return row["id"]  # type: ignore[no-any-return]

    async def _assemble_localized(
        self,
        localized_video_id: UUID,
        target_channel_id: UUID,
        source_video_id: UUID,
        voiceover_path: str,
        caption_result: Any,
    ) -> Any:
        """Assemble localized video reusing source scene images.

        Fetches scene image paths from the source video's completed
        image_processing job, then feeds them into the assembler with
        the new voiceover and caption data.
        """
        from src.models.assembly import AssemblyInput, SceneForAssembly

        # Get scene images from source video
        async with self._db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(GET_SOURCE_IMAGES, {"video_id": str(source_video_id)})
            img_row = cast("Row | None", await cur.fetchone())

        image_paths: list[str] = []
        if img_row and img_row.get("image_paths"):
            raw = img_row["image_paths"]
            image_paths = json.loads(raw) if isinstance(raw, str) else raw

        # Get scene timing from source audio processing result
        async with self._db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """SELECT result FROM pipeline_jobs
                       WHERE video_id = %(video_id)s
                         AND stage = 'audio_processing'
                         AND status = 'completed'
                       ORDER BY completed_at DESC LIMIT 1""",
                {"video_id": str(source_video_id)},
            )
            _audio_row = await cur.fetchone()  # noqa: F841 — metadata reserved for future audio mixing

        # Build scenes for assembly — reuse image paths with timing
        scenes: list[SceneForAssembly] = []
        if image_paths:
            # Distribute images evenly across the voiceover duration

            vo_info = await self._get_audio_info(voiceover_path)
            duration = vo_info.duration_seconds if hasattr(vo_info, "duration_seconds") else 600
            per_scene = duration / max(len(image_paths), 1)

            for i, img_path in enumerate(image_paths):
                scenes.append(
                    SceneForAssembly(
                        scene_number=i + 1,
                        image_storage_path=img_path,
                        start_seconds=round(i * per_scene, 2),
                        end_seconds=round((i + 1) * per_scene, 2),
                        narration_text="",
                    )
                )

        assembly_input = AssemblyInput(
            video_id=localized_video_id,
            channel_id=target_channel_id,
            title="",
            scenes=scenes,
            audio_path=voiceover_path,
            caption_words=caption_result.caption_words,
            audio_duration_seconds=vo_info.duration_seconds,
        )

        return await self._assembler.render(assembly_input)

    async def _get_audio_info(self, path: str) -> Any:
        """Get audio info, importing AudioProcessor lazily."""
        from src.services.audio_processor import AudioProcessor

        proc = AudioProcessor(self._settings, self._http)
        return await proc.get_audio_info(path)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

# Timing markers that must survive translation
_REQUIRED_MARKERS = {
    "[HOOK]",
    "[AD_BREAK]",
    "[CTA_LIGHT]",
    "[CTA_ENGAGE]",
    "[CTA_END]",
    "[PROMISE]",
    "[STAKES]",
    "[PATTERN_INTERRUPT]",
}


def _verify_markers_preserved(source: str, translated: str) -> bool:
    """Check that all timing markers from the source exist in the translation."""
    for marker in _REQUIRED_MARKERS:
        if marker in source and marker not in translated:
            return False

    # Also check [SCENE:...] markers (variable content)
    source_scene_count = len(re.findall(r"\[SCENE:", source))
    translated_scene_count = len(re.findall(r"\[SCENE:", translated))
    if source_scene_count > 0 and translated_scene_count == 0:
        return False

    # Check [SILENCE:...] markers
    source_silence_count = len(re.findall(r"\[SILENCE:", source))
    translated_silence_count = len(re.findall(r"\[SILENCE:", translated))
    return not (source_silence_count > 0 and translated_silence_count == 0)
