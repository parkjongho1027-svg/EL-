"""입력 수정 시 네 계산·검토·두 시뮬레이션의 재계산을 검사한다."""
from types import SimpleNamespace
from concurrent.futures import Future
from main import LiveCalculationController
from src.services.background_jobs import calculate_snapshot
class Root:
    def __init__(self):self.jobs=[]
    def after(self,_delay,callback):self.jobs.append(callback);return len(self.jobs)
    def after_cancel(self,_job):pass
    def flush(self):
        while self.jobs:
            self.jobs.pop(0)()
class ImmediateExecutor:
    def submit(self,func,*args):
        future=Future()
        try:future.set_result(func(*args))
        except Exception as error:future.set_exception(error)
        return future
    def shutdown(self,**_kwargs):pass
class Entry:
    def __init__(self,value):self.value=value
    def get(self):return self.value
class Panel:
    def __init__(self,values):
        self.entries={key:Entry(value) for key,value in values.items()}
        self.store=SimpleNamespace(_suppress_history=False)
        self.calls=0
    def calculate(self):
        assert self.store._suppress_history
        self.calls+=1
class Simulator(Panel):
    def __init__(self):
        super().__init__({'distance':'30','vmax':'2','amax':'1','jerk':'0.8','mass':'1500','force':'0'})
        self.energy_entries={key:Entry(value) for key,value in dict(car_mass='1000',
            load_mass='500',counterweight_mass='1500',equivalent_extra_mass='300',
            resistance='100',drive_efficiency='.85',regen_efficiency='.5',
            auxiliary_kw='.15',ref_vmax='2',ref_amax='1',ref_jerk='.8',
            candidate_vmax='2',candidate_amax='1',candidate_jerk='.8').items()}
        self.direction=SimpleNamespace(get=lambda:'상승')
        self.measurement_paths={'reference':Entry(''),'candidate':Entry('')}
        self._energy_profile=None
        self.energy_calls=0
    def winfo_exists(self):return True
    def calculate(self,precomputed=None):
        assert precomputed and precomputed['samples']
        self.calls+=1
    def calculate_energy(self,precomputed=None,premeasurements=None):
        assert precomputed and premeasurements=={}
        self.energy_calls+=1
motor=Panel({'Q':'1000'});traction=Panel({'Q':'1000'})
brake=Panel({'v':'2','t':'1','d':''})
traffic=Panel({'A':'800','criterion_source':'교재','floor_areas':'800;900'})
criteria=Panel({'count':'6'});criteria.traction_entries={('load','t1'):Entry('100')}
simulator=Simulator()
root=Root()
app=SimpleNamespace(root=root,panels=[motor,traction,brake,traffic],
    brake_panel=brake,traffic_panel=traffic,criteria_panel=criteria,scurve_panel=simulator)
controller=LiveCalculationController(app)
controller._executor.shutdown(wait=False,cancel_futures=True)
controller._executor=ImmediateExecutor()
for panel in (motor,traction,brake,traffic,criteria):
    controller.run(panel)
    assert panel.calls==1 and not panel.store._suppress_history
controller.run(simulator,'mechanical')
controller.run(simulator,'electrical')
root.flush()
assert simulator.calls==1 and simulator.energy_calls==1
controller.run(simulator,'mechanical')
controller._serial+=1  # 입력이 바뀐 뒤 도착한 옛 결과는 화면에 반영하지 않는다.
root.flush()
assert simulator.calls==1
simulator.entries['jerk'].value='1e'
controller.run(simulator,'mechanical')
assert simulator.calls==1
print('입력 지연 계산 범위·기록 억제·미완성 수식 건너뛰기 확인')
