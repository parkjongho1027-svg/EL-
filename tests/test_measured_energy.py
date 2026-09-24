"""실측 CSV가 계산 결과와 비교되는 경계의 회귀 검사."""
import csv
import math

import pytest

from src.core.energy_model import estimate_trip, read_measurement
from src.core.errors import CalculationInputError


@pytest.fixture
def predicted():
    return estimate_trip(distance=8, vmax=1, amax=1, jerk=1,
                         car_mass=1000, load_mass=200, counterweight_mass=1200,
                         equivalent_extra_mass=0, resistance=50, direction='상승',
                         drive_efficiency=.8, regen_efficiency=.5,
                         auxiliary_kw=.1, step=.1)


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('time_s', 'speed_m_s', 'grid_kw'))
        writer.writerows(rows)


def test_measurement_integrates_signed_power_and_interpolates_speed(tmp_path, predicted):
    samples = predicted['samples']
    duration = predicted['duration_s']
    half = duration / 2
    for i in range(len(samples) - 1):
        a, b = samples[i], samples[i + 1]
        if a[0] <= half <= b[0]:
            speed = a[2] + (b[2] - a[2]) * (half - a[0]) / (b[0] - a[0])
            break
    path = tmp_path / 'measurement.csv'
    write_csv(path, ((0, 0, 2), (half, speed, -1), (duration, 0, 0)))
    result = read_measurement(path, predicted)
    expected = ((2 - 1) * half / 2 + (-1 + 0) * half / 2) / 3600
    assert result['measured_kwh'] == pytest.approx(expected)
    assert result['speed_rmse_m_s'] == pytest.approx(0, abs=1e-9)
    assert result['sample_count'] == 3


@pytest.mark.parametrize('rows', [
    ((0, 0, 1), (0, 0, 1)),  # time must increase
    ((0, -1, 1), (10, 0, 1)),
    ((0, 0, 'nan'), (10, 0, 1)),
    ((0, 0, 1), (10, 0)),  # missing cell
])
def test_measurement_invalid_rows_are_user_errors(tmp_path, predicted, rows):
    path = tmp_path / 'bad.csv'
    write_csv(path, rows)
    with pytest.raises(CalculationInputError):
        read_measurement(path, predicted)


def test_measurement_invalid_utf8_is_user_error(tmp_path, predicted):
    path = tmp_path / 'bad.csv'
    path.write_bytes(b'\xff\xfe\x00')
    with pytest.raises(CalculationInputError, match='실측 CSV'):
        read_measurement(path, predicted)


def test_measurement_rejects_missing_header_and_short_trip(tmp_path, predicted):
    path = tmp_path / 'bad.csv'
    path.write_text('time_s,grid_kw\n0,0\n1,0\n', encoding='utf-8')
    with pytest.raises(CalculationInputError, match='헤더'):
        read_measurement(path, predicted)
    write_csv(path, ((0, 0, 0), (1, 0, 0)))
    with pytest.raises(ValueError, match='운행 시작부터 종료까지'):
        read_measurement(path, predicted)


def test_measurement_rejects_oversized_file_before_parsing(tmp_path, predicted):
    path = tmp_path / 'too_large.csv'
    with path.open('wb') as stream:
        stream.truncate(5_000_001)
    with pytest.raises(CalculationInputError, match='5 MB'):
        read_measurement(path, predicted)


def test_zero_power_measurement_has_no_percentage_error(tmp_path, predicted):
    path = tmp_path / 'zero.csv'
    write_csv(path, ((0, 0, 0), (predicted['duration_s'], 0, 0)))
    result = read_measurement(path, predicted)
    assert result['measured_kwh'] == 0
    assert result['energy_error_pct'] is None


def test_energy_input_rejects_nonfinite_power():
    with pytest.raises(CalculationInputError):
        estimate_trip(distance=8, vmax=1, amax=1, jerk=1,
                      car_mass=1000, load_mass=200, counterweight_mass=1200,
                      equivalent_extra_mass=0, resistance=math.inf, direction='상승',
                      drive_efficiency=.8, regen_efficiency=.5, auxiliary_kw=.1)
