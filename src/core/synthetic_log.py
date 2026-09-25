"""Clearly labelled, deterministic simulated signals for import/UI regression checks."""

import csv
from dataclasses import dataclass
import math
from pathlib import Path
import random

from .errors import CalculationInputError


@dataclass(frozen=True, slots=True)
class SyntheticOptions:
    seed: int = 42
    speed_noise_m_s: float = 0.015
    acceleration_noise_m_s2: float = 0.02
    delay_s: float = 0.025
    joint_spacing_m: float = 2.0
    joint_pulse_m_s2: float = 0.15
    harmonic_hz: float = 3.0
    harmonic_m_s2: float = 0.01

    def __post_init__(self):
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed <= 2**32 - 1:
            raise CalculationInputError("난수 시드는 0~4294967295 사이의 정수여야 합니다.")
        for key in ("speed_noise_m_s", "acceleration_noise_m_s2", "delay_s",
                    "joint_spacing_m", "joint_pulse_m_s2", "harmonic_hz", "harmonic_m_s2"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise CalculationInputError(f"{key}: 0 이상의 유한한 수가 필요합니다.")
        if self.joint_spacing_m == 0:
            raise CalculationInputError("레일 이음매 간격은 양수(m)여야 합니다.")


def generate_synthetic_log(profile: dict, options: SyntheticOptions = SyntheticOptions()) -> list[dict]:
    """Add deterministic noise and position-triggered pulses to an ideal profile.

    Synthetic speed is independently noised and not integrated from acceleration.
    This is for testing display/parser behaviour, not model accuracy or sensor physics.
    """
    samples = profile["samples"]
    if len(samples) > 20_010:
        raise CalculationInputError("합성 운행은 20,010샘플 이하로 제한합니다.")
    rng = random.Random(options.seed)
    result = []
    index = 0
    next_joint_m = options.joint_spacing_m
    for time_s, position_m, _speed, _accel, _power in samples:
        delayed_t = max(0.0, time_s - options.delay_s)
        while index + 1 < len(samples) - 1 and samples[index + 1][0] < delayed_t:
            index += 1
        left, right = samples[index:index + 2]
        fraction = (delayed_t - left[0]) / (right[0] - left[0])
        model_speed = left[2] + fraction * (right[2] - left[2])
        model_accel = left[3] + fraction * (right[3] - left[3])
        bump = 0.0
        if position_m >= next_joint_m:
            bump = options.joint_pulse_m_s2
            next_joint_m += options.joint_spacing_m * (1 + math.floor((position_m - next_joint_m) / options.joint_spacing_m))
        harmonic = options.harmonic_m_s2 * math.sin(2 * math.pi * options.harmonic_hz * time_s)
        result.append({
            "time_s": time_s,
            "speed_m_s": max(0.0, model_speed + rng.gauss(0, options.speed_noise_m_s)),
            "acceleration_m_s2": model_accel + bump + harmonic + rng.gauss(0, options.acceleration_noise_m_s2),
            "source": "SYNTHETIC_DEMO_NOT_MEASURED",
        })
    return result


def save_synthetic_log(path: str | Path, profile: dict, options: SyntheticOptions = SyntheticOptions()) -> int:
    """Write demo CSV compatible with both encoder and acceleration viewers."""
    rows = generate_synthetic_log(profile, options)
    try:
        with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=("time_s", "speed_m_s", "acceleration_m_s2", "source"))
            writer.writeheader()
            writer.writerows(rows)
    except OSError as error:
        raise CalculationInputError(f"합성 CSV를 저장할 수 없습니다: {error}") from error
    return len(rows)
