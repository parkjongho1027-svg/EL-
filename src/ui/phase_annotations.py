"""Seven physical S-curve intervals shared by the hoistway and plot renderers."""

import math

from src.core.hoistway import PHASE_NAMES


PHASE_ENGLISH = ("JERK", "CONST ACC", "ACC ROUND", "CRUISE",
                 "DEC ROUND", "CONST DEC", "LEVELING")


def phase_segments(profile):
    """Return nonempty (number, name, start, end) intervals, or none for old data."""
    durations = profile.get("phase_durations_s")
    if not isinstance(durations, (tuple, list)) or len(durations) != len(PHASE_NAMES):
        return ()
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) or value < 0 for value in durations):
        return ()
    elapsed = 0.0
    segments = []
    for number, (name, duration) in enumerate(zip(PHASE_NAMES, durations), 1):
        end = elapsed + duration
        if duration > 1e-12:
            segments.append((number, name, elapsed, end))
        elapsed = end
    if not math.isclose(elapsed, profile.get("duration_s", 0), rel_tol=1e-7,
                        abs_tol=1e-7):
        return ()
    return tuple(segments)
