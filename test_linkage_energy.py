"""여섯 탭의 같은 설계값 전달과 S-Curve 기계적 일 보존을 검사."""
import math
from types import SimpleNamespace
from main import ElevatorApp, CriteriaPanel
from elevator_review_engine import scurve_profile
from simulation_plot import draw_scurve_plot

class Entry:
    def __init__(self, value=''):
        self.value = str(value)
    def get(self): return self.value
    def cget(self, name): return 'normal'
    def delete(self, *_): self.value = ''
    def insert(self, _, value): self.value = str(value)
class Var:
    def __init__(self, value): self.value = value
    def get(self): return self.value
class Panel:
    def __init__(self, name, entries):
        self.storage_key = name
        self.entries = {key: Entry(value) for key, value in entries.items()}
        self.undo_stack = []
    def capture_state(self):
        return {key: entry.get() for key, entry in self.entries.items()}
motor = Panel('motor', {'Q':'1500','OB':'45','V':'2','P':'19.03'})
motor.unit_vars = {'V':Var('m/s')}
traction = Panel('traction', {'Q':'1500','OB':'45','n':'6'})
brake = Panel('brake', {'v':''})
brake.speed_unit = Var('m/s')
traffic = Panel('traffic', {})
criteria = Panel('criteria', {'count':'8','rated':'2.5','selected_motor':'22'})
criteria.drive = Var('권상식')
scurve = Panel('scurve', {'vmax':'2','distance':'30'})
scurve.default_state = {'vmax':'2'}
app = SimpleNamespace(panels=[motor,traction,brake,traffic],motor_panel=motor,
                      traction_panel=traction,brake_panel=brake,traffic_panel=traffic,
                      criteria_panel=criteria,scurve_panel=scurve,_auto_filled_values={},
                      _panel_number=ElevatorApp._panel_number,
                      _can_auto_fill=lambda p,k,force=False:ElevatorApp._can_auto_fill(app,p,k,force))
app._collect_live_common_values=lambda index:ElevatorApp._collect_live_common_values(app,index)
common=app._collect_live_common_values(4)
assert common['speed_m_s']==2.5 and common['rope_count']==8
for panel in app.panels+[app.scurve_panel]:
    ElevatorApp._apply_live_common_values(app,panel,common)
assert motor.entries['V'].get()=='2.5'
assert traction.entries['n'].get()=='8'
assert brake.entries['v'].get()=='2.5'
assert scurve.entries['vmax'].get()=='2.5'
assert criteria.entries['selected_motor'].get()=='22'
assert motor.entries['P'].get()=='19.03'  # 계산 필요동력과 선정 전동기를 혼합하지 않는다.
# S-Curve 속도 상한을 의도적으로 낮춰도 정격속도를 역으로 바꾸지 않는다.
scurve.entries['vmax'].value='1.5'
assert app._collect_live_common_values(5)['speed_m_s']==2.5
ElevatorApp._apply_live_common_values(app,scurve,app._collect_live_common_values(0))
assert scurve.entries['vmax'].get()=='1.5'
# 전동기 탭을 출발점으로 바꾸어도 KC 정격속도까지 양방향 전달된다.
motor.entries['V'].value='3'
common=app._collect_live_common_values(0)
ElevatorApp._apply_live_common_values(app,criteria,common)
assert criteria.entries['rated'].get()=='3'

class CriteriaFake:
    def calculate(self): self.called=True
fake=CriteriaFake()
assert CriteriaPanel._calculate_on_return(fake)=='break' and fake.called

profile=scurve_profile(30,2,1,.8,1500,0)
assert math.isclose(profile['motoring_mechanical_wh'],profile['braking_mechanical_wh'],abs_tol=.001)
profile=scurve_profile(30,2,1,.8,1500,5000)
net=profile['motoring_mechanical_wh']-profile['braking_mechanical_wh']
assert math.isclose(net,5000*30/3600,abs_tol=.01)
assert len(profile['signed_mechanical_kw_samples'])==len(profile['samples'])
assert profile['peak_motoring_kw'] >= 0 and profile['peak_braking_kw'] <= 0
class Canvas:
    def __init__(self):self.lines=0;self.labels=0
    def delete(self,*_):pass
    def winfo_width(self):return 600
    def winfo_height(self):return 240
    def configure(self,**_):pass
    def create_text(self,*_,**kwargs):self.labels+=1
    def create_line(self,*_,**kwargs):self.lines+=1
canvas=Canvas()
draw_scurve_plot(canvas,profile,{'text':'black','border':'grey','accent':'blue',
                                 'background':'white','surface':'white'})
assert canvas.lines>=4 and canvas.labels>=5
print('KC↔계산값 연동·서로 다른 속도 구분·Enter·기계적 일 적분·그래프 확인')
