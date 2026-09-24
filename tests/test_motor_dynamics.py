"""독립 물리량과 수작업 산술 기준. 법규 또는 제조사 인증 예제가 아님."""
from dataclasses import replace
import math
import pytest

from src.core.motor_dynamics import G, MotorDutyInput, estimate_motor_duty
from src.core.errors import CalculationInputError


@pytest.fixture
def inputs():
    return MotorDutyInput(distance_m=30, speed_m_s=2, accel_m_s2=1,
                          jerk_m_s3=.8, car_kg=1000, load_kg=500,
                          rated_load_kg=1000, counterweight_kg=1500,
                          extra_mass_kg=300, sheave_radius_m=.4,
                          gear_ratio=1, roping_ratio=1,
                          motor_inertia_kg_m2=2, resistance_n=100,
                          efficiency=.85, cycle_s=120, regen_fraction=0)


@pytest.mark.parametrize('gear,roping,radius,expected', [
    (1,1,.4,2.5), (2,1,.4,5), (1,2,.4,5),
    (2,2,.5,8), (1,1,.5,2), (3,1,.5,6),
])
def test_axis_ratio_analytical(inputs, gear, roping, radius, expected):
    result = estimate_motor_duty(replace(inputs, gear_ratio=gear,
                              roping_ratio=roping, sheave_radius_m=radius))
    assert result['axis_rad_per_m'] == pytest.approx(expected, rel=1e-8)
    mass = inputs.car_kg + inputs.load_kg + inputs.counterweight_kg + inputs.extra_mass_kg
    assert result['reflected_inertia_kg_m2'] == pytest.approx(
        mass / expected**2 + inputs.motor_inertia_kg_m2, rel=1e-8)


@pytest.mark.parametrize('mass,rotor_j', [(100,0), (500,2), (1000,10),
                                            (2500,.5), (4000,20)])
def test_total_inertia_independent_reference(inputs, mass, rotor_j):
    updated = replace(inputs, car_kg=mass, motor_inertia_kg_m2=rotor_j)
    result = estimate_motor_duty(updated)
    assert result['reflected_inertia_kg_m2'] == pytest.approx(
        (mass+inputs.load_kg+inputs.counterweight_kg+inputs.extra_mass_kg)/2.5**2
        + rotor_j, rel=1e-8)


@pytest.mark.parametrize('cycle', [60,90,120,180,240])
def test_cycle_energy_and_duty_independent(inputs, cycle):
    result = estimate_motor_duty(replace(inputs, cycle_s=cycle))
    assert result['duty_ed_pct'] == pytest.approx(100*result['run_time_s']/cycle, rel=1e-8)
    assert result['resistor_average_kw'] == pytest.approx(
        result['resistor_cycle_kj']/cycle, rel=1e-8)


@pytest.mark.parametrize('regen', [0,.25,.5,.75,1])
def test_regen_resistor_fraction(inputs, regen):
    reference = estimate_motor_duty(inputs)
    result = estimate_motor_duty(replace(inputs, regen_fraction=regen))
    assert result['resistor_cycle_kj'] == pytest.approx(
        reference['resistor_cycle_kj']*(1-regen), abs=1e-9)
    assert result['resistor_peak_kw'] == pytest.approx(
        reference['resistor_peak_kw']*(1-regen), abs=1e-9)


@pytest.mark.parametrize('overrides', [
    {'load_kg':1001}, {'speed_m_s':0}, {'sheave_radius_m':0},
    {'cycle_s':1}, {'efficiency':1.01}, {'regen_fraction':1.01},
    {'motor_inertia_kg_m2':-1}, {'jerk_m_s3':math.nan},
    {'car_kg':True}, {'gear_ratio':'wrong'},
])
def test_invalid_physical_inputs(inputs, overrides):
    with pytest.raises(CalculationInputError):
        estimate_motor_duty(replace(inputs, **overrides))


def test_rotor_inertia_changes_peak_torque_not_trajectory(inputs):
    light = estimate_motor_duty(replace(inputs, motor_inertia_kg_m2=0))
    heavy = estimate_motor_duty(replace(inputs, motor_inertia_kg_m2=20))
    assert light['run_time_s'] == pytest.approx(heavy['run_time_s'])
    assert heavy['peak_torque_nm'] > light['peak_torque_nm']
    assert len(light['samples']) == len(heavy['samples'])
    assert any(abs(a[2]-b[2]) > 1 for a,b in zip(light['samples'],heavy['samples']))


def test_rated_load_boundary_is_valid_and_overload_is_rejected(inputs):
    at_rating = replace(inputs, load_kg=inputs.rated_load_kg)
    assert estimate_motor_duty(at_rating)['run_time_s'] > 0
    with pytest.raises(CalculationInputError, match='정격'):
        replace(inputs, load_kg=math.nextafter(inputs.rated_load_kg, math.inf))


def test_idle_time_reduces_rms_torque_without_changing_peak(inputs):
    short = estimate_motor_duty(inputs)
    long = estimate_motor_duty(replace(inputs, cycle_s=inputs.cycle_s * 4))
    assert long['peak_torque_nm'] == pytest.approx(short['peak_torque_nm'])
    assert long['thermal_rms_torque_nm'] == pytest.approx(
        short['thermal_rms_torque_nm'] / 2, rel=1e-8)
    assert long['duty_ed_pct'] == pytest.approx(short['duty_ed_pct'] / 4)


def test_core_package_imports_without_tk():
    import ast
    from pathlib import Path
    for path in (Path('src/core').glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        imports = [node.module for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom)]
        assert not any(name and name.startswith(('tkinter','src.ui')) for name in imports)
