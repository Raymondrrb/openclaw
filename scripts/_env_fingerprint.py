"""Shared environment fingerprint for history entries.

Answers: "Why did it work yesterday and not today?"
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Dict


def env_fingerprint() -> Dict[str, str]:
    """Minimal environment fingerprint for telemetry history."""
    return {
        "hostname": platform.node() or "unknown",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": sys.platform,
        "cwd": os.getcwd(),
    }
