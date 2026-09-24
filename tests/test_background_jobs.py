"""작업 함수는 Tk를 사용하지 않고 계산 결과만 반환한다."""
from background_jobs import calculate_snapshot


def test_mechanical_worker_returns_profile():
    result,measurements=calculate_snapshot('mechanical',(30,2,1,.8,1500,0))
    assert measurements=={}
    assert abs(result['samples'][-1][1]-30)<1e-7
