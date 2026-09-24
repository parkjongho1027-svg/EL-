"""계산 엔진의 직접 생성·모듈 의존성 경계 검사."""
from dataclasses import replace

import pytest

from src.core import elevator_review_engine, trajectory
from src.core.energy_model import EnergyTripInput
from src.core.errors import CalculationInputError


@pytest.fixture
def raw_trip():
    return dict(distance=30, vmax=2, amax=1, jerk=.8, car_mass=1000,
                load_mass=500, counterweight_mass=1500, equivalent_extra_mass=0,
                resistance=100, direction='상승', drive_efficiency=.85,
                regen_efficiency=.5, auxiliary_kw=.15, step=.05)


def test_direct_dataclass_construction_validates_and_normalizes(raw_trip):
    raw_trip['distance'] = '30'
    result = EnergyTripInput(**raw_trip)
    assert result.distance == 30.0
    assert isinstance(result.distance, float)
    with pytest.raises(CalculationInputError, match='distance'):
        replace(result, distance=0)


@pytest.mark.parametrize('field,invalid', [
    ('vmax', True), ('car_mass', -1), ('load_mass', -1),
    ('drive_efficiency', 1.1), ('regen_efficiency', 1.1),
    ('step', float('nan')), ('direction', '역방향'),
])
def test_direct_dataclass_rejects_invalid_values(raw_trip, field, invalid):
    raw_trip[field] = invalid
    with pytest.raises(CalculationInputError):
        EnergyTripInput(**raw_trip)


def test_validate_reports_unknown_and_missing_fields(raw_trip):
    with pytest.raises(CalculationInputError, match='알 수 없는'):
        EnergyTripInput.validate(**(raw_trip | {'unexpected': 1}))
    raw_trip.pop('step')
    with pytest.raises(CalculationInputError, match='step'):
        EnergyTripInput.validate(**raw_trip)


def test_legacy_review_import_points_to_independent_trajectory():
    assert elevator_review_engine.scurve_profile is trajectory.scurve_profile


def test_tiny_trajectory_inputs_fail_as_input_error():
    with pytest.raises(CalculationInputError, match='숫자 범위'):
        trajectory.scurve_profile(1e-308, 1e308, 1e-308,
                                  1e308, 1e308, 0, 1e-308)


def test_short_run_never_reaches_configured_speed():
    short = trajectory.scurve_profile(.5, 2, 1, .8, 1500)
    long = trajectory.scurve_profile(30, 2, 1, .8, 1500)
    assert short['cruise_s'] == 0
    assert short['peak_speed_m_s'] < 2
    assert short['samples'][-1][1] == pytest.approx(.5, abs=1e-8)
    assert long['peak_speed_m_s'] == 2
    assert long['cruise_s'] > 0
    assert short['duration_s'] < long['duration_s']


@pytest.mark.parametrize('bad', [0, -1, 'bad', True, float('nan')])
def test_trajectory_rejects_nonphysical_speed(bad):
    with pytest.raises(CalculationInputError):
        trajectory.scurve_profile(30, bad, 1, .8, 1500)
