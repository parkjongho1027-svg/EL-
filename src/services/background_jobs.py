"""Tk 객체에 접근하지 않는 실시간 시뮬레이션 작업."""

from src.core.energy_model import compare_trips, read_measurement
from src.core.elevator_review_engine import scurve_profile


def calculate_snapshot(mode, snapshot):
    if mode == "mechanical":
        return scurve_profile(*snapshot), {}
    shared, reference, candidate, paths = snapshot
    result = compare_trips(shared, reference, candidate)
    measurements = {
        key: read_measurement(path, result[key]) for key, path in paths.items() if path
    }
    return result, measurements
