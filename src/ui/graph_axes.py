"""Comparable axis ranges for charts opened as one saved-graph group."""

import math


def nice_step(value, sections=5):
    if not math.isfinite(value) or value <= 0:
        raise ValueError("그래프 축 입력이 올바르지 않습니다.")
    desired = value / sections
    base = 10 ** math.floor(math.log10(desired))
    for factor in (1, 2, 5, 10):
        if factor * base >= desired - 1e-12:
            return factor * base
    return 10 * base


def _upper(value, sections=5):
    step = nice_step(max(value, 1e-9), sections)
    return math.ceil(value / step - 1e-12) * step, step


def axes_for_graphs(kind, data):
    """Bounds and round ticks shared by selected records of the same kind."""
    if not data:
        raise ValueError("비교할 그래프가 없습니다.")
    if kind == "traction":
        x = max(samples[-1][0] for samples in data)
        high = max(
            value
            for samples in data
            for _distance, car, counter in samples
            for value in (car, counter)
        )
        y, y_step = _upper(high)
        x_max, x_step = _upper(x)
        return dict(x_max=x_max, x_step=x_step, y_min=0, y_max=y, y_step=y_step)
    if kind == "traffic":
        x = max(len(result["per_floor"]) for result in data)
        high = max(value for result in data for value in result["per_floor"])
        x_step = max(1, round(nice_step(x, 10)))
        x_max = math.ceil(x / x_step) * x_step
        # Counts must have integer tick labels; 1/2/5 scale where possible.
        y_step = max(1, round(nice_step(max(high, 1), 5)))
        return dict(
            x_max=x_max,
            x_step=x_step,
            y_min=0,
            y_max=math.ceil(max(high, 1) / y_step) * y_step,
            y_step=y_step,
        )
    if kind in ("mechanical", "electrical"):
        profiles = [
            profile
            for entry in data
            for profile in (
                (entry,)
                if kind == "mechanical"
                else (entry["reference"], entry["candidate"])
            )
        ]
        x_max, x_step = _upper(max(p["duration_s"] for p in profiles))
        speed_max, speed_step = _upper(max(p["peak_speed_m_s"] for p in profiles))
        electrical = kind == "electrical"
        values = [
            v
            for p in profiles
            for v in (
                p["grid_kw_samples"]
                if electrical
                else p["signed_mechanical_kw_samples"]
            )
        ]
        power_step = nice_step(max(max(values), abs(min(values)), 1e-9), 3)
        high = math.ceil(max(max(values), 0) / power_step) * power_step
        low = math.floor(min(min(values), 0) / power_step) * power_step
        if high <= low:
            high = low + power_step
        return dict(
            x_max=x_max,
            x_step=x_step,
            speed_max=speed_max,
            speed_step=speed_step,
            power_min=low,
            power_max=high,
            power_step=power_step,
        )
    raise ValueError("지원하지 않는 그래프입니다.")
