"""프로젝트 저장 직전 여섯 화면의 공통값 우선순위와 사본 보존."""
from src.ui.project_snapshot import merge_project_states


def states():
    return {
        'motor': {'values': {'Q': '1000', 'OB': '40', 'V': '120'}, 'units': {'V': 'm/min'}},
        'traction': {'values': {'Q': '800', 'OB': '45', 'Wc': '1400', 'n': '6'}},
        'brake': {'values': {'v': '2'}},
        'traffic': {'values': {'F': '12'}},
        'criteria': {'count': '8', 'rated': '2.5', '__drive__': '권상식'},
        'scurve': {'_energy': {'load_mass': '300'}},
    }


def test_active_motor_speed_unit_and_six_panels_are_preserved():
    original = states()
    saved, common = merge_project_states(original, 'motor')
    assert set(saved) == set(original)
    assert common['speed_m_s'] == 2
    assert saved['motor']['values']['Q'] == saved['traction']['values']['Q'] == '1000'
    assert saved['criteria']['rated'] == '2'
    assert common['rope_count'] == 6
    assert original['traction']['values']['Q'] == '800'
    assert original['criteria']['rated'] == '2.5'


def test_active_criteria_override_respects_rope_type():
    original = states()
    saved, common = merge_project_states(original, 'criteria')
    assert common['speed_m_s'] == 2.5
    assert common['rope_count'] == 8
    assert saved['motor']['values']['V'] == '150'
    assert saved['traction']['values']['n'] == '8'
    original['criteria']['__drive__'] = '유압식'
    saved, common = merge_project_states(original, 'criteria')
    assert common['rope_count'] == 6
    assert saved['criteria']['count'] == '8'
