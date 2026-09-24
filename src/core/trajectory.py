"""GUI 및 기준 조항에 독립적인 저크 제한 운행 궤적 계산."""
import math
from .errors import CalculationInputError, SimulationLimitError

def scurve_profile(distance, vmax, amax, jerk, moving_mass, imbalance_force=0, step=0.05):
    """대칭 7구간 저크 제한 궤적과 부호가 있는 단순화 기계동력."""
    try:
        valid = (all(not isinstance(x,bool) and math.isfinite(x) and x > 0
                     for x in (distance,vmax,amax,jerk,moving_mass,step))
                 and not isinstance(imbalance_force,bool) and math.isfinite(imbalance_force))
    except (TypeError,ValueError,OverflowError):
        valid = False
    if not valid:
        raise CalculationInputError('거리·속도·가속도·저크·질량·시간간격은 유한한 양수여야 합니다.')
    def acceleration(v):
        tj = min(amax / jerk, math.sqrt(v / jerk))
        if not math.isfinite(tj) or tj <= 0 or jerk * tj == 0:
            raise CalculationInputError('가속 구간의 숫자 범위가 계산 정밀도를 벗어났습니다.')
        ta = max(0., v / (jerk*tj) - tj)
        distance_to_speed = v * (2*tj+ta)
        if not all(math.isfinite(x) for x in (ta, distance_to_speed)):
            raise CalculationInputError('가속 구간의 숫자 범위를 확인하세요.')
        return tj, ta, distance_to_speed
    tj, ta, min_distance = acceleration(vmax)
    vp = vmax
    if min_distance > distance:
        lo, hi = 0., vmax
        for _ in range(70):
            mid = (lo+hi)/2
            if acceleration(mid)[2] > distance:
                hi = mid
            else:
                lo = mid
        vp = (lo+hi)/2
        tj, ta, min_distance = acceleration(vp)
    if vp <= 0:
        raise CalculationInputError('계산된 최고속도가 숫자 정밀도를 벗어났습니다.')
    tc = max(0., (distance-min_distance)/vp)
    duration_estimate = 2*(2*tj+ta)+tc
    if not math.isfinite(duration_estimate) or duration_estimate/step > 20000:
        raise SimulationLimitError('시뮬레이션은 최대 20,000개 시간 샘플까지 지원합니다. 거리·속도·시간 간격을 확인하세요.')
    phases = ((jerk,tj),(0.,ta),(-jerk,tj),(0.,tc),(-jerk,tj),(0.,ta),(jerk,tj))
    t=x=v=a=0.
    samples=[(0.,0.,0.,0.,0.)]
    signed_kw=[0.]
    motoring_wh=braking_wh=0.

    def positive_area(p0, p1, dt):
        """부호 변경 시 0 교차점을 나눠 양의 구간만 적분한다. kW·s 반환."""
        if p0 >= 0 and p1 >= 0:
            return (p0 + p1)*dt/2
        if p0 <= 0 and p1 <= 0:
            return 0.
        if p0 > 0:
            return p0*dt*(p0/(p0-p1))/2
        return p1*dt*(p1/(p1-p0))/2

    for j,duration in phases:
        remaining=duration
        while remaining > 1e-12:
            if len(samples) >= 20010:
                raise SimulationLimitError('시뮬레이션은 최대 20,000개 시간 샘플까지 지원합니다. 입력값을 확인하세요.')
            dt=min(step,remaining)
            x += v*dt + a*dt*dt/2 + j*dt**3/6
            v += a*dt + j*dt*dt/2
            a += j*dt
            t += dt
            power_kw=(moving_mass*a+imbalance_force)*v/1000
            if not all(math.isfinite(number) for number in (t,x,v,a,power_kw)):
                raise CalculationInputError('운행 계산값이 너무 큽니다. 입력값을 확인하세요.')
            motoring_wh += positive_area(signed_kw[-1],power_kw,dt)*1000/3600
            braking_wh += positive_area(-signed_kw[-1],-power_kw,dt)*1000/3600
            signed_kw.append(power_kw)
            samples.append((t,x,max(0.,v),a,abs(power_kw)))
            remaining -= dt
    if not all(math.isfinite(number) for number in (motoring_wh, braking_wh, t, x, v, a)):
        raise CalculationInputError('운행 에너지 계산값의 숫자 범위를 확인하세요.')
    return {'duration_s':t,'peak_speed_m_s':vp,'cruise_s':tc,'samples':samples,
            'peak_mechanical_kw':max(row[4] for row in samples),
            'signed_mechanical_kw_samples':signed_kw,
            'peak_motoring_kw':max(signed_kw), 'peak_braking_kw':min(signed_kw),
            'motoring_mechanical_wh':motoring_wh,
            'braking_mechanical_wh':braking_wh}
