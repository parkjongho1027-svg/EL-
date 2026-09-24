"""5분 동안 완료된 왕복 운행으로 계산한 간이 수송 인원 시뮬레이션."""
import heapq
import math
import random
from .errors import CalculationInputError


def simulate_five_minutes(floors, cars, seats, board_rate, travel_s,
                          door_s, passenger_s, *, seed=42):
    """고정된 탑승률·균등 목적층 가정, 300초 이내 완료된 운행만 집계.

    대기행렬/배차/재호출/승객 도착률/역방향은 모델 밖이다.
    """
    vals = (floors,cars,seats,board_rate,travel_s,door_s,passenger_s)
    if (any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)
            for v in vals) or any(v <= 0 for v in vals) or
            not all(isinstance(v,int) and v <= 100 for v in (floors,cars,seats)) or
            floors < 2 or board_rate > 1):
        raise CalculationInputError('층수·대수·정원은 양의 정수(최대 100), 시간은 양수, 탑승률은 0~1입니다.')
    rng = random.Random(seed)
    rider_count = max(1, round(seats*board_rate))
    available = [0.0]*cars
    heapq.heapify(available)
    completed = [0]*(floors-1)
    trips = 0
    while available:
        start = heapq.heappop(available)
        if start >= 300:
            break
        destinations = [rng.randrange(floors-1) for _ in range(rider_count)]
        stops = len(set(destinations))
        farthest = max(destinations)+1
        duration = (travel_s*farthest/(floors-1) + door_s*stops
                    + passenger_s*rider_count)
        end = start + duration*1.1  # 문·탑승 지연 10%: 기존 교통량 모델의 손실시간 근사
        if end > 300:
            continue
        trips += 1
        if trips > 10000:
            raise CalculationInputError('반복 운행 수가 10,000회를 넘었습니다. 시간 단위를 확인하세요.')
        for dest in destinations:
            completed[dest] += 1
        heapq.heappush(available,end)
    return {'completed_people':sum(completed),
            'per_floor':tuple(completed), 'floors':floors, 'window_s':300}
