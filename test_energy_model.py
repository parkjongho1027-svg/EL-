"""전력 적분, 비교 경계, 실측 CSV 읽기를 검증한다."""
import csv
import math
import tempfile
from pathlib import Path
from energy_model import compare_trips, estimate_trip, read_measurement

SHARED=dict(distance=30,car_mass=1000,load_mass=500,counterweight_mass=1500,
            equivalent_extra_mass=300,resistance=100,direction='상승',
            drive_efficiency=0.85,regen_efficiency=0.5,auxiliary_kw=0.15)
CURVE=dict(vmax=2,amax=1,jerk=0.8)
base=estimate_trip(**SHARED,**CURVE)
assert abs(base['net_kwh']-(base['draw_kwh']-base['returned_kwh']+base['auxiliary_kwh']))<1e-12
assert abs(base['auxiliary_kwh']-0.15*base['duration_s']/3600)<1e-12
assert base['returned_kwh']>0 and base['draw_kwh']>0
same=compare_trips(SHARED,CURVE,CURVE)
assert abs(same['difference_kwh'])<1e-12
assert same['difference_pct'] is not None and abs(same['difference_pct'])<1e-9
no_regen=estimate_trip(**(SHARED|{'regen_efficiency':0}),**CURVE)
assert no_regen['returned_kwh']==0 and no_regen['net_kwh']>base['net_kwh']
reverse=estimate_trip(**(SHARED|{'direction':'하강','load_mass':0}),**CURVE)
assert reverse['net_kwh'] != base['net_kwh']
for altered in ({'drive_efficiency':0},{'regen_efficiency':1.1},{'resistance':-1}):
    try:estimate_trip(**(SHARED|altered),**CURVE)
    except ValueError:pass
    else:raise AssertionError(f'허용되지 않는 입력: {altered}')
with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'measured.csv'
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(('time_s','speed_m_s','grid_kw'))
        for sample,p in zip(base['samples'],base['grid_kw_samples']):
            writer.writerow((sample[0],sample[2],p))
    observed=read_measurement(path,base)
    assert observed['speed_rmse_m_s']<1e-9
    assert abs(observed['measured_kwh']-base['net_kwh'])<5e-7
    path.write_text('time_s,speed_m_s,grid_kw\n0,0,1\n0,0,2\n',encoding='utf-8')
    try:read_measurement(path,base)
    except ValueError:pass
    else:raise AssertionError('중복 시각 수용')
print('동일 시나리오·부호별 전력 적분·회생·실측 CSV 검증 통과')
