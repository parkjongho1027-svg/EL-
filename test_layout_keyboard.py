"""화면 없이 카드 배치와 Tab 입력값 교체 동작을 점검."""
from types import SimpleNamespace
from types import MethodType
from main import (INTEGRATED_RESULT_CELLS, ElevatorApp,
                  focus_input_for_replacement)

assert INTEGRATED_RESULT_CELLS == (
    (0, 0), (0, 1), (1, 0), (1, 1), (0, 2), (1, 2))

class Entry:
    def __init__(self, text):
        self.text = text
        self.selected = None
        self.focused = False
    def cget(self, option):
        return 'normal'
    def winfo_viewable(self):
        return True
    def focus_set(self):
        self.focused = True
    def selection_range(self, start, end):
        self.selected = (start, end)
    def icursor(self, position):
        self.cursor = position

first, second = Entry('120'), Entry('30')
third = Entry('70')
criteria = SimpleNamespace(entries={'count': first, 'diameter': second},
                           traction_entries={('load','t1'): third})
app = SimpleNamespace(criteria_panel=criteria,scurve_panel=None,_tab_after_enter=None)
app._visible_inputs = MethodType(ElevatorApp._visible_inputs,app)
app._focus_first_input = MethodType(ElevatorApp._focus_first_input,app)
app._move_to_next_tab = MethodType(ElevatorApp._move_to_next_tab,app)
assert ElevatorApp._focus_adjacent_input(app, criteria, first) == 'break'
assert second.focused and second.selected == (0, 'end')
assert ElevatorApp._focus_adjacent_input(app, criteria, second) == 'break'
assert third.focused and third.selected == (0, 'end')
first.focused = False
ElevatorApp._focus_first_input(app, criteria)
assert first.focused and first.selected == (0, 'end')
plain = Entry('기존값')
focus_input_for_replacement(plain)
assert plain.selected == (0, 'end')

class Tabs:
    def __init__(self,selected,count):
        self.selected=selected;self.count=count
    def select(self,index=None):
        if index is not None:self.selected=index
        return self.selected
    def index(self,index):
        return self.count if index=='end' else index

mechanical=Entry('30');energy=Entry('1000');csv=Entry('record.csv')
simulator=SimpleNamespace(entries={'distance':mechanical},
    energy_entries={'car_mass':energy},measurement_paths={'reference':csv},
    mode_tabs=Tabs(0,2))
motor=SimpleNamespace(entries={'Q':Entry('1500'),'V':Entry('2')})
app.scurve_panel=simulator
app.panels=[motor,*[SimpleNamespace(entries={'v':Entry('2')}) for _ in range(3)]]
app.notebook=Tabs(5,6)
app.root=SimpleNamespace(after_idle=lambda callback:callback())
assert ElevatorApp._focus_adjacent_input(app,simulator,mechanical)=='break'
assert simulator.mode_tabs.selected==1 and energy.selected==(0,'end')
assert ElevatorApp._focus_adjacent_input(app,simulator,energy)=='break'
assert csv.selected==(0,'end')
assert ElevatorApp._focus_adjacent_input(app,simulator,csv)=='break'
assert app.notebook.selected==0 and motor.entries['Q'].selected==(0,'end')
assert ElevatorApp._focus_adjacent_input(app,simulator,energy,-1)=='break'
assert simulator.mode_tabs.selected==0 and mechanical.selected==(0,'end')

# 계산 전 Tab은 다음 입력칸, Enter로 계산한 직후 Tab은 다음 계산 탭.
app.notebook.select(0)
assert ElevatorApp._focus_adjacent_input(app,motor,motor.entries['Q'])=='break'
assert app.notebook.selected==0 and motor.entries['V'].selected==(0,'end')
ElevatorApp._mark_calculated_input(app,motor,motor.entries['Q'])
assert ElevatorApp._focus_adjacent_input(app,motor,motor.entries['Q'])=='break'
assert app.notebook.selected==1 and app.panels[1].entries['v'].selected==(0,'end')
app.notebook.select(5)
ElevatorApp._mark_calculated_input(app,simulator,mechanical)
assert ElevatorApp._focus_adjacent_input(app,simulator,mechanical)=='break'
assert app.notebook.selected==0 and motor.entries['Q'].selected==(0,'end')
print('Tab 입력칸 선택 및 Enter 계산 후 다음 계산 탭 선택 확인')
