"""Floor-to-floor positions for a simplified 1:1 hoistway animation."""

from dataclasses import dataclass
import math

from .errors import CalculationInputError


@dataclass(frozen=True)
class HoistwayTrip:
    floors: int
    start_floor: int
    end_floor: int
    height_m: float

    def __post_init__(self):
        if isinstance(self.floors, bool) or not isinstance(self.floors, int) or not 2 <= self.floors <= 100:
            raise CalculationInputError("전체 층수는 2~100 사이의 정수여야 합니다.")
        if any(isinstance(floor, bool) or not isinstance(floor, int) or not 1 <= floor <= self.floors
               for floor in (self.start_floor, self.end_floor)):
            raise CalculationInputError("출발층과 도착층은 1층부터 전체 층수 사이여야 합니다.")
        if self.start_floor == self.end_floor:
            raise CalculationInputError("출발층과 도착층을 다르게 선택하세요.")
        if isinstance(self.height_m, bool) or not isinstance(self.height_m, (int, float)) or not math.isfinite(self.height_m) or self.height_m <= 0:
            raise CalculationInputError("전체 승강행정은 유한한 양수여야 합니다.")

    @property
    def floor_height_m(self):
        return self.height_m / (self.floors - 1)

    @property
    def distance_m(self):
        return abs(self.end_floor - self.start_floor) * self.floor_height_m

    @property
    def direction(self):
        return 1 if self.end_floor > self.start_floor else -1

    def position(self, traveled_m):
        if not isinstance(traveled_m, (int, float)) or not math.isfinite(traveled_m):
            raise CalculationInputError("이동 위치는 유한한 숫자여야 합니다.")
        travel = min(self.distance_m, max(0.0, traveled_m))
        car = (self.start_floor - 1) * self.floor_height_m + self.direction * travel
        return car, self.height_m - car


PHASE_NAMES = ("jerk", "일정가속", "가속라운드", "전속", "감속라운드", "일정감속", "착상부")


def trip_phase(samples, index, phase_durations_s=None):
    """Classify a sample using the exact durations of the seven jerk segments."""
    if not samples or not 0 <= index < len(samples):
        raise CalculationInputError("운행 표본의 위치가 올바르지 않습니다.")
    if phase_durations_s is not None:
        if not isinstance(phase_durations_s, (tuple, list)) or len(phase_durations_s) != len(PHASE_NAMES) \
                or any(isinstance(value, bool) or not isinstance(value, (float, int))
                       or not math.isfinite(value) or value < 0 for value in phase_durations_s):
            raise CalculationInputError("운행 구간 시간은 유한한 0 이상 숫자 7개여야 합니다.")
        if index == len(samples) - 1:
            return "도착"
        time = samples[index][0]
        elapsed = 0.0
        for name, duration in zip(PHASE_NAMES, phase_durations_s):
            if duration <= 1e-12:
                continue
            elapsed += duration
            if time <= elapsed + 1e-9:
                return name
        return "착상부"
    if index == 0:
        return "출발"
    if index == len(samples) - 1:
        return "도착"
    acceleration = samples[index][3]
    if acceleration > 1e-6:
        return "가속"
    if acceleration < -1e-6:
        return "감속"
    return "주행"
