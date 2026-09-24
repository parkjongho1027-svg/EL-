"""승강 위치별 매달린 로프 중량 기반 간이 장력 분포 (인증 계산 아님)."""
import math
from .errors import CalculationInputError
from .motor_dynamics import G

TensionSamples = tuple[tuple[float, float, float], ...]


def tension_by_height(car_kg: float, load_kg: float, balance_fraction: float,
                      travel_m: float, rope_kg_m: float, rope_count: float,
                      points: int = 41) -> TensionSamples:
    """도르래 양쪽의 정지 상태 로프 장력 N/가닥을 계산한다.

    위치 0은 카 최하층, H는 카 최상층. 로프 길이는 H-x 및 x 근사.
    가속도, 보상체인, 편차, 감김각 및 제조사 사양은 포함하지 않음.
    """
    raw = (car_kg,load_kg,balance_fraction,travel_m,rope_kg_m,rope_count)
    try:
        values = [float(v) if not isinstance(v,bool) else math.nan for v in raw]
    except (ValueError,TypeError,OverflowError):
        raise CalculationInputError('장력 그래프 입력은 숫자여야 합니다.') from None
    car,load,balance,travel,rope,n = values
    if (not all(map(math.isfinite, values)) or car <= 0 or load < 0 or
            not 0 <= balance <= 1 or travel <= 0 or rope < 0 or
            n < 1 or not n.is_integer() or type(points) is not int or not 2 <= points <= 1001):
        raise CalculationInputError('장력 입력 범위와 로프 가닥 수를 확인하세요.')
    weight = car + load * balance
    samples = tuple((travel*i/(points-1),
                     (car+load+n*rope*travel*(1-i/(points-1)))*G/n,
                     (weight+n*rope*travel*i/(points-1))*G/n)
                    for i in range(points))
    if not all(math.isfinite(value) for sample in samples for value in sample):
        raise CalculationInputError('로프 장력 계산 결과의 숫자 범위를 확인하세요.')
    return samples
