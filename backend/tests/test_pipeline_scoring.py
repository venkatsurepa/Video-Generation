"""Tests for the pipeline stage DAG and scoring logic.

Verifies the PIPELINE_STAGES configuration is internally consistent:
dependency graph is acyclic, all referenced services exist, timeouts
are reasonable, and the stage ordering is correct.
"""

from __future__ import annotations

from src.pipeline.orchestrator import _MEDIA_STAGES, _STAGE_TO_VIDEO_STATUS, Orchestrator
from src.pipeline.stages import PIPELINE_STAGES


class TestPipelineDAG:
    def test_all_dependencies_reference_existing_stages(self) -> None:
        """Every dependency should reference a stage that exists in PIPELINE_STAGES."""
        for stage_name, config in PIPELINE_STAGES.items():
            for dep in config["depends_on"]:
                assert dep in PIPELINE_STAGES, (
                    f"Stage '{stage_name}' depends on '{dep}' which doesn't exist"
                )

    def test_no_circular_dependencies(self) -> None:
        """The stage DAG must be acyclic (no circular dependencies)."""
        # Topological sort — if it fails, there's a cycle
        visited: set[str] = set()
        in_stack: set[str] = set()

        def dfs(stage: str) -> None:
            if stage in in_stack:
                raise ValueError(f"Circular dependency detected at {stage}")
            if stage in visited:
                return
            in_stack.add(stage)
            for dep in PIPELINE_STAGES[stage]["depends_on"]:
                dfs(dep)
            in_stack.discard(stage)
            visited.add(stage)

        for stage in PIPELINE_STAGES:
            dfs(stage)

    def test_root_stages_have_no_dependencies(self) -> None:
        """script_generation should be the only root stage (no dependencies)."""
        roots = [name for name, cfg in PIPELINE_STAGES.items() if not cfg["depends_on"]]
        assert roots == ["script_generation"]

    def test_leaf_stages_are_post_upload(self) -> None:
        """Leaf stages (nothing depends on them) should be post-upload stages."""
        dependents = set()
        for config in PIPELINE_STAGES.values():
            for dep in config["depends_on"]:
                dependents.add(dep)

        leaf_stages = {name for name in PIPELINE_STAGES if name not in dependents}
        # All leaf stages depend (directly or transitively) on youtube_upload.
        # shorts_generation is NOT a leaf — cross_platform_distribution depends on it.
        assert leaf_stages == {
            "podcast_publish",
            "localization",
            "community_post",
            "discord_notification",
            "cross_platform_distribution",
        }

    def test_pipeline_stage_count(self) -> None:
        """Pipeline should have exactly 17 stages."""
        assert len(PIPELINE_STAGES) == 17


class TestStageConfiguration:
    def test_all_stages_have_required_fields(self) -> None:
        """Every stage config must have depends_on, service, timeout, max_retries."""
        required_keys = {"depends_on", "service", "timeout_seconds", "max_retries"}
        for name, config in PIPELINE_STAGES.items():
            assert required_keys.issubset(config.keys()), (
                f"Stage '{name}' missing keys: {required_keys - config.keys()}"
            )

    def test_timeouts_are_reasonable(self) -> None:
        """Stage timeouts should be between 30s and 15 minutes."""
        for name, config in PIPELINE_STAGES.items():
            timeout = config["timeout_seconds"]
            assert 30 <= timeout <= 900, f"Stage '{name}' timeout {timeout}s is outside [30, 900]"

    def test_max_retries_positive(self) -> None:
        """All stages should allow at least 1 retry."""
        for name, config in PIPELINE_STAGES.items():
            assert config["max_retries"] >= 1, (
                f"Stage '{name}' has max_retries={config['max_retries']}"
            )


class TestParallelStages:
    def test_voiceover_images_music_thumbnail_are_parallel(self) -> None:
        """voiceover, images, music, and thumbnail should all depend only on script."""
        parallel_after_script = {
            "voiceover_generation",
            "image_generation",
            "music_selection",
            "thumbnail_generation",
        }
        for stage in parallel_after_script:
            assert PIPELINE_STAGES[stage]["depends_on"] == ["script_generation"], (
                f"Stage '{stage}' should depend only on script_generation"
            )

    def test_audio_processing_depends_on_voiceover_and_music(self) -> None:
        """audio_processing needs both voiceover and music."""
        deps = set(PIPELINE_STAGES["audio_processing"]["depends_on"])
        assert deps == {"voiceover_generation", "music_selection"}

    def test_video_assembly_depends_on_three_stages(self) -> None:
        """video_assembly needs audio, images, and captions."""
        deps = set(PIPELINE_STAGES["video_assembly"]["depends_on"])
        assert deps == {"audio_processing", "image_processing", "caption_generation"}

    def test_youtube_upload_depends_on_assembly_and_classification(self) -> None:
        """youtube_upload needs video_assembly and content_classification."""
        deps = set(PIPELINE_STAGES["youtube_upload"]["depends_on"])
        assert deps == {"video_assembly", "content_classification"}

    def test_localization_depends_on_youtube_upload(self) -> None:
        """localization runs AFTER English version is published."""
        deps = set(PIPELINE_STAGES["localization"]["depends_on"])
        assert deps == {"youtube_upload"}


class TestOrchestratorDependents:
    def test_script_generation_has_five_dependents(self) -> None:
        """script_generation should unlock 5 parallel stages."""
        deps = Orchestrator.get_dependents("script_generation")
        assert set(deps) == {
            "voiceover_generation",
            "image_generation",
            "music_selection",
            "thumbnail_generation",
            "content_classification",
        }

    def test_voiceover_has_caption_dependent(self) -> None:
        """voiceover_generation should unlock caption_generation."""
        deps = Orchestrator.get_dependents("voiceover_generation")
        assert "caption_generation" in deps
        assert "audio_processing" in deps

    def test_youtube_upload_has_post_upload_dependents(self) -> None:
        """youtube_upload unlocks podcast, shorts, localization, community, and discord."""
        deps = set(Orchestrator.get_dependents("youtube_upload"))
        assert deps == {
            "podcast_publish",
            "shorts_generation",
            "localization",
            "community_post",
            "discord_notification",
        }


class TestVideoStatusMapping:
    def test_stage_to_video_status_mappings(self) -> None:
        """Key stages should map to the correct video status."""
        assert _STAGE_TO_VIDEO_STATUS["script_generation"] == "script_generated"
        assert _STAGE_TO_VIDEO_STATUS["video_assembly"] == "assembled"
        assert _STAGE_TO_VIDEO_STATUS["youtube_upload"] == "published"

    def test_media_stages_correct(self) -> None:
        """All 4 media stages should be tracked for media_complete."""
        assert (
            frozenset(
                {
                    "audio_processing",
                    "image_processing",
                    "caption_generation",
                    "thumbnail_generation",
                }
            )
            == _MEDIA_STAGES
        )

    def test_build_downstream_payload_merges_deps(self) -> None:
        """_build_downstream_payload should include results from all dependencies."""
        completed = {
            "voiceover_generation": {"voiceover_r2_key": "vo.wav"},
            "music_selection": {"music_url": "music.wav"},
            "script_generation": {"script_text": "test"},
        }
        payload = Orchestrator._build_downstream_payload("audio_processing", completed)

        assert "voiceover_generation" in payload
        assert "music_selection" in payload
        assert "script_generation" not in payload  # not a dep of audio_processing
