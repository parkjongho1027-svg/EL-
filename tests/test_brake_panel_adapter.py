"""브레이크 화면이 순수 계산값을 표시하고 오류를 서비스로 전달한다."""
from types import MethodType, SimpleNamespace

from src.ui.brake_panel import BrakePanel


class Entry:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class Unit:
    def get(self):
        return 'm/s'


def make_panel():
    messages = []
    records = []
    errors = []
    panel = SimpleNamespace(
        entries={'v': Entry('3'), 't': Entry('0.6'),
                 'd': Entry(''), 'a': Entry('')},
        speed_unit=Unit(),
        services=SimpleNamespace(widget_language=lambda _: 'ko',
                                 show_unexpected_error=lambda *args: errors.append(args)),
        _show=lambda msg, error=False: messages.append((msg, error)),
        _remember_input=lambda value: records.append(value),
    )
    panel._get = MethodType(BrakePanel._get, panel)
    return panel, messages, records, errors


def test_brake_panel_calculation_outputs_units_and_keeps_inputs():
    panel, messages, records, errors = make_panel()
    BrakePanel.calculate(panel)
    assert not errors
    assert '제동거리 d = 0.9000 m' in messages[-1][0]
    assert '감속도 a = 5.0000 m/s²' in messages[-1][0]
    assert panel.entries['d'].get() == ''
    assert len(records) == 1


def test_brake_panel_invalid_value_preserves_inputs():
    panel, messages, records, errors = make_panel()
    panel.entries['t'].value = '0'
    BrakePanel.calculate(panel)
    assert messages[-1][1] is True
    assert '0보다 큰' in messages[-1][0]
    assert not records and not errors


def test_brake_panel_unexpected_error_is_logged_via_service():
    panel, messages, records, errors = make_panel()
    panel._get = lambda _: (_ for _ in ()).throw(RuntimeError('internal'))
    BrakePanel.calculate(panel)
    assert len(errors) == 1
    assert errors[0][0] is panel
    assert isinstance(errors[0][-1], RuntimeError)
