#!/usr/bin/env python3
"""Pipeline DAG integrity validator.

Validates that the pipeline stage graph defined in stages.py is a valid DAG,
all handlers exist, and the orchestrator state machine is consistent.

Usage:
    python -m scripts.validate_dag
"""

from __future__ import annotations

import sys
from collections import deque

# Orchestrator constants
from src.pipeline.orchestrator import _MEDIA_STAGES, _STAGE_TO_VIDEO_STATUS

# ---------------------------------------------------------------------------
# Import pipeline definitions
# ---------------------------------------------------------------------------
from src.pipeline.stages import PIPELINE_STAGES

# Worker handlers (import the dict directly)
from src.pipeline.worker import _STAGE_HANDLERS

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_PASS = "\033[92mPASS\033[0m"
_FAIL = "\033[91mFAIL\033[0m"
_WARN = "\033[93mWARN\033[0m"

errors: list[str] = []
warnings: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [{_PASS}] {label}")
    else:
        msg = f"{label}: {detail}" if detail else label
        errors.append(msg)
        print(f"  [{_FAIL}] {label}" + (f" — {detail}" if detail else ""))


def warn(label: str, detail: str = "") -> None:
    msg = f"{label}: {detail}" if detail else label
    warnings.append(msg)
    print(f"  [{_WARN}] {label}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# 1. DAG structure validation
# ---------------------------------------------------------------------------

print("\n=== 1. DAG Structure ===\n")

all_stages = set(PIPELINE_STAGES.keys())

# Check all dependency references are valid
dangling: list[tuple[str, str]] = []
for stage, config in PIPELINE_STAGES.items():
    for dep in config.get("depends_on", []):
        if dep not in all_stages:
            dangling.append((stage, dep))

check(
    "All dependency references are valid stages",
    len(dangling) == 0,
    f"dangling: {dangling}" if dangling else "",
)

# Check for cycles using Kahn's algorithm (topological sort)
in_degree: dict[str, int] = {s: 0 for s in all_stages}
adj: dict[str, list[str]] = {s: [] for s in all_stages}

for stage, config in PIPELINE_STAGES.items():
    for dep in config.get("depends_on", []):
        adj[dep].append(stage)
        in_degree[stage] += 1

queue: deque[str] = deque(s for s, d in in_degree.items() if d == 0)
sorted_stages: list[str] = []
while queue:
    node = queue.popleft()
    sorted_stages.append(node)
    for neighbor in adj[node]:
        in_degree[neighbor] -= 1
        if in_degree[neighbor] == 0:
            queue.append(neighbor)

has_cycle = len(sorted_stages) != len(all_stages)
check(
    "No cycles in DAG",
    not has_cycle,
    f"sorted {len(sorted_stages)}/{len(all_stages)} stages" if has_cycle else "",
)

if not has_cycle:
    print(f"  Topological order: {' → '.join(sorted_stages)}")

# Root stages (no dependencies)
roots = [s for s, c in PIPELINE_STAGES.items() if not c.get("depends_on", [])]
check(
    f"Root stages: {roots}",
    len(roots) >= 1,
    "No root stages found" if not roots else "",
)

# Leaf stages (nothing depends on them)
has_dependents = set()
for config in PIPELINE_STAGES.values():
    for dep in config.get("depends_on", []):
        has_dependents.add(dep)
leaves = sorted(all_stages - has_dependents)
print(f"  Leaf stages: {leaves}")

# Optional stage validation
optional_stages = {s for s, c in PIPELINE_STAGES.items() if c.get("optional", False)}
mandatory_stages = all_stages - optional_stages
print(f"  Optional stages ({len(optional_stages)}): {sorted(optional_stages)}")
print(f"  Mandatory stages ({len(mandatory_stages)}): {sorted(mandatory_stages)}")

# Check: no mandatory stage depends on an optional stage
mandatory_depending_on_optional: list[tuple[str, str]] = []
for stage in mandatory_stages:
    for dep in PIPELINE_STAGES[stage].get("depends_on", []):
        if dep in optional_stages:
            mandatory_depending_on_optional.append((stage, dep))

check(
    "No mandatory stage depends on an optional stage",
    len(mandatory_depending_on_optional) == 0,
    f"violations: {mandatory_depending_on_optional}"
    if mandatory_depending_on_optional
    else "",
)

# Fan-out analysis
print("\n  Fan-out from each stage:")
for stage in sorted_stages:
    dependents = [s for s, c in PIPELINE_STAGES.items() if stage in c.get("depends_on", [])]
    if dependents:
        print(f"    {stage} → {dependents} ({len(dependents)} downstream)")

# ---------------------------------------------------------------------------
# 2. Worker handler completeness
# ---------------------------------------------------------------------------

print("\n=== 2. Worker Handler Completeness ===\n")

handler_stages = set(_STAGE_HANDLERS.keys())

missing_handlers = all_stages - handler_stages
orphan_handlers = handler_stages - all_stages

check(
    f"All {len(all_stages)} stages have handlers",
    len(missing_handlers) == 0,
    f"missing: {missing_handlers}" if missing_handlers else "",
)

check(
    "No orphaned handlers (handlers without stages)",
    len(orphan_handlers) == 0,
    f"orphaned: {orphan_handlers}" if orphan_handlers else "",
)

# Verify each handler is callable
for stage, handler in _STAGE_HANDLERS.items():
    check(
        f"Handler for '{stage}' is callable",
        callable(handler),
        f"got {type(handler)}" if not callable(handler) else "",
    )

# ---------------------------------------------------------------------------
# 3. Orchestrator state machine
# ---------------------------------------------------------------------------

print("\n=== 3. Orchestrator State Machine ===\n")

# _STAGE_TO_VIDEO_STATUS references valid stages
for stage in _STAGE_TO_VIDEO_STATUS:
    check(
        f"Status mapping stage '{stage}' exists in PIPELINE_STAGES",
        stage in all_stages,
    )

# _MEDIA_STAGES references valid stages
for stage in _MEDIA_STAGES:
    check(
        f"Media stage '{stage}' exists in PIPELINE_STAGES",
        stage in all_stages,
    )

# _MEDIA_STAGES should all be mandatory
optional_media = _MEDIA_STAGES & optional_stages
check(
    "All media stages are mandatory (not optional)",
    len(optional_media) == 0,
    f"optional media stages: {optional_media}" if optional_media else "",
)

# Media stages should all converge before video_assembly
video_assembly_deps = set(PIPELINE_STAGES["video_assembly"]["depends_on"])
# Media stages that are direct deps of video_assembly
media_as_assembly_deps = _MEDIA_STAGES & video_assembly_deps
# Some media stages may be indirect deps (e.g., thumbnail_generation feeds content_classification)
print(f"  video_assembly depends on: {video_assembly_deps}")
print(f"  _MEDIA_STAGES: {_MEDIA_STAGES}")
print(f"  Media stages that are direct assembly deps: {media_as_assembly_deps}")

# Check that youtube_upload waits for video_assembly
yt_deps = set(PIPELINE_STAGES["youtube_upload"]["depends_on"])
check(
    "youtube_upload depends on video_assembly",
    "video_assembly" in yt_deps,
)

# Check post-upload stages depend on youtube_upload
post_upload = ["podcast_publish", "shorts_generation", "localization",
               "community_post", "discord_notification"]
for stage in post_upload:
    if stage in all_stages:
        deps = PIPELINE_STAGES[stage]["depends_on"]
        check(
            f"Post-upload stage '{stage}' depends on youtube_upload",
            "youtube_upload" in deps,
        )

# ---------------------------------------------------------------------------
# 4. Stage config completeness
# ---------------------------------------------------------------------------

print("\n=== 4. Stage Config Completeness ===\n")

for stage, config in PIPELINE_STAGES.items():
    has_service = "service" in config
    has_timeout = "timeout_seconds" in config
    has_retries = "max_retries" in config

    check(
        f"'{stage}' has service field",
        has_service,
        "missing 'service'" if not has_service else "",
    )
    check(
        f"'{stage}' has timeout_seconds",
        has_timeout,
        "missing 'timeout_seconds'" if not has_timeout else "",
    )
    check(
        f"'{stage}' has max_retries",
        has_retries,
        "missing 'max_retries'" if not has_retries else "",
    )

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 50)
print(f"Total stages: {len(all_stages)}")
print(f"Total handlers: {len(handler_stages)}")
print(f"Errors: {len(errors)}")
print(f"Warnings: {len(warnings)}")

if errors:
    print(f"\n{_FAIL} {len(errors)} error(s) found:")
    for e in errors:
        print(f"  - {e}")

if warnings:
    print(f"\n{_WARN} {len(warnings)} warning(s):")
    for w in warnings:
        print(f"  - {w}")

if not errors and not warnings:
    print(f"\n{_PASS} All checks passed!")

sys.exit(1 if errors else 0)
