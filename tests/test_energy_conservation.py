"""실측 정확도와 무관하게 이상화 모델의 일·에너지 수지를 검사한다."""

import pytest

from src.core.energy_model import compare_trips, estimate_trip
from src.core.errors import CalculationInputError


def ideal_trip(**changes):
    inputs = dict(distance=30, vmax=2, amax=1, jerk=.8,
                  car_mass=1000, load_mass=500, counterweight_mass=1500,
                  equivalent_extra_mass=0, resistance=100, direction='상승',
                  drive_efficiency=1, regen_efficiency=1,
                  auxiliary_kw=0, step=.01)
    return estimate_trip(**(inputs | changes))


@pytest.mark.parametrize('resistance', [0, 50, 100, 500])
def test_ideal_drive_net_energy_equals_resistance_times_distance(resistance):
    # Start/end kinetic energy and imbalance are zero: net work = R * S.
    profile = ideal_trip(resistance=resistance)
    assert profile['net_kwh'] == pytest.approx(resistance * 30 / 3_600_000,
                                               abs=2e-9)
    assert profile['samples'][-1][1] == pytest.approx(30, abs=1e-7)


@pytest.mark.parametrize('direction,expected_sign', [('상승', 1), ('하강', -1)])
def test_ideal_elevation_energy_changes_sign_with_direction(direction, expected_sign):
    # car + payload exceeds counterweight by 200 kg; no other losses.
    profile = ideal_trip(load_mass=700, resistance=0, direction=direction)
    gravity_work_kwh = 200 * 9.80665 * 30 / 3_600_000
    assert profile['net_kwh'] == pytest.approx(expected_sign * gravity_work_kwh,
                                               abs=2e-9)


def test_auxiliary_power_adds_running_time_energy():
    idle = ideal_trip(auxiliary_kw=0)
    active = ideal_trip(auxiliary_kw=.2)
    assert active['net_kwh'] - idle['net_kwh'] == pytest.approx(
        .2 * active['duration_s'] / 3600, abs=1e-12)


def test_identical_curves_report_zero_modeled_saving():
    shared = dict(distance=30, car_mass=1000, load_mass=500,
                  counterweight_mass=1500, equivalent_extra_mass=0,
                  resistance=100, direction='상승', drive_efficiency=.85,
                  regen_efficiency=.5, auxiliary_kw=.1)
    curve = dict(vmax=2, amax=1, jerk=.8)
    result = compare_trips(shared, curve, curve)
    assert result['difference_kwh'] == 0
    assert result['difference_pct'] == 0


def test_reference_net_zero_has_no_valid_saving_percentage():
    shared = dict(distance=30, car_mass=1000, load_mass=500,
                  counterweight_mass=1500, equivalent_extra_mass=0,
                  resistance=0, direction='상승', drive_efficiency=1,
                  regen_efficiency=1, auxiliary_kw=0)
    curve = dict(vmax=2, amax=1, jerk=.8)
    assert compare_trips(shared, curve, curve)['difference_pct'] is None
    with pytest.raises(CalculationInputError, match='항목별 객체'):
        compare_trips(None, curve, curve)
