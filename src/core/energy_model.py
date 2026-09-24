"""동일 운행 조건의 두 S-Curve 전기 에너지 추정과 실측 CSV 검증."""
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from .errors import CalculationInputError
from .trajectory import scurve_profile


@dataclass(frozen=True, slots=True)
class EnergyTripInput:
    """UI와 순수 계산 함수 사이의 단위/범위 확인된 운행 입력."""
    distance: float
    vmax: float
    amax: float
    jerk: float
    car_mass: float
    load_mass: float
    counterweight_mass: float
    equivalent_extra_mass: float
    resistance: float
    direction: str
    drive_efficiency: float
    regen_efficiency: float
    auxiliary_kw: float
    step: float

    def __post_init__(self):
        # Direct dataclass construction must enforce the same limits as validate().
        positive = ('distance','vmax','amax','jerk','car_mass','counterweight_mass','drive_efficiency','step')
        nonnegative = ('load_mass','equivalent_extra_mass','resistance','regen_efficiency','auxiliary_kw')
        for name in positive:
            object.__setattr__(self, name, _finite(name, getattr(self, name), positive=True))
        for name in nonnegative:
            object.__setattr__(self, name, _finite(name, getattr(self, name), nonnegative=True))
        if self.direction not in ('상승','하강'):
            raise CalculationInputError('운행 방향은 상승 또는 하강이어야 합니다.')
        if self.drive_efficiency > 1 or self.regen_efficiency > 1:
            raise CalculationInputError('효율은 0~1 사이여야 합니다.')

    @classmethod
    def validate(cls, **raw: object) -> 'EnergyTripInput':
        positive = ('distance','vmax','amax','jerk','car_mass','counterweight_mass','drive_efficiency','step')
        nonnegative = ('load_mass','equivalent_extra_mass','resistance','regen_efficiency','auxiliary_kw')
        missing = set((*positive,*nonnegative,'direction')) - raw.keys()
        if missing:
            raise CalculationInputError('시뮬레이션 입력 항목이 누락되었습니다: '+', '.join(sorted(missing)))
        unknown = raw.keys() - set((*positive,*nonnegative,'direction'))
        if unknown:
            raise CalculationInputError('알 수 없는 시뮬레이션 입력 항목: '+', '.join(sorted(unknown)))
        return cls(**raw)


def _finite(name, value, positive=False, nonnegative=False):
    if isinstance(value,bool):
        raise CalculationInputError(f'{name}: 숫자를 입력하세요.')
    try:
        value = float(value)
    except (TypeError,ValueError,OverflowError):
        raise CalculationInputError(f'{name}: 숫자를 입력하세요.') from None
    if not math.isfinite(value) or (positive and value <= 0) or (nonnegative and value < 0):
        raise CalculationInputError(f'{name}: 유한한 {"양수" if positive else "0 이상" if nonnegative else "숫자"}가 필요합니다.')
    return value


def estimate_trip(distance, vmax, amax, jerk, car_mass, load_mass, counterweight_mass,
                  equivalent_extra_mass, resistance, direction, drive_efficiency,
                  regen_efficiency, auxiliary_kw, step=0.05):
    """상수 효율 근사. 전력 부호는 계통에서 끌어오면 양수, 회수하면 음수."""
    inputs=EnergyTripInput.validate(distance=distance,vmax=vmax,amax=amax,jerk=jerk,
        car_mass=car_mass,load_mass=load_mass,counterweight_mass=counterweight_mass,
        equivalent_extra_mass=equivalent_extra_mass,resistance=resistance,direction=direction,
        drive_efficiency=drive_efficiency,regen_efficiency=regen_efficiency,
        auxiliary_kw=auxiliary_kw,step=step)
    eta=inputs.drive_efficiency
    regen=inputs.regen_efficiency
    moving_mass=inputs.car_mass+inputs.load_mass+inputs.counterweight_mass+inputs.equivalent_extra_mass
    imbalance=(inputs.car_mass+inputs.load_mass-inputs.counterweight_mass)*9.80665*(1 if inputs.direction=='상승' else -1)
    force=imbalance+inputs.resistance
    profile=scurve_profile(inputs.distance,inputs.vmax,inputs.amax,inputs.jerk,moving_mass,force,inputs.step)
    powers=profile['signed_mechanical_kw_samples']
    def grid(p):
        return (p/eta if p >= 0 else p*regen)+inputs.auxiliary_kw
    grid_power=[grid(p) for p in powers]
    if not all(math.isfinite(p) for p in grid_power):
        raise CalculationInputError('전력 계산값이 숫자 범위를 초과합니다. 질량·속도·효율을 확인하세요.')
    samples=profile['samples']
    # 부호 변경 지점은 구동·회생 적분과 동일하게 기계동력의 0 교차에서 분리한다.
    draw_kwh=return_kwh=aux_kwh=0.
    for (t0,*_), (t1,*_), p0,p1 in zip(samples,samples[1:],powers,powers[1:]):
        dt=t1-t0
        if p0*p1 < 0:
            ratio=abs(p0)/(abs(p0)+abs(p1))
            segments=((p0,0.,dt*ratio),(0.,p1,dt*(1-ratio)))
        else:
            segments=((p0,p1,dt),)
        for a,b,interval in segments:
            area=(a+b)*interval/2/3600
            if area >= 0:
                draw_kwh += area/eta
            else:
                return_kwh += -area*regen
        aux_kwh += inputs.auxiliary_kw*dt/3600
    profile.update(grid_kw_samples=grid_power, moving_mass_kg=moving_mass,
                   imbalance_force_n=imbalance, resistance_n=inputs.resistance,
                   draw_kwh=draw_kwh, returned_kwh=return_kwh, auxiliary_kwh=aux_kwh,
                   net_kwh=draw_kwh-return_kwh+aux_kwh)
    if not all(math.isfinite(profile[key]) for key in ('draw_kwh','returned_kwh','auxiliary_kwh','net_kwh')):
        raise CalculationInputError('전기에너지 적분값이 숫자 범위를 초과합니다. 입력값을 확인하세요.')
    return profile


