"""Validate up/down floor geometry and simulated travel against trajectory output."""

import pytest

from src.core.errors import CalculationInputError
from src.core.hoistway import HoistwayTrip, trip_phase
from src.core.trajectory import scurve_profile


@pytest.mark.parametrize("start,end,expected_start,expected_end", [
    (2, 6, 3.0, 15.0),
    (6, 2, 15.0, 3.0),
])
def test_selected_floors_use_same_travel_and_opposite_car_counterweight(
    start, end, expected_start, expected_end
):
    trip = HoistwayTrip(11, start, end, 30)
    assert trip.distance_m == 12
    profile = scurve_profile(trip.distance_m, 2, 1, 0.8, 1500)
    start_car, start_weight = trip.position(profile["samples"][0][1])
    end_car, end_weight = trip.position(profile["samples"][-1][1])
    assert start_car == pytest.approx(expected_start)
    assert start_weight == pytest.approx(30 - expected_start)
    assert end_car == pytest.approx(expected_end, abs=1e-7)
    assert end_weight == pytest.approx(30 - expected_end, abs=1e-7)
    assert all(0 <= position <= 30 for position in (start_car, start_weight, end_car, end_weight))


@pytest.mark.parametrize("floors,start,end,height", [
    (1, 1, 1, 30), (8, 4, 4, 30), (8, 0, 4, 30), (8, 1, 9, 30),
    (8, 1, 2, 0), (8, 1, 2, float("nan")),
])
def test_invalid_floor_selection_is_rejected(floors, start, end, height):
    with pytest.raises(CalculationInputError):
        HoistwayTrip(floors, start, end, height)


def test_full_trip_displays_phases_in_order_when_cruise_exists():
    samples = scurve_profile(40, 2, 1, .8, 1500)["samples"]
    phases = [trip_phase(samples, index) for index in range(len(samples))]
    changes = [phase for index, phase in enumerate(phases)
               if index == 0 or phase != phases[index - 1]]
    assert changes == ["출발", "가속", "주행", "감속", "도착"]
    with pytest.raises(CalculationInputError):
        trip_phase(samples, len(samples))
