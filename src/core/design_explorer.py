"""Bounded motor/rope design exploration using the existing engineering engine.

All returned numbers are recomputed with the physics model. The small neighbour
surrogate is an auditable approximation for comparison, never a safety decision.
"""

from dataclasses import dataclass
import math
from statistics import mean

from .errors import CalculationInputError
from .motor_dynamics import MotorDutyInput, estimate_motor_duty
from .rope_traction import tension_by_height


@dataclass(frozen=True)
class DesignRequest:
    distance_m: float
    speed_m_s: float
    rated_load_kg: float
    car_kg: float
    rope_kg_m: float
    motor_options_kw: tuple[float, ...]
    sheave_radius_m: float = 0.4
    motor_inertia_kg_m2: float = 2.0
    cycle_s: float = 120.0
    power_margin: float = 1.15

    def __post_init__(self):
        for key in (
            "distance_m",
            "speed_m_s",
            "rated_load_kg",
            "car_kg",
            "sheave_radius_m",
            "cycle_s",
            "power_margin",
        ):
            value = getattr(self, key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise CalculationInputError(f"{key}: 유한한 양수를 입력하세요.")
        for key in ("rope_kg_m", "motor_inertia_kg_m2"):
            value = getattr(self, key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise CalculationInputError(f"{key}: 유한한 0 이상의 값을 입력하세요.")
        if self.power_margin < 1 or self.power_margin > 3:
            raise CalculationInputError("전동기 용량 여유 계수는 1~3이어야 합니다.")
        if (
            not self.motor_options_kw
            or len(self.motor_options_kw) > 30
            or any(
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
                or v <= 0
                for v in self.motor_options_kw
            )
        ):
            raise CalculationInputError("선정 가능한 전동기 kW 목록을 확인하세요.")


def _duty_case(request, ropes, balance, load, direction):
    counterweight = request.car_kg + request.rated_load_kg * balance
    # Entire rope travel length is a conservative equivalent moving-mass assumption.
    inputs = MotorDutyInput(
        distance_m=request.distance_m,
        speed_m_s=request.speed_m_s,
        accel_m_s2=1.0,
        jerk_m_s3=0.8,
        car_kg=request.car_kg,
        load_kg=load,
        rated_load_kg=request.rated_load_kg,
        counterweight_kg=counterweight,
        extra_mass_kg=ropes * request.rope_kg_m * request.distance_m,
        sheave_radius_m=request.sheave_radius_m,
        gear_ratio=1,
        roping_ratio=1,
        motor_inertia_kg_m2=request.motor_inertia_kg_m2,
        resistance_n=100,
        efficiency=0.85,
        cycle_s=request.cycle_s,
        regen_fraction=0,
        direction=direction,
        step_s=0.1,
    )
    return estimate_motor_duty(inputs)


def _exact(request, ropes, balance):
    duties = [
        _duty_case(request, ropes, balance, load, direction)
        for load in (0, request.rated_load_kg)
        for direction in ("상승", "하강")
    ]
    peak_kw = max(case["peak_input_kw"] for case in duties)
    torque_nm = max(case["peak_torque_nm"] for case in duties)
    tension_n = max(
        v
        for sample in tension_by_height(
            request.car_kg,
            request.rated_load_kg,
            balance,
            request.distance_m,
            request.rope_kg_m,
            ropes,
            points=2,
        )
        for v in sample[1:]
    )
    return peak_kw, torque_nm, tension_n


def _estimate(anchors, ropes, balance):
    # Local inverse-distance estimate; anchor coordinates are scaled to similar ranges.
    neighbours = sorted(
        anchors,
        key=lambda row: ((row[0] - ropes) / 8) ** 2 + ((row[1] - balance) / 0.2) ** 2,
    )[:4]
    weights = [
        1 / max(1e-8, ((row[0] - ropes) / 8) ** 2 + ((row[1] - balance) / 0.2) ** 2)
        for row in neighbours
    ]
    return sum(row[2] * weight for row, weight in zip(neighbours, weights)) / sum(
        weights
    )


def explore_designs(request: DesignRequest):
    """Rank sampled motor/rope combinations; return exact results and holdout error."""
    if not isinstance(request, DesignRequest):
        raise CalculationInputError("검증된 설계 입력이 필요합니다.")
    anchors = [
        (n, ob, _exact(request, n, ob)[0])
        for n in (4, 6, 8, 10, 12)
        for ob in (0.35, 0.45, 0.55)
    ]
    held_out = [
        (n, ob, _exact(request, n, ob)[0]) for n in (5, 7, 9, 11) for ob in (0.4, 0.5)
    ]
    relative_errors = [
        abs(_estimate(anchors, n, ob) - kw) / max(kw, 1e-9) for n, ob, kw in held_out
    ]
    ratings = sorted(set(request.motor_options_kw))
    candidates = []
    rejected = 0
    for ropes in range(4, 13):
        for ob_index in range(9):
            balance = round(0.35 + ob_index * 0.025, 3)
            # Anchors and holdout are reused, but each output goes through exact physics.
            known = next(
                (
                    row[2]
                    for row in anchors + held_out
                    if row[0] == ropes and row[1] == balance
                ),
                None,
            )
            peak_kw, torque, tension = _exact(request, ropes, balance)
            if known is not None and not math.isclose(peak_kw, known, rel_tol=1e-10):
                raise CalculationInputError("물리식 재검증 값이 일치하지 않습니다.")
            motor = next(
                (v for v in ratings if v >= peak_kw * request.power_margin), None
            )
            if motor is None:
                rejected += 1
                continue
            candidates.append(
                {
                    "ropes": ropes,
                    "balance_pct": balance * 100,
                    "selected_motor_kw": motor,
                    "required_peak_kw": peak_kw,
                    "peak_torque_nm": torque,
                    "max_static_tension_n_per_rope": tension,
                    "surrogate_peak_kw": _estimate(anchors, ropes, balance),
                }
            )
    candidates.sort(
        key=lambda item: (
            item["selected_motor_kw"],
            item["ropes"],
            item["required_peak_kw"],
        )
    )
    top = []
    configurations = set()
    for candidate in candidates:
        configuration = (candidate["selected_motor_kw"], candidate["ropes"])
        if configuration not in configurations:
            configurations.add(configuration)
            top.append(candidate)
        if len(top) == 3:
            break
    return {
        "top": top,
        "feasible_count": len(candidates),
        "rejected_count": rejected,
        "holdout_mean_error_pct": 100 * mean(relative_errors),
        "holdout_max_error_pct": 100 * max(relative_errors),
        "tested_cases": 81,
    }
