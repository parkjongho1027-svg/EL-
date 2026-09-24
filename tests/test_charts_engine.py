"""그래프용 값도 GUI 밖에서 검증한다."""
import pytest
from src.core.capacity import simulate_five_minutes
from src.core.rope_traction import tension_by_height
from src.core.errors import CalculationInputError


def test_rope_endpoints_by_hand():
    values = tension_by_height(1000,500,.5,30,1,5,points=3)
    g=9.80665
    assert values[0][1] == pytest.approx((1500+150)*g/5)
    assert values[0][2] == pytest.approx(1250*g/5)
    assert values[-1][1] == pytest.approx(1500*g/5)
    assert values[-1][2] == pytest.approx((1250+150)*g/5)


def test_five_minute_seed_and_car_count():
    one = simulate_five_minutes(10,1,10,.8,60,4,1,seed=42)
    two = simulate_five_minutes(10,2,10,.8,60,4,1,seed=42)
    assert one == simulate_five_minutes(10,1,10,.8,60,4,1,seed=42)
    assert two['completed_people'] >= one['completed_people']
    assert sum(one['per_floor']) == one['completed_people']


@pytest.mark.parametrize('bad',[(0,1,10,1,60,4,1),
                                  (10,0,10,1,60,4,1),
                                  (10,1,10,1.2,60,4,1),
                                  (10,1,10,1,0,4,1)])
def test_five_minute_bad_inputs(bad):
    with pytest.raises(CalculationInputError):
        simulate_five_minutes(*bad)
