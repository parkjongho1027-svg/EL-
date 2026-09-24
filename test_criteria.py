from types import SimpleNamespace
from main import CriteriaPanel
class E:
 def __init__(self,x):self.x=str(x)
 def get(self):return self.x
class V:
 def __init__(self,x):self.x=x
 def get(self):return self.x
class Fake:
 def __init__(self):
  self.entries={k:E(v) for k,v in {'count':3,'diameter':8,'breaking':100000,'force':10000,
    'rated':2,'measured_up':2.2,'measured_down':2,'selected_motor':10}.items()}
  self.traction_entries={(case,key):E(v) for case,data in {
    'load':(2,1,.2,3),'emergency':(1.2,1,.2,3),'stationary':(1.2,1,.2,3)
  }.items() for key,v in zip(('t1','t2','f','alpha'),data)}
  self.drive=V('권상식');self.speed_conditions=V(True)
  self.brake_checks={k:V('미충족 증빙' if k=='load' else '자료 없음') for k in ('load','sets','failure','decel')}
  self.root=SimpleNamespace(_elevator_app=SimpleNamespace(
    motor_panel=SimpleNamespace(entries={'P':E(12.7)},_target_key=lambda:'P')))
  self.output=''
 def winfo_toplevel(self):return self.root
 def _show(self,text,**kwargs):self.output=text
 def capture_state(self):return {'count':self.entries['count'].get()}
 def _remember(self,*_):pass
f=Fake();CriteriaPanel.calculate(f)
assert f.output.count('[권장 검토')==6,f.output
assert '브레이크' in f.output and '속도' in f.output
assert '카·균형추 정지' in f.output and '반대 방향' in f.output
print('로프·적재/정지 권상·속도·브레이크·전동기 부족 안내 표시 확인')
