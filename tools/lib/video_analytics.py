"""Video performance analytics — metrics recording and niche scoring.

Feeds YouTube performance data back into the pipeline to improve
future niche selection. Stdlib only.
"""

from __future__ import annotations

from tools.lib.common import now_iso
from tools.lib.supabase_client import insert, query, _enabled
from tools.lib.supabase_pipeline import set_channel_memory, get_channel_memory


def record_metrics(
    video_id: str,
    *,
    youtube_id: str = "",
    niche: str = "",
    views_24h: int | None = None,
    views_48h: int | None = None,
    views_7d: int | None = None,
    views_30d: int | None = None,
    ctr_percent: float | None = None,
    avd_seconds: int | None = None,
    avg_view_percent: float | None = None,
    affiliate_clicks: int | None = None,
    conversions: int | None = None,
    rpm_estimate: float | None = None,
) -> None:
    """Insert a video_metrics row. Only non-None fields are included."""
    row: dict = {
        "video_id": video_id,
        "recorded_at": now_iso(),
    }
    if youtube_id:
        row["youtube_id"] = youtube_id
    if niche:
        row["niche"] = niche
    if views_24h is not None:
        row["views_24h"] = views_24h
    if views_48h is not None:
        row["views_48h"] = views_48h
    if views_7d is not None:
        row["views_7d"] = views_7d
    if views_30d is not None:
        row["views_30d"] = views_30d
    if ctr_percent is not None:
        row["ctr"] = ctr_percent
    if avd_seconds is not None:
        row["avd_seconds"] = avd_seconds
    if avg_view_percent is not None:
        row["avg_view_percent"] = avg_view_percent
    if affiliate_clicks is not None:
        row["affiliate_clicks"] = affiliate_clicks
    if conversions is not None:
        row["conversions"] = conversions
    if rpm_estimate is not None:
        row["rpm_estimate"] = rpm_estimate

    insert("video_metrics", row)


def get_niche_performance(limit: int = 50) -> list[dict]:
    """Query recent video_metrics, ordered by recorded_at desc."""
    return query(
        "video_metrics",
        select="*",
        order="recorded_at.desc",
        limit=limit,
    )


def update_niche_scores() -> None:
    """Compute avg CTR/views per niche from video_metrics, save to channel_memory.

    Reads all metrics, groups by niche, computes averages, and saves
    the result as channel_memory["niche_performance_scores"].
    """
    metrics = get_niche_performance(limit=200)
    if not metrics:
        return

    # Group by niche
    niche_data: dict[str, list[dict]] = {}
    for m in metrics:
        niche = m.get("niche", "")
        if not niche:
            continue
        niche_data.setdefault(niche, []).append(m)

    scores: dict[str, dict] = {}
    for niche, items in niche_data.items():
        ctrs = [m["ctr"] for m in items if m.get("ctr") is not None]
        views_7d = [m["views_7d"] for m in items if m.get("views_7d") is not None]

        avg_ctr = sum(ctrs) / len(ctrs) if ctrs else 0
        avg_views = sum(views_7d) / len(views_7d) if views_7d else 0

        # Score: normalized CTR (0-10) + normalized views (0-5)
        ctr_score = min(avg_ctr / 1.0, 10.0)  # 10% CTR = max 10 points
        views_score = min(avg_views / 10000, 5.0)  # 50K views = max 5 points

        scores[niche] = {
            "avg_ctr": round(avg_ctr, 2),
            "avg_views_7d": round(avg_views, 0),
            "performance_bonus": round(ctr_score + views_score, 1),
            "video_count": len(items),
        }

    set_channel_memory("niche_performance_scores", scores)
