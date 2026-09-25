"""Bounded encoder-log speed overlay against a model trajectory (m/s, seconds)."""

import csv
import math
from pathlib import Path

from .errors import CalculationInputError


def load_speed_log(path: str | Path) -> list[tuple[float, float]]:
    """Accept CSV/TXT containing time_s,speed_m_s and up to 50,000 samples."""
    source = Path(path)
    try:
        if source.stat().st_size > 5_000_000:
            raise CalculationInputError("속도 기록은 5 MB 이하여야 합니다.")
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not {"time_s", "speed_m_s"}.issubset(reader.fieldnames):
                raise CalculationInputError("CSV/TXT에는 time_s,speed_m_s 머리글이 필요합니다.")
            rows = []
            for row in reader:
                if len(rows) >= 50_000:
                    raise CalculationInputError("속도 기록은 최대 50,000행까지 읽습니다.")
                try:
                    time_s, speed = float(row["time_s"]), float(row["speed_m_s"])
                except (KeyError, TypeError, ValueError, OverflowError):
                    raise CalculationInputError("속도 기록의 시간·속도에 숫자만 입력하세요.") from None
                if (not math.isfinite(time_s) or not math.isfinite(speed)
                        or time_s < 0 or speed < 0 or rows and time_s <= rows[-1][0]):
                    raise CalculationInputError("시간은 0 이상 엄격히 증가하고 속도는 0 이상이어야 합니다.")
                rows.append((time_s, speed))
    except (OSError, UnicodeError, csv.Error) as error:
        raise CalculationInputError(f"속도 기록을 읽을 수 없습니다: {error}") from error
    if len(rows) < 2:
        raise CalculationInputError("비교할 속도 샘플이 두 개 이상 필요합니다.")
    return rows


def compare_speed_log(profile: dict, measured: list[tuple[float, float]]) -> dict:
    """Interpolate the model at measured timestamps; do not extrapolate or align clocks."""
    samples = profile["samples"]
    duration = profile["duration_s"]
    if (len(measured) < 2 or measured[0][0] > 0.2
            or abs(measured[-1][0] - duration) > max(0.5, duration * 0.05)):
        raise CalculationInputError("같은 운행의 시작과 끝을 포함해야 합니다(종료 시각 오차 5% 또는 0.5초 이하).")
    aligned = []
    i = 0
    for t, actual in measured:
        if t > duration:
            continue
        while i + 1 < len(samples) - 1 and samples[i + 1][0] < t:
            i += 1
        left, right = samples[i], samples[i + 1]
        fraction = (t - left[0]) / (right[0] - left[0])
        predicted = left[2] + fraction * (right[2] - left[2])
        aligned.append((t, predicted, actual))
    if len(aligned) < 2:
        raise CalculationInputError("운행 시간 내에 비교 가능한 기록이 부족합니다.")
    errors = [actual - predicted for _, predicted, actual in aligned]
    return {
        "points": aligned,
        "rmse_m_s": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "max_error_m_s": max(map(abs, errors)),
        "sample_count": len(aligned),
        "duration_s": duration,
    }
