"""Learning subsystem — global event registry and cross-video queries."""

from rayvault.learning.registry import (
    get_agent_learnings,
    get_patterns,
    get_promotion_candidates,
    get_weekly_summary,
    query_events,
)

__all__ = [
    "query_events",
    "get_patterns",
    "get_agent_learnings",
    "get_promotion_candidates",
    "get_weekly_summary",
]
