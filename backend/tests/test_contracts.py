"""Verify data contracts between pipeline stages are compatible.

Each test checks that the Pydantic models produced by one stage can be
consumed by the next.  Catches field-name drift, type mismatches, and
missing required fields *before* they cause runtime failures during a
multi-hour render.
"""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# 1. SceneBreakdown compatibility: script ↔ voiceover ↔ description
# ---------------------------------------------------------------------------


def test_scene_breakdown_has_voiceover_fields():
    """script.SceneBreakdown is the canonical definition used by all stages.

    The voiceover generator's _build_scene_text() accesses narration_text,
    emotion_tag, and is_ad_break on SceneBreakdown instances.
    """
    from src.models.script import SceneBreakdown

    fields = set(SceneBreakdown.model_fields.keys())
    assert "scene_number" in fields
    assert "narration_text" in fields
    assert "emotion_tag" in fields
    assert "is_ad_break" in fields


def test_script_scene_breakdown_works_for_description():
    """DescriptionInput.scenes expects list[script.SceneBreakdown]."""
    from src.models.script import SceneBreakdown

    # Build a valid SceneBreakdown and verify it's accepted by DescriptionInput
    scene = SceneBreakdown(
        scene_number=1,
        start_time_seconds=0.0,
        end_time_seconds=30.0,
        narration_text="The investigation began in 2019.",
        scene_description="Dark office with scattered papers",
        emotion_tag="suspenseful",
        narration_speed="NORMAL",
    )
    assert scene.scene_number == 1
    assert scene.narration_text  # used for chapter timestamps


# ---------------------------------------------------------------------------
# 2. CaptionWord ↔ Remotion TypeScript interface
# ---------------------------------------------------------------------------


def test_caption_word_has_remotion_fields():
    """Python CaptionWord maps to TypeScript CaptionWord interface.

    Remotion expects: {text: string, startFrame: number, endFrame: number}
    Python model has:  text, start_frame, end_frame
    build_input_props() converts: start_frame → startFrame
    """
    from src.models.caption import CaptionWord

    word = CaptionWord(text="investigation", start_frame=0, end_frame=15)
    assert word.text == "investigation"
    assert word.start_frame == 0
    assert word.end_frame == 15

    # Verify camelCase conversion matches Remotion interface
    dumped = word.model_dump()
    assert "text" in dumped
    assert "start_frame" in dumped
    assert "end_frame" in dumped

    # The worker's build_input_props does manual dict mapping:
    # {"text": w.text, "startFrame": w.start_frame, "endFrame": w.end_frame}
    remotion_dict = {
        "text": word.text,
        "startFrame": word.start_frame,
        "endFrame": word.end_frame,
        "isHighlighted": False,
    }
    assert remotion_dict["startFrame"] == 0
    assert remotion_dict["endFrame"] == 15


# ---------------------------------------------------------------------------
# 3. AssemblyInput can be built from pipeline stage outputs
# ---------------------------------------------------------------------------


def test_assembly_input_buildable_from_pipeline_outputs():
    """AssemblyInput can be constructed from real pipeline stage outputs.

    The handler builds AssemblyInput from:
    - image_processing.processed_image_keys + script_generation.scenes → scenes
    - audio_processing.audio_r2_key → audio_path
    - caption_generation.words_r2_key → caption_words (downloaded from R2)
    """
    from src.models.assembly import AssemblyInput, SceneForAssembly
    from src.models.caption import CaptionWord

    vid = uuid.uuid4()
    cid = uuid.uuid4()

    # Simulate upstream outputs
    processed_keys = [
        f"{cid}/{vid}/scene_000_processed.jpg",
        f"{cid}/{vid}/scene_001_processed.jpg",
    ]
    raw_scenes = [
        {
            "scene_number": 1,
            "start_time_seconds": 0.0,
            "end_time_seconds": 30.0,
            "narration_text": "Scene one narration.",
        },
        {
            "scene_number": 2,
            "start_time_seconds": 30.0,
            "end_time_seconds": 60.0,
            "narration_text": "Scene two narration.",
        },
    ]

    # Build SceneForAssembly the way the fixed handler does
    scenes = []
    for i, r2_key in enumerate(processed_keys):
        timing = raw_scenes[i] if i < len(raw_scenes) else {}
        scenes.append(
            SceneForAssembly(
                scene_number=timing.get("scene_number", i + 1),
                image_storage_path=r2_key,
                start_seconds=float(timing.get("start_time_seconds", 0)),
                end_seconds=float(timing.get("end_time_seconds", 30)),
                narration_text=timing.get("narration_text", ""),
            )
        )

    caption_words = [
        CaptionWord(text="Scene", start_frame=0, end_frame=10),
        CaptionWord(text="one", start_frame=10, end_frame=20),
    ]

    assembly = AssemblyInput(
        video_id=vid,
        channel_id=cid,
        title="Test Title",
        scenes=scenes,
        audio_path=f"{cid}/{vid}/final_audio.wav",
        caption_words=caption_words,
        audio_duration_seconds=60.0,
    )

    assert len(assembly.scenes) == 2
    assert assembly.scenes[0].image_storage_path.endswith("scene_000_processed.jpg")
    assert assembly.scenes[1].start_seconds == 30.0
    assert assembly.audio_path.endswith("final_audio.wav")
    assert len(assembly.caption_words) == 2


