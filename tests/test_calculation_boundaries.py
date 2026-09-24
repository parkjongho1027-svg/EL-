"""UI를 거치지 않는 계산 호출과 여섯 제동 입력 조합 검증."""

import pytest

from src.core.calculators import (
    calculate_brake_values, calculate_motor_value, calculate_traffic_values,
    calculate_traction_values,
)
from src.core.errors import CalculationInputError


@pytest.mark.parametrize('pair', [
    {'v': 3, 't': .6}, {'v': 3, 'd': .9}, {'d': .9, 't': .6},
    {'v': 3, 'a': 5}, {'d': .9, 'a': 5}, {'t': .6, 'a': 5},
])
def test_all_brake_pairs_match_independent_reference(pair):
    actual = calculate_brake_values(**pair)
    for key, expected in {'v': 3, 't': .6, 'd': .9, 'a': 5}.items():
        assert actual[key] == pytest.approx(expected, rel=1e-12)
    assert actual['consistent']


def test_extra_brake_value_mismatch_is_exposed():
    result = calculate_brake_values(v=3, t=.6, d=1.8)
    assert not result['consistent']
    assert result['differences']['d'] == pytest.approx(1)


def test_core_rejects_nonfinite_traction_and_brake_results():
    with pytest.raises(CalculationInputError, match='숫자 범위'):
        calculate_traction_values(dict(OB=50, Wc=1e308, Q=1e308,
                                       H=1e308, wr=1e308, n=6, Wcomp=0, Wm=0))
    with pytest.raises(CalculationInputError, match='숫자 범위'):
        calculate_brake_values(v=1e308, t=1e308)


@pytest.mark.parametrize('target,incorrect', [('eff', .1), ('OB', 100)])
def test_motor_rejects_inverse_outside_physical_range(target, incorrect):
    # P is intentionally inconsistent with Q, V and the missing efficiency/balance.
    values = {'P': incorrect, 'Q': 1500, 'V': 180, 'OB': .45, 'eff': .8}
    values.pop(target)
    with pytest.raises(CalculationInputError):
        calculate_motor_value(target, values)


@pytest.fixture
def traffic():
    return dict(A=100, F=5, excluded_floors=2, S=10, phi=.15,
                C=10, board_rate=.8, n=3, td=4, tp=1, Tr_travel=60)


@pytest.mark.parametrize('overrides', [
    {'F': 5.5}, {'C': 10.5}, {'n': 3.5}, {'excluded_floors': .5},
    {'express_stops': .5}, {'express_stops': 3},
    {'floor_areas': [100, 200]},
])
def test_traffic_rejects_invalid_counts_or_incomplete_floor_areas(traffic, overrides):
    with pytest.raises(CalculationInputError):
        calculate_traffic_values(traffic | overrides)


def test_floor_area_list_is_used_instead_of_uniform_area(traffic):
    result = calculate_traffic_values(traffic | {'floor_areas': [100, 200, 300]})
    assert result['included_floors'] == 3
    assert result['total_area'] == pytest.approx(600)
    assert result['population'] == pytest.approx(60)
