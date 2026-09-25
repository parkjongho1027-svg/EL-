"""화면과 무관한 계산식의 정상·입력오류·내부오류 경계를 확인합니다."""
import math
from src.core.calculators import (calculate_motor_value, calculate_traction_values,
                         calculate_brake_values, calculate_traffic_values)
from src.common.utils import calculate_safely, parse_number, require_calculation
from src.core.elevator_review_engine import (INTERNAL_NOTICE, compare_criterion,
                                    evaluate_actual_speed, evaluate_traction_case)

motor = {'Q': 1500, 'V': 180, 'OB': .45, 'eff': .8}
assert math.isclose(calculate_motor_value('P', motor), 30.330882352941178)
for invalid in ({**motor, 'eff': 0}, {**motor, 'eff': math.nan},
                {**motor, 'V': -5}, {**motor, 'OB': 1}, {**motor, 'Q': '잘못된 값'}):
    result = calculate_safely(calculate_motor_value, 'P', invalid)
    assert result.value is None and result.error.startswith('입력값 오류:')

traction = {'Q': 1500, 'Wc': 2400, 'H': 50, 'wr': 1.1,
            'n': 6, 'OB': 45, 'Wcomp': 0, 'Wm': 0}
assert math.isclose(calculate_traction_values(traction)['final'], 1.41875)
assert calculate_safely(calculate_traction_values, {**traction, 'n': 0}).error
assert calculate_safely(calculate_traction_values, {**traction, 'wr': math.inf}).error

brake = calculate_brake_values(v=3, t=.6)
assert math.isclose(brake['a'], 5)
assert calculate_safely(calculate_brake_values, v=3, t=0).error
assert calculate_safely(calculate_brake_values, v=3, t=math.nan).error

traffic = {'A': 500, 'F': 10, 'S': 10, 'phi': .15,
           'C': 15, 'board_rate': .8, 'n': 10,
           'td': 4, 'tp': 1, 'Tr_travel': 60}
assert calculate_traffic_values(traffic)['recommended'] >= 1
assert calculate_safely(calculate_traffic_values, {**traffic, 'board_rate': 0}).error
assert calculate_safely(calculate_traffic_values, {**traffic, 'n': 0}).error
assert calculate_safely(calculate_traffic_values, {**traffic, 'Tr_travel': math.inf}).error

assert math.isclose(parse_number('50*1.1*6', '로프 중량'), 330)
assert calculate_safely(parse_number, '1/0', '예시').error
assert calculate_safely(parse_number, 'True', '예시').error
assert calculate_safely(lambda: math.inf).error
assert require_calculation(calculate_safely(lambda x: x + 1, 4)) == 5
assert compare_criterion(12.2, 12, warning_margin=2)['engineering_notice'] == INTERNAL_NOTICE
assert compare_criterion(11, 12, warning_margin=2)['engineering_notice'] is None
assert math.isclose(compare_criterion(1.5, 2, 'MAX')['margin_pct'], 25)
assert calculate_safely(compare_criterion, 12, 12, warning_margin=-1).error
assert calculate_safely(evaluate_actual_speed, 2, math.nan, True, True, True).error
assert calculate_safely(evaluate_traction_case, 'load', 2, 1, 1000, 1000).error
assert evaluate_traction_case('stationary', 3, 1, .2, 3)['comparison'] == '≥'

unexpected = calculate_safely(lambda: (_ for _ in ()).throw(RuntimeError('내부 오류')))
assert unexpected.value is None and unexpected.unexpected is not None
try:
    require_calculation(unexpected)
except RuntimeError:
    pass
else:
    raise AssertionError('예상치 못한 오류가 기록 경로로 전달되지 않았습니다.')
print('네 계산식 정상 결과·유효하지 않은 입력·예상치 못한 오류 분리 확인')