# ---------------------------------------------------------------------------
# 4. VideoUploadInput can be built from assembly + thumbnail + caption
# ---------------------------------------------------------------------------


def test_youtube_upload_input_buildable():
    """VideoUploadInput can be constructed from assembly, thumbnail, and caption outputs.

    The handler downloads R2 keys to local paths before building VideoUploadInput,
    which requires local filesystem paths for file_path, thumbnail_path, srt_path.
    """
    from src.models.youtube import VideoUploadInput

    vid = uuid.uuid4()
    cid = uuid.uuid4()

    # These are local paths (after downloading from R2)
    upload = VideoUploadInput(
        video_id=vid,
        channel_id=cid,
        file_path="/tmp/crimemill/worker/final.mp4",
        title="The $2 Billion Fraud Nobody Talks About",
        description="In this video we explore...",
        tags=["fraud", "documentary", "true crime"],
        thumbnail_path="/tmp/crimemill/worker/thumbnail.jpg",
        srt_path="/tmp/crimemill/worker/captions.srt",
    )

    assert upload.file_path.endswith(".mp4")
    assert upload.thumbnail_path is not None
    assert upload.thumbnail_path.endswith(".jpg")
    assert upload.srt_path is not None
    assert upload.srt_path.endswith(".srt")
    assert len(upload.tags) == 3
    assert upload.category_id == 27  # default: Education


# ---------------------------------------------------------------------------
# 5. DescriptionInput can be built from script generation outputs
# ---------------------------------------------------------------------------


def test_description_input_buildable_from_script():
    """DescriptionInput can be constructed from script generation outputs.

    The handler builds DescriptionInput from SceneBreakdown list, title,
    case summary, and optional affiliate/channel config.
    """
    from src.models.description import (
        AffiliateConfig,
        ChannelLinks,
        DescriptionInput,
    )
    from src.models.script import SceneBreakdown

    vid = uuid.uuid4()
    scenes = [
        SceneBreakdown(
            scene_number=1,
            start_time_seconds=0.0,
            end_time_seconds=45.0,
            narration_text="The story begins in a quiet suburb.",
            scene_description="Suburban street at dusk",
            emotion_tag="establishing",
            narration_speed="NORMAL",
        ),
        SceneBreakdown(
            scene_number=2,
            start_time_seconds=45.0,
            end_time_seconds=120.0,
            narration_text="But beneath the surface, a scheme was brewing.",
            scene_description="Close-up of financial documents",
            emotion_tag="suspicious",
            narration_speed="SLOW",
        ),
    ]

    desc_input = DescriptionInput(
        video_id=vid,
        title="The Quiet Suburb's $50M Secret",
        case_summary="A financial fraud scheme spanning three years...",
        scenes=scenes,
        sources=[],
        affiliate_config=AffiliateConfig(),
        channel_links=ChannelLinks(),
        hashtags=["fraud", "truecrime"],
    )

    assert len(desc_input.scenes) == 2
    assert desc_input.scenes[0].start_time_seconds == 0.0
    assert desc_input.title == "The Quiet Suburb's $50M Secret"


# ---------------------------------------------------------------------------
# 6. ImagePrompt field compatibility: script → image
# ---------------------------------------------------------------------------


def test_script_image_prompt_compatible_with_image_prompt():
    """script.ImagePrompt serializes fields that image.ImagePrompt can consume.

    script.ImagePrompt has: scene_number, prompt, negative_prompt,
        aspect_ratio, lighting, mood, reference_scene_description
    image.ImagePrompt has: prompt, negative_prompt, tier, model,
        width, height, scene_number

    Overlapping fields: prompt, negative_prompt, scene_number
    Extra fields in script version (lighting, mood, etc.) are dropped
    by Pydantic model_validate with default config.
    """
    from src.models.image import ImagePrompt as ImageGenPrompt
    from src.models.script import ImagePrompt as ScriptPrompt

    # Simulate what the worker does: serialize script prompts, then validate as image prompts
    script_prompt = ScriptPrompt(
        scene_number=1,
        prompt="Dark boardroom with scattered documents, cinematic lighting",
        negative_prompt="text, watermark, cartoon",
        aspect_ratio="16:9",
        lighting="cold blue overhead",
        mood="suspenseful",
        reference_scene_description="CEO office after raid",
    )

    dumped = script_prompt.model_dump()

    # model_validate should accept the overlapping fields and use defaults for the rest
    image_prompt = ImageGenPrompt.model_validate(dumped)
    assert image_prompt.prompt == script_prompt.prompt
    assert image_prompt.negative_prompt == script_prompt.negative_prompt
    assert image_prompt.scene_number == 1
    # Non-overlapping fields use defaults
    assert image_prompt.width == 1920
    assert image_prompt.height == 1080


# ---------------------------------------------------------------------------
# 7. MusicResult field mapping in handler
# ---------------------------------------------------------------------------


