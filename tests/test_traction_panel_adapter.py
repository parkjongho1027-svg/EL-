"""트랙션 화면 어댑터가 계산 결과와 입력 오류를 구분한다."""
from types import SimpleNamespace

from src.ui.traction_panel import IntegratedTractionPanel


class Entry:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def make_panel():
    messages = []
    records = []
    errors = []
    entries = {key: Entry(value) for key, value in {
        'Q': '1500', 'Wc': '2400', 'H': '50', 'wr': '1.1',
        'n': '6', 'OB': '45', 'Wcomp': '0', 'Wm': '0',
    }.items()}
    panel = SimpleNamespace(
        entries=entries,
        services=SimpleNamespace(widget_language=lambda _: 'ko',
                                 log_unexpected_error=lambda *args: errors.append(args),
                                 show_unexpected_error=lambda *args: errors.append(args)),
        _remember=lambda *args: records.append(args),
        _show=lambda msg, error=False: messages.append((msg, error)),
    )
    return panel, messages, records, errors


def test_traction_adapter_uses_larger_ratio_without_mutating_entries():
    panel, messages, records, errors = make_panel()
    IntegratedTractionPanel.calculate(panel)
    assert '최종 트랙션비 = 1.4187' in messages[-1][0] or '최종 트랙션비 = 1.4188' in messages[-1][0]
    assert panel.entries['Q'].get() == '1500'
    assert len(records) == 1 and not errors


def test_traction_adapter_rejects_fractional_rope_count():
    panel, messages, records, errors = make_panel()
    panel.entries['n'].value = '6.5'
    IntegratedTractionPanel.calculate(panel)
    assert messages[-1][1] is True
    assert '정수' in messages[-1][0]
    assert not records and not errors
