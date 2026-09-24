"""관성·운전주기 기반 모터/저항기 1차 설계 추정 (Tk 의존성 없음).

축 환산 비율 k = gear_ratio * roping_ratio / sheave_radius [rad/m].
카 이동 v에 대응하는 모터축 각속도는 k*v [rad/s]이다.
"""
from dataclasses import dataclass, fields
import math

from .errors import CalculationInputError
from .elevator_review_engine import scurve_profile

G = 9.80665


@dataclass(frozen=True, slots=True)
class MotorDutyInput:
    distance_m: float
    speed_m_s: float
    accel_m_s2: float
    jerk_m_s3: float
    car_kg: float
    load_kg: float
    rated_load_kg: float
    counterweight_kg: float
    extra_mass_kg: float
    sheave_radius_m: float
    gear_ratio: float
    roping_ratio: float
    motor_inertia_kg_m2: float
    resistance_n: float
    efficiency: float
    cycle_s: float
    regen_fraction: float
    direction: str = '상승'
    step_s: float = 0.05

    def __post_init__(self):
        positive = {'distance_m', 'speed_m_s', 'accel_m_s2', 'jerk_m_s3',
                    'car_kg', 'rated_load_kg', 'counterweight_kg', 'sheave_radius_m',
                    'gear_ratio', 'roping_ratio', 'efficiency', 'cycle_s', 'step_s'}
        for field in fields(self):
            if field.name == 'direction':
                continue
            value = getattr(self, field.name)
            if isinstance(value, bool):
                raise CalculationInputError(f'{field.name}: 유한한 숫자를 입력하세요.')
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError):
                raise CalculationInputError(f'{field.name}: 유한한 숫자를 입력하세요.') from None
            if not math.isfinite(value) or value < 0 or (field.name in positive and value == 0):
                raise CalculationInputError(f'{field.name}: 유효한 0 이상의 값을 입력하세요.')
            object.__setattr__(self, field.name, value)
        if self.direction not in ('상승', '하강'):
            raise CalculationInputError('direction: 상승 또는 하강을 선택하세요.')
        if self.load_kg > self.rated_load_kg:
            raise CalculationInputError('적재 질량이 정격 적재 질량을 초과했습니다.')
        if self.efficiency > 1 or self.regen_fraction > 1:
            raise CalculationInputError('효율과 회생 비율은 0~1 사이여야 합니다.')


def estimate_motor_duty(inputs: MotorDutyInput) -> dict:
    """동일한 S-Curve 궤적으로 축 토크, 열부하 및 저항기 전력을 추정한다.

    토크 RMS는 비운행 시간을 토크 0으로 취급한다. 정지 유지·문 구동 발열은 제외.
    음의 기계동력 중 (1-회생비율)만 저항기에서 열로 소모된다고 가정.
    """
    if not isinstance(inputs, MotorDutyInput):
        raise CalculationInputError('MotorDutyInput으로 검증된 입력이 필요합니다.')
    k = inputs.gear_ratio * inputs.roping_ratio / inputs.sheave_radius_m
    moving_mass = (inputs.car_kg + inputs.load_kg + inputs.counterweight_kg
                   + inputs.extra_mass_kg)
    force = ((inputs.car_kg + inputs.load_kg - inputs.counterweight_kg)
             * G * (1 if inputs.direction == '상승' else -1) + inputs.resistance_n)
    profile = scurve_profile(inputs.distance_m, inputs.speed_m_s, inputs.accel_m_s2,
                             inputs.jerk_m_s3, moving_mass, force, inputs.step_s)
    duration = profile['duration_s']
    if inputs.cycle_s < duration - 1e-8:
        raise CalculationInputError('운전 주기는 1회 주행시간보다 짧을 수 없습니다.')
    samples = profile['samples']
    torque_samples = []
    resistor_w_samples = []
    input_w_samples = []
    for time, _distance, speed, acceleration, _abs_power in samples:
        omega = k * speed
        torque = (force + moving_mass * acceleration) / k
        torque += inputs.motor_inertia_kg_m2 * k * acceleration
        shaft_w = torque * omega
        resistor_w = max(0.0, -shaft_w) * (1 - inputs.regen_fraction)
        if not all(map(math.isfinite, (time, omega, torque, shaft_w, resistor_w))):
            raise CalculationInputError('축 토크 또는 저항기 전력 계산값이 너무 큽니다.')
        torque_samples.append(torque)
        resistor_w_samples.append(resistor_w)
        input_w_samples.append(max(0.0, shaft_w) / inputs.efficiency)
    torque2_integral = 0.0
    resistor_energy_j = 0.0
    for idx in range(1, len(samples)):
        dt = samples[idx][0] - samples[idx-1][0]
        # 선형 보간 구간에서 ∫T²dt = dt*(T0²+T0*T1+T1²)/3
        t0, t1 = torque_samples[idx-1:idx+1]
        torque2_integral += dt * (t0*t0+t0*t1+t1*t1)/3
        # 0 교차 부근은 실제 저항기 에너지의 상계 쪽인 사다리꼴 근사.
        resistor_energy_j += dt * (resistor_w_samples[idx-1]+resistor_w_samples[idx])/2
    rms = math.sqrt(torque2_integral / inputs.cycle_s)
    result = {
        'run_time_s': duration,
        'cycle_s': inputs.cycle_s,
        'duty_ed_pct': 100 * duration / inputs.cycle_s,
        'axis_rad_per_m': k,
        'reflected_inertia_kg_m2': moving_mass / (k*k) + inputs.motor_inertia_kg_m2,
        'peak_torque_nm': max(abs(t) for t in torque_samples),
        'peak_motor_rad_s': k * profile['peak_speed_m_s'],
        'peak_input_kw': max(input_w_samples)/1000,
        'thermal_rms_torque_nm': rms,
        'resistor_peak_kw': max(resistor_w_samples)/1000,
        'resistor_cycle_kj': resistor_energy_j/1000,
        'resistor_average_kw': resistor_energy_j/inputs.cycle_s/1000,
        'samples': tuple((row[0], row[2], torque, resistor / 1000)
                         for row, torque, resistor in zip(samples, torque_samples, resistor_w_samples)),
    }
    if not all(math.isfinite(v) for k2, v in result.items() if k2 != 'samples'):
        raise CalculationInputError('계산 결과의 숫자 범위를 확인하세요.')
    return result
