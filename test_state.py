import json, tempfile
from pathlib import Path
from types import SimpleNamespace
from main import CriteriaPanel, SCurvePanel, PersistentStore, ElevatorApp
class Entry:
    def __init__(self,value=''):self.value=value
    def get(self):return self.value
    def delete(self,*_):self.value=''
    def insert(self,_,value):self.value=str(value)
class Var:
    def __init__(self,value):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value
class Button:
    def config(self,**kwargs):pass
with tempfile.TemporaryDirectory() as td:
    store=PersistentStore.__new__(PersistentStore)
    store.path=Path(td)/'data.json';store.save_warning='';store.on_save_error=None;store._save_error_reported=''
    store.data={'calculators':{k:{'previous':None,'history':[]} for k in ('motor','traction','brake','traffic','criteria','scurve')},'projects':[]}
    c=CriteriaPanel.__new__(CriteriaPanel)
    c.store=store;c.storage_key='criteria';c.entries={'count':Entry('3'),'rated':Entry('2')}
    c.traction_entries={('load','t1'):Entry('150'),('stationary','alpha'):Entry('3.14')}
    c.drive=Var('권상식');c.speed_conditions=Var(True);c.brake_checks={'load':Var('충족 증빙')}
    c.previous_button=Button();c.history_button=Button();c.undo_stack=[]
    c.capture_state=lambda:CriteriaPanel.capture_state(c)
    state=c.capture_state()
    CriteriaPanel._remember(c,'검토 저장 테스트')
    assert store.history('criteria')[0]['load_t1']=='150'
    assert store.previous('criteria')['__speed_conditions__'] is True
    CriteriaPanel.apply_state(c,{},remember_undo=False)
    assert c.entries['count'].get()==''
    CriteriaPanel.apply_state(c,store.previous('criteria'),remember_undo=False)
    assert c.capture_state()==state
    s=SCurvePanel.__new__(SCurvePanel);s.entries={'distance':Entry('30'),'jerk':Entry('0.8')};s.undo_stack=[]
    s.capture_state=lambda:SCurvePanel.capture_state(s)
    sim_state=s.capture_state();SCurvePanel.apply_state(s,{},remember_undo=False)
    SCurvePanel.apply_state(s,sim_state,remember_undo=False)
    assert s.capture_state()==sim_state
    data=json.loads(store.path.read_text())
    assert data['calculators']['criteria']['history'][0]['__brake_load__']=='충족 증빙'
print('기준 검토 기록·이전값·프로젝트 입력 구조·시뮬레이션 상태 복원 확인')

class SnapshotPanel:
    def __init__(self,state):self.state=state;self.saved=None
    def capture_state(self):return self.state
    def apply_state(self,state):self.saved=state
    def calculate(self):pass
class Notebook:
    def select(self):return 'criteria-tab'
    def index(self,_):return 4
app=SimpleNamespace(
    notebook=Notebook(),motor_panel=SnapshotPanel({'values':{'Q':'1000','OB':'50','V':'120'},'units':{'V':'m/min'}}),
    traction_panel=SnapshotPanel({'values':{'Q':'1000','OB':'50','Wc':'1500'}}),
    brake_panel=SnapshotPanel({'values':{'v':'2'},'speed_unit':'m/s'}),
    traffic_panel=SnapshotPanel({'building_use':'user'}),
    criteria_panel=SnapshotPanel(state),scurve_panel=SnapshotPanel(sim_state),
    _auto_filled_values={},store=SimpleNamespace(_suppress_history=False),language='ko',
    _state_number=ElevatorApp._state_number,
    _mark_project_common_values_as_linked=lambda:None)
states,common=ElevatorApp._project_snapshot(app)
assert set(states)=={'motor','traction','brake','traffic','criteria','scurve'}
assert states['criteria']['load_t1']=='150' and states['scurve']['distance']=='30'
# Suppress UI-only banners; verify old and new panels all receive their saved state.
import main
main.show_input_status=lambda *_args:None
ElevatorApp.apply_project(app,{'id':'test','name':'test','states':states})
assert app.criteria_panel.saved==states['criteria']
assert app.scurve_panel.saved==states['scurve']
assert all(p.saved is not None for p in (app.motor_panel,app.traction_panel,app.brake_panel,app.traffic_panel))
print('프로젝트 여섯 탭 저장·불러오기 확인')