def compare_trips(shared, reference, candidate):
    if not all(isinstance(part,dict) for part in (shared,reference,candidate)):
        raise CalculationInputError('기준·후보 곡선의 입력 자료는 항목별 객체여야 합니다.')
    a=estimate_trip(**shared,**reference)
    b=estimate_trip(**shared,**candidate)
    saved=a['net_kwh']-b['net_kwh']
    percent=saved/a['net_kwh']*100 if a['net_kwh'] > 1e-12 else None
    return {'reference':a,'candidate':b,'difference_kwh':saved,'difference_pct':percent}


def read_measurement(path, predicted):
    """헤더 time_s,speed_m_s,grid_kw. 음수 grid_kw는 실측 계통 회수."""
    path=Path(path)
    try:
        if not path.is_file():
            raise CalculationInputError(f'실측 파일을 찾을 수 없습니다: {path}')
        if path.stat().st_size > 5_000_000:
            raise CalculationInputError('실측 CSV는 5 MB 이하여야 합니다.')
        with path.open('r',encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream)
            if not reader.fieldnames or not {'time_s','speed_m_s','grid_kw'} <= set(reader.fieldnames):
                raise CalculationInputError('CSV 헤더는 time_s,speed_m_s,grid_kw가 필요합니다.')
            rows=[]
            for row in reader:
                if len(rows)>=100000:
                    raise CalculationInputError('실측 데이터는 10만 행 이하여야 합니다.')
                try:
                    t,v,p=(float(row[key]) for key in ('time_s','speed_m_s','grid_kw'))
                except (KeyError,TypeError,ValueError):
                    raise CalculationInputError('실측 CSV에 누락되거나 숫자가 아닌 값이 있습니다.') from None
                if not all(math.isfinite(x) for x in (t,v,p)) or t<0 or v<0 or (rows and t<=rows[-1][0]):
                    raise CalculationInputError('실측 시간은 0 이상 증가, 속도는 0 이상, 전력은 유한한 값이어야 합니다.')
                rows.append((t,v,p))
    except (OSError,UnicodeError,csv.Error) as error:
        raise CalculationInputError(f'실측 CSV를 읽을 수 없습니다: {error}') from error
    if len(rows)<2 or rows[0][0]>0.2 or abs(rows[-1][0]-predicted['duration_s'])>max(0.5,predicted['duration_s']*0.05):
        raise ValueError('실측 CSV는 운행 시작부터 종료까지 포함해야 하며 예측 운행시간과 5% 또는 0.5초 이내로 맞아야 합니다.')
    energy=sum((b[0]-a[0])*(a[2]+b[2])/2/3600 for a,b in zip(rows,rows[1:]))
    samples=predicted['samples']
    i=0
    error2=0.
    for t,v,_ in rows:
        if t>samples[-1][0]:
            expected=0.
        else:
            while i+1<len(samples)-1 and samples[i+1][0]<t:
                i+=1
            a,b=samples[i],samples[i+1]
            fraction=max(0.,min(1.,(t-a[0])/(b[0]-a[0])))
            expected=a[2]+fraction*(b[2]-a[2])
        error2+=(v-expected)**2
    return {'measured_kwh':energy,'predicted_kwh':predicted['net_kwh'],
            'energy_error_kwh':predicted['net_kwh']-energy,
            'energy_error_pct':(predicted['net_kwh']-energy)/abs(energy)*100 if abs(energy)>1e-12 else None,
            'speed_rmse_m_s':math.sqrt(error2/len(rows)),'sample_count':len(rows)}
