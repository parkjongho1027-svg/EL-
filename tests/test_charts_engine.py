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


def test_rope_count_scales_suspended_load_but_not_rope_weight_per_strand():
    few = tension_by_height(1000, 500, .5, 30, 1, 5, points=2)
    many = tension_by_height(1000, 500, .5, 30, 1, 10, points=2)
    g = 9.80665
    assert few[0][1] == pytest.approx((1500 / 5 + 30) * g)
    assert many[0][1] == pytest.approx((1500 / 10 + 30) * g)
    assert few[0][1] - many[0][1] == pytest.approx(150 * g)


@pytest.mark.parametrize('points', [1, True, 1002])
def test_rope_sample_count_rejects_invalid_values(points):
    with pytest.raises(CalculationInputError):
        tension_by_height(1000, 500, .5, 30, 1, 5, points=points)


def test_rope_extreme_mass_does_not_return_infinity():
    with pytest.raises(CalculationInputError, match='숫자 범위'):
        tension_by_height(1e308, 1e308, .5, 1e308, 1e308, 5)


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
