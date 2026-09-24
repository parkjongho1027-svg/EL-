"""조항 입력 판정의 산술/증빙 경계. 법령 원문 일치의 독립 검증은 아님."""
import math

import pytest

from src.core.elevator_review_engine import (
    compare_criterion, evaluate_actual_speed, evaluate_brake_evidence,
    evaluate_motor_capacity, evaluate_rope_clause, evaluate_traction_case,
    review_guidance,
)


@pytest.mark.parametrize('value,limit,mode,status,margin', [
    (12, 12, 'MIN', 'COMPLIANT', 0),
    (11, 12, 'MIN', 'NONCOMPLIANT', -100/12),
    (105, 105, 'MAX', 'COMPLIANT', 0),
    (106, 105, 'MAX', 'NONCOMPLIANT', -100/105),
])
def test_threshold_margin(value, limit, mode, status, margin):
    result = compare_criterion(value, limit, mode)
    assert result['status'] == status
    assert result['margin_pct'] == pytest.approx(margin)


@pytest.mark.parametrize('diameter,count,limit,clause', [
    (8, 3, 12, '9.2.2 가'),
    (6, 3, 16, '9.2.2 나'),
    (8, 2, 16, '9.2.2 다'),
])
def test_rope_selection_and_boundary(diameter, count, limit, clause):
    ratio = limit
    result = evaluate_rope_clause('traction', 'rope', count, diameter, ratio*1000, 1000)
    assert result['status'] == 'COMPLIANT'
    assert result['clause'] == clause
    assert result['value'] == pytest.approx(limit)


def test_rope_missing_unsupported_and_under_limit():
    assert evaluate_rope_clause('traction', 'rope', 3, 8, None, 1000)['status'] == 'INDETERMINATE'
    assert evaluate_rope_clause('traction', 'belt', 3, 8, 12000, 1000)['status'] == 'INDETERMINATE'
    assert evaluate_rope_clause('traction', 'rope', 3, 8, 11999, 1000)['status'] == 'NONCOMPLIANT'


@pytest.mark.parametrize('ratio,status', [(92, 'COMPLIANT'), (105, 'COMPLIANT'),
                                           (91.99, 'NONCOMPLIANT'), (105.01, 'NONCOMPLIANT')])
def test_measured_speed_at_both_limits(ratio, status):
    result = evaluate_actual_speed(100, ratio, True, True, True)
    assert result['status'] == status
    assert result['ratio_pct'] == pytest.approx(ratio)


def test_missing_speed_evidence_and_brake_evidence():
    assert evaluate_actual_speed(100, 100, False, True, True)['status'] == 'INDETERMINATE'
    assert evaluate_brake_evidence(True, True, True, True)['status'] == 'INDETERMINATE'
    assert evaluate_brake_evidence(True, False, True, True)['status'] == 'NONCOMPLIANT'
    assert evaluate_brake_evidence(True, None, True, True)['status'] == 'INDETERMINATE'


@pytest.mark.parametrize('case,ratio,passes', [
    ('load', 1.5, True), ('emergency', 3, False),
    ('stationary', 3, True), ('stationary', 1.5, False),
])
def test_traction_comparison_direction(case, ratio, passes):
    # f·alpha = ln(2), so the exact reference bound is 2.
    result = evaluate_traction_case(case, ratio*1000, 1000, math.log(2), 1)
    assert result['status'] == ('조건식 충족' if passes else '조건식 미충족')
    assert result['legal_status'] == 'INDETERMINATE'
    assert result['limit'] == pytest.approx(2)


def test_traction_missing_data_is_undetermined():
    assert evaluate_traction_case('load', None, 1000, .3, 2)['status'] == 'INDETERMINATE'


@pytest.mark.parametrize('topic,kwargs,anchor', [
    ('rope', {}, '장력'),
    ('traction', {'case': 'load'}, '최악 위치'),
    ('traction', {'case': 'stationary'}, '빈 카'),
    ('speed', {'measured_ratio': 106}, '상한 초과'),
    ('speed', {'measured_ratio': 91}, '하한 미달'),
    ('brake', {'failed_checks': ('load',)}, '125%'),
    ('motor', {}, '필요동력'),
])
def test_failed_review_guidance_names_relevant_evidence(topic, kwargs, anchor):
    instructions = review_guidance(topic, **kwargs)
    assert len(instructions) == 2
    assert anchor in ' '.join(instructions)


def test_unknown_review_guidance_is_rejected():
    with pytest.raises(ValueError, match='지원하지 않는'):
        review_guidance('unknown')


def test_comparisons_do_not_return_infinite_margins():
    with pytest.raises(ValueError, match='여유율'):
        compare_criterion(1e308, 1e-308)
    with pytest.raises(ValueError, match='마찰계수'):
        evaluate_traction_case('load', 2, 1, 1e308, 1e308)
    with pytest.raises(ValueError, match='여유율'):
        evaluate_traction_case('load', 1e308, 1, 1e-308, 1)


def test_motor_comparison_is_design_only_and_reports_shortfall():
    insufficient = evaluate_motor_capacity(12.7, 10)
    adequate = evaluate_motor_capacity(12.7, 15)
    assert insufficient == {'adequate': False, 'shortfall_kw': pytest.approx(2.7)}
    assert adequate == {'adequate': True, 'shortfall_kw': 0}
    with pytest.raises(ValueError, match='양수'):
        evaluate_motor_capacity(12.7, 0)


def test_unsupported_drive_and_small_rope_are_not_auto_certified():
    args = ('rope', 3, 8, 16000, 1000)
    assert evaluate_rope_clause('hydraulic', *args)['status'] == 'NOT_APPLICABLE'
    assert evaluate_rope_clause('traction', 'rope', 3, 5.9, 16000, 1000)['status'] == 'INDETERMINATE'
    assert evaluate_rope_clause('traction', 'rope', 1, 8, 16000, 1000)['status'] == 'NONCOMPLIANT'
    with pytest.raises(ValueError, match='양의 정수'):
        evaluate_rope_clause('traction', 'rope', 0, 8, 16000, 1000)


def test_criterion_inputs_and_speed_evidence_reject_invalid_numbers():
    with pytest.raises(ValueError):
        compare_criterion(2, 0)
    with pytest.raises(ValueError, match='비교 유형'):
        compare_criterion(2, 1, 'RANGE')
    with pytest.raises(ValueError, match='속도'):
        evaluate_actual_speed(2, float('nan'), True, True, True)
