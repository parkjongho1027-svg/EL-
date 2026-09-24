"""화면 없이 입력 문자와 다이얼로그 부모 선택 경계를 검사."""
from ui_components import numeric_input_allowed, resolve_dialog_parent, set_dialog_root

assert numeric_input_allowed('50*1.1*6')
assert numeric_input_allowed('1.2e-3')
assert numeric_input_allowed('(1500+330)/2')
assert numeric_input_allowed('')  # 수정 중 빈칸 허용
assert numeric_input_allowed('100; 200; 300', list_mode=True)
for value in ('abc', 'math.sqrt(4)', '120\n500', '1;2'):
    assert not numeric_input_allowed(value)
assert not numeric_input_allowed('3' * 201)

class Root:
    def focus_get(self):
        return None

root = Root()
set_dialog_root(root)
assert resolve_dialog_parent() is root
child = object()
assert resolve_dialog_parent(child) is child
print('입력 문자 검증·대화창 부모 지정 확인')
