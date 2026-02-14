"""RayVault shared policy constants — single source of truth.

Every script that checks stability, drift, confidence, or thresholds
should import from here. This prevents the classic bug where refresh
uses one definition of "unstable" and repair uses another.

Changing a value here changes behavior globally.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Stability gate
# ---------------------------------------------------------------------------

STABILITY_SLEEP_SEC = 0.3       # sleep between size polls
STABILITY_ZERO_IS_UNSTABLE = True

# ---------------------------------------------------------------------------
# Probe retry
# ---------------------------------------------------------------------------

PROBE_RETRY_COUNT = 1
PROBE_RETRY_BACKOFF_SEC = 1.5

# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------

REPAIR_DOUBLE_CHECK_SLEEP_SEC = 0.5
REPAIR_DANGLING_SEEN_THRESHOLD = 2   # require N sightings before bucket-eligible

# ---------------------------------------------------------------------------
# Drift / QC
# ---------------------------------------------------------------------------

DRIFT_WARN_SEC = 0.5
DRIFT_CRITICAL_SEC = 1.0

# ---------------------------------------------------------------------------
# Identity confidence
# ---------------------------------------------------------------------------

# Confidence levels for index entries
CONFIDENCE_HIGH = "high"        # sha8 in filename + probe OK
CONFIDENCE_MEDIUM = "medium"    # no sha8 but size+mtime match previous
CONFIDENCE_LOW = "low"          # no sha8, no fingerprint match

# ---------------------------------------------------------------------------
# Root enforcement
# ---------------------------------------------------------------------------

ROOT_ENFORCEMENT = "strict"     # always reject outside root

# ---------------------------------------------------------------------------
# SHA8
# ---------------------------------------------------------------------------

ALLOW_MISSING_SHA8_DEFAULT = False

# ---------------------------------------------------------------------------
# Ring buffer sizes
# ---------------------------------------------------------------------------

HISTORY_RING_SIZE = 10

# ---------------------------------------------------------------------------
# Bitrate
# ---------------------------------------------------------------------------

BITRATE_MIN_BPS = 1_000_000    # 1 Mbps

# ---------------------------------------------------------------------------
# Index schema
# ---------------------------------------------------------------------------

INDEX_SCHEMA_VERSION = 2
