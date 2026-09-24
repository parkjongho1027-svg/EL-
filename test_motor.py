from types import SimpleNamespace
from main import SolverPanel, calculate_motor_value
from elevator_review_engine import evaluate_motor_capacity, review_guidance
class E:
 def __init__(self,value=''):self.value=value
 def get(self):return self.value
 def config(self,**kw):pass
 def delete(self,*_):self.value=''
 def insert(self,_,value):self.value=str(value)
class V:
 def get(self):return 'm/s'
class Motor:
 storage_key='motor'
 vars_spec=[{'key':'P','label':'전동기 용량 P','unit':'kW'},
            {'key':'Q','label':'적재하중 Q','unit':'kg'},
            {'key':'V','label':'정격속도 V','unit_factors':{'m/s':60,'m/min':1}},
            {'key':'OB','label':'오버밸런스율 OB','percent':True},
            {'key':'eff','label':'전체효율 η','percent':True}]
 def __init__(self):
  self.entries={k:E(v) for k,v in {'P':'','Q':'1000','V':'1.5','OB':'40','eff':'80'}.items()}
  self.unit_vars={'V':V()};self.formulas={'P':lambda values:calculate_motor_value('P',values)}
  self.input_validator=None;self.result_validator=None;self.result=''
  self.root=SimpleNamespace(_language='ko',_elevator_app=SimpleNamespace(
      criteria_panel=SimpleNamespace(entries={'selected_motor':E('10')})))
 def winfo_toplevel(self):return self.root
 def _target_key(self):return 'P'
 def capture_state(self):return {}
 def _remember_input(self,*_):pass
 def _show(self,text,**_):self.result=text
m=Motor()
SolverPanel.calculate(m)
assert '[계산 과정]' in m.result and '▶' in m.result
assert '[설계용량]' not in m.result and '법정 적합' not in m.result
m.root._elevator_app.criteria_panel.entries['selected_motor'].value='15'
SolverPanel.calculate(m)
assert '설계용량 충족' not in m.result and '[권장 검토]' not in m.result
assert evaluate_motor_capacity(12.7,15)['adequate']
assert not evaluate_motor_capacity(12.7,10)['adequate']
assert '반대 방향' in ' '.join(review_guidance('traction',case='stationary'))
print('전동기 탭은 계산값만 출력·선정용량 비교는 기준 검토로 분리 확인')
