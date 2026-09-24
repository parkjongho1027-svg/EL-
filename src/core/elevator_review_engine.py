import math

# 검토 범위: 개별 KC 조항의 입력값 검사. 전체 승강기의 합격증명이 아니다.
KC_SOURCE = 'KC 2050-51:2022 (행정안전부 고시 별표 22)'
KC_URL = 'https://law.go.kr/LSW/flDownload.do?flSeq=141709087'
INTERNAL_NOTICE = '※ 법령상 판정이 아닌 프로그램 내부 설계검토 기준입니다.'


def review_guidance(topic, *, case=None, measured_ratio=None, failed_checks=()):
    """미충족 결과에 붙일 확인·재검토 선택지. 자동 설계변경 명령이 아니다.

    호출자는 해당 조건이 실제로 미충족일 때만 이 문구를 표시한다.
    각 선택지는 제조사 설계도서와 다른 안전조건의 영향 확인을 전제로 한다.
    """
    if topic == 'rope':
        return (
            '① 1가닥의 인증 최소 파단하중과 최하층 정격하중에서의 최대 장력 산정을 원자료와 대조하세요.',
            '② 제조사와 매다는 장치의 사양·가닥 수·하중 분담을 함께 재검토할 수 있습니다. 변경안은 도르래 직경비와 권상 조건도 다시 확인해야 합니다.',
        )
    if topic == 'traction':
        if case == 'stationary':
            return (
                '① 최고·최저 위치의 빈 카 조건과 장력·마찰계수·감긴각 산정을 제조사 도서와 대조하세요.',
                '② 과도한 권상 방지 방식과 전기안전장치의 작동을 함께 검토할 수 있습니다. 다른 두 조건과 반대 방향의 부등식입니다.',
            )
        return (
            '① 해당 조건의 최악 위치·부하·감속도를 반영했는지 장력과 마찰계수·감긴각의 근거를 재확인하세요.',
            '② 제조사와 권상 설계의 대안을 검토할 수 있습니다. 정지 조건의 권상 제한과 다른 안전조건도 함께 평가해야 합니다.',
        )
    if topic == 'speed':
        direction = '상한 초과' if measured_ratio is not None and measured_ratio > 105 else '하한 미달'
        return (
            f'① {direction}: 50% 적재, 중간 주행, 정격 전압·주파수 및 계측기 조건에서 재측정 여부를 검토하세요.',
            '② 같은 결과가 재현되면 제조사와 속도 제어 설정·구동계의 설계값을 대조하고, 조정안의 다른 안전조건 영향을 확인하세요.',
        )
    if topic == 'brake':
        labels = {'load':'125% 하강 정지시험', 'sets':'기계적 제동부품 2세트',
                  'failure':'한 세트 고장 시 감속·정지·유지', 'decel':'안전장치·완충기 감속도와의 비교'}
        items = ', '.join(labels[key] for key in failed_checks if key in labels)
        return (
            f'① 미충족으로 표시된 항목({items or "시험·구성 조건"})의 시험성적서와 설계도서를 대조하세요.',
            '② 제조사·자격을 갖춘 기술자와 제동계 구성 및 시험조건의 보완안을 검토하고 재시험 결과를 확인하세요.',
        )
    if topic == 'motor':
        return (
            '① 필요동력 계산에 사용한 정격하중·속도·오버밸런스율·효율과 단위를 먼저 확인하세요.',
            '② 계산값이 유지되면 제조사와 더 큰 정격용량 또는 다른 구동계 설계안을 검토하고 운전 정격·발열·제동·권상 조건을 함께 확인하세요.',
        )
    raise ValueError('지원하지 않는 검토 항목입니다.')

