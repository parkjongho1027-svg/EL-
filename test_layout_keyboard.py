"""화면 없이 카드 배치와 Tab 입력값 교체 동작을 점검."""
from types import SimpleNamespace
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
app = SimpleNamespace(criteria_panel=criteria)
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
print('4분할+오른쪽 세로 배치·Tab 이동 시 값 전체 선택 확인')
