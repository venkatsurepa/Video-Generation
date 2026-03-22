from __future__ import annotations

__all__ = [
    "INSERT_COST",
    "GET_COST_SUMMARY",
    "GET_COST_BY_PROVIDER",
]

INSERT_COST: str = """
INSERT INTO generation_costs
    (video_id, stage, provider, model, input_units, output_units, cost_usd, latency_ms)
VALUES
    (%(video_id)s, %(stage)s, %(provider)s, %(model)s,
     %(input_units)s, %(output_units)s, %(cost_usd)s, %(latency_ms)s);
"""

GET_COST_SUMMARY: str = """
SELECT
    COUNT(DISTINCT gc.video_id) AS total_videos,
    SUM(gc.cost_usd) AS total_cost,
    AVG(vcs.total_cost_usd) AS avg_per_video,
    SUM(gc.cost_usd) FILTER (WHERE gc.stage = 'script_generation') AS script_cost,
    SUM(gc.cost_usd) FILTER (WHERE gc.stage = 'voiceover_generation') AS voiceover_cost,
    SUM(gc.cost_usd) FILTER (WHERE gc.stage = 'image_generation') AS image_cost,
    SUM(gc.cost_usd) FILTER (WHERE gc.stage = 'video_assembly') AS assembly_cost,
    SUM(gc.cost_usd) FILTER (WHERE gc.stage = 'thumbnail_generation') AS thumbnail_cost,
    SUM(gc.cost_usd) FILTER (WHERE gc.stage = 'caption_generation') AS caption_cost
FROM generation_costs gc
LEFT JOIN video_cost_summary vcs ON vcs.video_id = gc.video_id
WHERE gc.created_at >= current_date - make_interval(days := %(days)s);
"""

GET_COST_BY_PROVIDER: str = """
SELECT
    provider,
    model,
    COUNT(*) AS calls,
    SUM(cost_usd) AS total_cost
FROM generation_costs
WHERE created_at >= current_date - make_interval(days := %(days)s)
GROUP BY provider, model
ORDER BY total_cost DESC;
"""