# 조항별 메타데이터. 법령 개정 시 이 표와 적용 함수를 함께 검토한다.
CRITERIA = {
    'rope_3_standard': {'id':'KC2050_51_9_2_2_A', 'title':'권상식 3가닥 이상 매다는 장치 안전율', 'source':KC_SOURCE,
                        'clause':'9.2.2 가', 'category':'LEGAL', 'comparison':'MIN', 'limit':12., 'unit':'-',
                        'required_inputs':('count','diameter_mm','breaking_n','force_n')},
    'rope_3_small': {'id':'KC2050_51_9_2_2_B', 'title':'권상식 3가닥 이상 6~8mm 미만 로프 안전율', 'source':KC_SOURCE,
                      'clause':'9.2.2 나', 'category':'LEGAL', 'comparison':'MIN', 'limit':16., 'unit':'-',
                      'required_inputs':('count','diameter_mm','breaking_n','force_n')},
    'rope_2': {'id':'KC2050_51_9_2_2_C', 'title':'권상식 2가닥 로프 안전율', 'source':KC_SOURCE,
               'clause':'9.2.2 다', 'category':'LEGAL', 'comparison':'MIN', 'limit':16., 'unit':'-',
               'required_inputs':('count','diameter_mm','breaking_n','force_n')},
    'running_speed': {'id':'KC2050_51_13_2_4', 'title':'실측속도 비율', 'source':KC_SOURCE,
                      'clause':'13.2.4', 'category':'LEGAL', 'comparison':'RANGE', 'limit':(92.,105.), 'unit':'%',
                      'required_inputs':('rated','measured','half_load_confirmed','midtravel_confirmed','supply_confirmed')},
    'brake_test': {'id':'KC2050_51_13_2_2_2_1', 'title':'전자기계 브레이크 증빙', 'source':KC_SOURCE,
                   'clause':'13.2.2.2.1', 'category':'LEGAL', 'comparison':'EVIDENCE', 'limit':None, 'unit':'-',
                   'required_inputs':('test_125','two_sets','single_failure','decel_checked')},
}


def compare_criterion(value, limit, comparison='MIN', warning_margin=None):
    """수치 비교의 결과와 기준 대비 여유율을 반환한다. 음수 여유는 미달이다."""
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (value, limit)) or limit <= 0:
        raise ValueError('계산값과 양수 기준값을 확인하세요.')
    if warning_margin is not None and (type(warning_margin) not in (int, float) or
                                       not math.isfinite(warning_margin) or warning_margin < 0):
        raise ValueError('내부 주의구간은 0 이상의 유한한 값이어야 합니다.')
    if comparison == 'MIN':
        margin = (value - limit) / limit * 100
        passed = value >= limit
    elif comparison == 'MAX':
        margin = (limit - value) / limit * 100
        passed = value <= limit
    else:
        raise ValueError('비교 유형은 MIN 또는 MAX여야 합니다.')
    engineering = '기준 미달' if not passed else ('한계 근접' if warning_margin is not None and margin <= warning_margin else '기준 충족')
    return {'status': 'COMPLIANT' if passed else 'NONCOMPLIANT', 'margin_pct': margin,
            'engineering': engineering,
            'engineering_notice': INTERNAL_NOTICE if engineering == '한계 근접' else None}


def evaluate_motor_capacity(required_kw, selected_kw):
    """전동기 설계용량의 단순 비교. KC 법정 판정과 분리한다."""
    if not all(math.isfinite(value) and value > 0 for value in (required_kw, selected_kw)):
        raise ValueError('필요동력과 선정 전동기 용량은 양수여야 합니다.')
    return {'adequate': selected_kw >= required_kw,
            'shortfall_kw': max(0., required_kw - selected_kw)}


def evaluate_rope_clause(drive_type, member_type, count, diameter_mm, breaking_n, force_n):
    """9.2.2 숫자 항목만 확인. 부속서 X 전체 평가나 인증을 대신하지 않는다."""
    if drive_type != 'traction':
        return {'status': 'NOT_APPLICABLE', 'reason': '권상 구동 로프 분기가 아닙니다. 다른 형식의 9.2.2 기준은 별도 검토하세요.'}
    if None in (count, diameter_mm, breaking_n, force_n):
        return {'status': 'INDETERMINATE', 'reason': '가닥 수, 공칭 직경, 1가닥 최소 파단하중 또는 최대 장력이 없습니다.'}
    if count != int(count) or count < 1 or diameter_mm <= 0 or breaking_n <= 0 or force_n <= 0:
        raise ValueError('가닥 수는 양의 정수, 직경·하중·장력은 양수여야 합니다.')
    if member_type != 'rope':
        return {'status': 'INDETERMINATE', 'reason': '벨트 등의 세부 분기는 제조사 자료와 부속서 X 대조가 필요합니다.'}
    if diameter_mm < 6:
        return {'status':'INDETERMINATE', 'reason':'공칭 직경 6 mm 미만은 적용 가능성과 부속서 X를 별도 확인해야 합니다.'}
    if count < 2:
        return {'status': 'NONCOMPLIANT', 'reason': '9.2.2 다: 권상 구동 매다는 장치는 2가닥 이상이 요구됩니다.', 'clause': '9.2.2 다'}
    # 나 항목은 3가닥, 6~8 mm 미만의 로프에 대해 16을 요구한다.
    if count >= 3 and 6 <= diameter_mm < 8:
        criterion=CRITERIA['rope_3_small']
    elif count >= 3:
        criterion=CRITERIA['rope_3_standard']
    else:
        criterion=CRITERIA['rope_2']
    limit, clause = criterion['limit'], criterion['clause']
    ratio = breaking_n / force_n
    result = compare_criterion(ratio, limit, criterion['comparison'])
    result.update(value=ratio, limit=limit, clause=clause,
                  reason='정격하중 카가 최하층에 정지한 조건의 1가닥 최소 파단하중/그 가닥 최대 힘만 비교했습니다. 부속서 X 추가 평가 필요.')
    return result