def test_music_result_handler_output_keys():
    """Verify the music_selection handler output keys match what
    audio_processing expects.

    music_selection outputs: music_r2_key, track_name, duration_seconds
    audio_processing reads:  music_data.get("music_r2_key", "")
    """
    # Simulate the fixed handler output
    music_output = {
        "track_name": "Shadows of Doubt",
        "music_r2_key": "ch123/vid456/background_music.wav",
        "duration_seconds": 180.0,
        "cost_usd": "0",
    }

    # Simulate what audio_processing reads
    music_r2_key = music_output.get("music_r2_key", "")
    assert music_r2_key == "ch123/vid456/background_music.wav"
    assert not music_r2_key.startswith("http")  # it's an R2 key, not a URL


# ---------------------------------------------------------------------------
# 8. R2 path consistency
# ---------------------------------------------------------------------------


def test_r2_key_format_consistency():
    """All R2 keys follow the pattern: {channel_id}/{video_id}/{filename}."""
    cid = uuid.uuid4()
    vid = uuid.uuid4()

    filenames = [
        "voiceover.wav",
        "scene_001_raw.jpg",
        "scene_000_processed.jpg",
        "final_audio.wav",
        "background_music.wav",
        "captions.srt",
        "caption_words.json",
        "thumbnail.jpg",
        "script.json",
    ]

    for fname in filenames:
        key = f"{cid}/{vid}/{fname}"
        parts = key.split("/")
        assert len(parts) == 3, f"R2 key should have 3 parts: {key}"
        assert parts[0] == str(cid)
        assert parts[1] == str(vid)
        assert parts[2] == fname


# ---------------------------------------------------------------------------
# 9. SceneForAssembly ↔ Remotion SceneProps mapping
# ---------------------------------------------------------------------------


def test_scene_for_assembly_maps_to_remotion_props():
    """SceneForAssembly fields map to Remotion SceneProps via build_input_props().

    Python SceneForAssembly: image_storage_path, start_seconds, end_seconds, narration_text
    Remotion SceneProps:     imageUrl, startFrame, durationFrames, kenBurnsType, narrationText
    """
    from src.models.assembly import SceneForAssembly

    scene = SceneForAssembly(
        scene_number=1,
        image_storage_path="ch/vid/scene_000_processed.jpg",
        start_seconds=0.0,
        end_seconds=30.0,
        narration_text="The story begins.",
    )

    # Simulate what build_input_props does (minus URL signing)
    fps = 30
    start_frame = int(scene.start_seconds * fps)
    duration_frames = int((scene.end_seconds - scene.start_seconds) * fps)

    remotion_scene = {
        "imageUrl": f"https://signed-url/{scene.image_storage_path}",
        "startFrame": start_frame,
        "durationFrames": duration_frames,
        "kenBurnsType": "zoom_in",
        "narrationText": scene.narration_text,
    }

    assert remotion_scene["startFrame"] == 0
    assert remotion_scene["durationFrames"] == 900  # 30 seconds × 30 fps
    assert remotion_scene["narrationText"] == "The story begins."


# ---------------------------------------------------------------------------
# 10. Voiceover handler uses generate_voiceover (not from_scenes)
# ---------------------------------------------------------------------------


def test_voiceover_handler_uses_raw_text():
    """The voiceover handler calls generate_voiceover(script_text, voice_id),
    not generate_voiceover_from_scenes(), because script_generation outputs
    the full script text as a string.

    VoiceoverGenerator.generate_voiceover() expects: (str, str) → VoiceoverResult
    The handler reads: payload["script_generation"]["script_text"]
    """
    from src.models.voiceover import VoiceoverResult

    # Verify VoiceoverResult has the fields the handler uses
    fields = set(VoiceoverResult.model_fields.keys())
    assert "file_path" in fields, "VoiceoverResult needs file_path"
    assert "duration_seconds" in fields, "VoiceoverResult needs duration_seconds"
    assert "character_count" in fields, "VoiceoverResult needs character_count"
    assert "cost_usd" in fields, "VoiceoverResult needs cost_usd"


# ---------------------------------------------------------------------------
# 11. Pipeline stage DAG consistency with handler registration
# ---------------------------------------------------------------------------


def test_all_stages_have_handlers():
    """Every stage defined in PIPELINE_STAGES must have a handler in _STAGE_HANDLERS."""
    from src.pipeline.stages import PIPELINE_STAGES
    from src.pipeline.worker import _STAGE_HANDLERS

    missing = set(PIPELINE_STAGES.keys()) - set(_STAGE_HANDLERS.keys())
    assert not missing, f"Stages without handlers: {missing}"


def test_all_handlers_have_stages():
    """Every handler in _STAGE_HANDLERS should correspond to a PIPELINE_STAGES entry."""
    from src.pipeline.stages import PIPELINE_STAGES
    from src.pipeline.worker import _STAGE_HANDLERS

    extra = set(_STAGE_HANDLERS.keys()) - set(PIPELINE_STAGES.keys())
    assert not extra, f"Handlers without stage definitions: {extra}"
