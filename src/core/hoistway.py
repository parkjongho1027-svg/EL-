"""승강로 시뮬레이션에서 사용하는 층간 이동과 카·균형추 위치 계산."""

from dataclasses import dataclass
import math

from .errors import CalculationInputError


@dataclass(frozen=True)
class HoistwayTrip:
    """층수와 출발·도착층을 받아 한 번의 승강기 운행 조건을 관리한다."""
    floors: int
    start_floor: int
    end_floor: int
    height_m: float

    def __post_init__(self):
        """층수, 출발·도착층, 전체 승강행정이 올바른 값인지 확인한다."""
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
        """전체 승강행정을 층 사이 개수로 나누어 한 층 높이를 구한다."""
        return self.height_m / (self.floors - 1)

    @property
    def distance_m(self):
        """출발층에서 도착층까지 실제로 이동할 거리를 구한다."""
        return abs(self.end_floor - self.start_floor) * self.floor_height_m

    @property
    def direction(self):
        """상승은 1, 하강은 -1로 운행 방향을 반환한다."""
        return 1 if self.end_floor > self.start_floor else -1

    def position(self, traveled_m):
        """이동한 거리를 이용해 현재 카와 균형추의 높이를 계산한다."""
        if not isinstance(traveled_m, (int, float)) or not math.isfinite(traveled_m):
            raise CalculationInputError("이동 위치는 유한한 숫자여야 합니다.")
        travel = min(self.distance_m, max(0.0, traveled_m))
        car = (self.start_floor - 1) * self.floor_height_m + self.direction * travel
        return car, self.height_m - car


def trip_phase(samples, index):
    """현재 S-Curve 표본이 8단계 운행 상태 중 어디에 해당하는지 구한다."""
    if not samples or not 0 <= index < len(samples):
        raise CalculationInputError("운행 표본의 위치가 올바르지 않습니다.")
    if index == len(samples) - 1:
        return "도착"
    if index == 0:
        return "Jerk"

    _t, _x, velocity, acceleration, _power = samples[index]
    prev_a = samples[index - 1][3]
    next_a = samples[index + 1][3] if index + 1 < len(samples) else acceleration
    da = next_a - prev_a
    eps_a, eps_j, eps_v = 1e-6, 1e-7, 1e-6

    # 현재 가속도의 부호와 앞뒤 표본의 가속도 변화를 함께 보고
    # Jerk → 일정가속 → 가속라운드 → 전속 → 감속라운드
    # → 일정감속 → 착상부 → 도착 순서의 상태를 구분한다.
    if acceleration > eps_a:
        if da > eps_j:
            return "Jerk"
        if da < -eps_j:
            return "가속라운드"
        return "일정가속"
    if acceleration < -eps_a:
        if da < -eps_j:
            return "감속라운드"
        if da > eps_j:
            return "착상부"
        return "일정감속"
    if velocity > eps_v:
        return "전속"
    return "Jerk"