def evaluate_actual_speed(rated, measured, half_load_confirmed, midtravel_confirmed, supply_confirmed):
    if rated is None or measured is None or not all((half_load_confirmed, midtravel_confirmed, supply_confirmed)):
        return {'status': 'INDETERMINATE', 'reason': '13.2.4의 50% 적재·중간 주행·정격 전압/주파수 측정조건과 실측값이 필요합니다.'}
    if any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in (rated, measured)):
        raise ValueError('속도는 양수여야 합니다.')
    ratio = measured / rated * 100
    if not math.isfinite(ratio):
        raise ValueError('실측속도 비율의 숫자 범위를 확인하세요.')
    return {'status': 'COMPLIANT' if CRITERIA['running_speed']['limit'][0] <= ratio <= CRITERIA['running_speed']['limit'][1] else 'NONCOMPLIANT',
            'ratio_pct': ratio, 'margin_percentage_points': min(ratio-CRITERIA['running_speed']['limit'][0], CRITERIA['running_speed']['limit'][1]-ratio),
            'clause': '13.2.4', 'reason': '상승·하강 각각 측정해 독립 확인해야 합니다.'}


def evaluate_brake_evidence(test_125=None, two_sets=None, single_failure=None, decel_checked=None):
    evidence = (test_125, two_sets, single_failure, decel_checked)
    if any(x is False for x in evidence):
        return {'status': 'NONCOMPLIANT', 'reason': '제공된 시험 또는 구성 자료에서 미충족 항목이 확인되었습니다.', 'clause': '13.2.2.2.1'}
    if any(x is None for x in evidence):
        return {'status': 'INDETERMINATE', 'reason': '125% 하강 정지시험, 감속도 비교, 2세트, 단일세트 고장시험의 자료가 모두 필요합니다.', 'clause': '13.2.2.2.1'}
    return {'status': 'INDETERMINATE', 'reported': '입력상 모든 항목 충족', 'reason': '체크 표시만으로 시험기록과 실제 구성을 확인할 수 없습니다. 원본 시험기록을 대조해야 합니다.', 'clause': '13.2.2.2.1'}


def scurve_profile(distance, vmax, amax, jerk, moving_mass, imbalance_force=0, step=0.05):
    """대칭 7구간 저크 제한 궤적과 부호가 있는 단순화 기계동력."""
    from .errors import CalculationInputError, SimulationLimitError
    try:
        valid = (all(not isinstance(x,bool) and math.isfinite(x) and x > 0
                     for x in (distance,vmax,amax,jerk,moving_mass,step))
                 and not isinstance(imbalance_force,bool) and math.isfinite(imbalance_force))
    except (TypeError,ValueError,OverflowError):
        valid = False
    if not valid:
        raise CalculationInputError('거리·속도·가속도·저크·질량·시간간격은 유한한 양수여야 합니다.')
    def acceleration(v):
        tj = min(amax / jerk, math.sqrt(v / jerk))
        ta = max(0., v / (jerk*tj) - tj)
        return tj, ta, v*(2*tj+ta)
    tj, ta, min_distance = acceleration(vmax)
    vp = vmax
    if min_distance > distance:
        lo, hi = 0., vmax
        for _ in range(70):
            mid = (lo+hi)/2
            if acceleration(mid)[2] > distance:
                hi = mid
            else:
                lo = mid
        vp = (lo+hi)/2
        tj, ta, min_distance = acceleration(vp)
    tc = max(0., (distance-min_distance)/vp)
    duration_estimate = 2*(2*tj+ta)+tc
    if not math.isfinite(duration_estimate) or duration_estimate/step > 20000:
        raise SimulationLimitError('시뮬레이션은 최대 20,000개 시간 샘플까지 지원합니다. 거리·속도·시간 간격을 확인하세요.')
    phases = ((jerk,tj),(0.,ta),(-jerk,tj),(0.,tc),(-jerk,tj),(0.,ta),(jerk,tj))
    t=x=v=a=0.
    samples=[(0.,0.,0.,0.,0.)]
    signed_kw=[0.]
    motoring_wh=braking_wh=0.

    def positive_area(p0, p1, dt):
        """부호 변경 시 0 교차점을 나눠 양의 구간만 적분한다. kW·s 반환."""
        if p0 >= 0 and p1 >= 0:
            return (p0 + p1)*dt/2
        if p0 <= 0 and p1 <= 0:
            return 0.
        if p0 > 0:
            return p0*dt*(p0/(p0-p1))/2
        return p1*dt*(p1/(p1-p0))/2

    for j,duration in phases:
        remaining=duration
        while remaining > 1e-12:
            if len(samples) >= 20010:
                raise SimulationLimitError('시뮬레이션은 최대 20,000개 시간 샘플까지 지원합니다. 입력값을 확인하세요.')
            dt=min(step,remaining)
            x += v*dt + a*dt*dt/2 + j*dt**3/6
            v += a*dt + j*dt*dt/2
            a += j*dt
            t += dt
            power_kw=(moving_mass*a+imbalance_force)*v/1000
            if not all(math.isfinite(number) for number in (t,x,v,a,power_kw)):
                raise ValueError('운행 계산값이 너무 큽니다. 입력값을 확인하세요.')
            motoring_wh += positive_area(signed_kw[-1],power_kw,dt)*1000/3600
            braking_wh += positive_area(-signed_kw[-1],-power_kw,dt)*1000/3600
            signed_kw.append(power_kw)
            samples.append((t,x,max(0.,v),a,abs(power_kw)))
            remaining -= dt
    return {'duration_s':t,'peak_speed_m_s':vp,'cruise_s':tc,'samples':samples,
            'peak_mechanical_kw':max(row[4] for row in samples),
            'signed_mechanical_kw_samples':signed_kw,
            'peak_motoring_kw':max(signed_kw), 'peak_braking_kw':min(signed_kw),
            'motoring_mechanical_wh':motoring_wh,
            'braking_mechanical_wh':braking_wh}



def evaluate_traction_case(case, t1, t2, friction, wrap_rad):
    """부속서 IX의 세 조건을 별개 방향으로 비교한다. 모든 힘/마찰은 별도 산정해야 한다."""
    if None in (t1,t2,friction,wrap_rad):
        return {'status':'INDETERMINATE','reason':'최악 위치의 두 장력과 조건별 마찰계수 및 감긴각이 필요합니다.'}
    if any(not math.isfinite(x) or x <= 0 for x in (t1,t2,friction,wrap_rad)):
        raise ValueError('장력·마찰계수·감긴각은 양수여야 합니다.')
    if case not in ('load','emergency','stationary'):
        raise ValueError('알 수 없는 권상 조건입니다.')
    ratio=t1/t2
    try:
        limit=math.exp(friction*wrap_rad)
    except OverflowError:
        raise ValueError('마찰계수와 감긴각의 곱이 너무 큽니다.') from None
    if not math.isfinite(ratio):
        raise ValueError('장력비의 숫자 범위를 확인하세요.')
    if case=='stationary':
        margin=(ratio-limit)/limit*100
        satisfied=ratio>=limit
        sign='≥'
    else:
        margin=(limit-ratio)/limit*100
        satisfied=ratio<=limit
        sign='≤'
    return {'status':'조건식 충족' if satisfied else '조건식 미충족',
            'legal_status':'INDETERMINATE', 'ratio':ratio,'limit':limit,
            'margin_pct':margin,'comparison':sign,
            'reason':'입력한 T1/T2·f·α의 산정과 최악 조건은 제조사 설계도서·부속서 IX와 대조해야 합니다.'}
