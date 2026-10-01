"""추적 가능한 전동기 부품 DB 기록과 검색을 담당하는 계산 보조 모듈.

제조사 자료에 토크·속도·관성이 빠져 있는 경우가 있으므로,
확인되지 않은 값을 0으로 만들지 않고 미확인(None) 상태로 보존한다.
"""

import math
from src.core.errors import CalculationInputError

REQUIRED_FIELDS = ("maker", "model", "rated_power_kw", "source", "verified_date")
OPTIONAL_NUMERIC_FIELDS = ("rated_torque_nm", "rated_speed_rpm", "inertia_kg_m2")
ALIASES = {
    "manufacturer": "maker",
    "rotor_inertia_kg_m2": "inertia_kg_m2",
}


def _normalise_aliases(data):
    """예전 파일의 항목명을 현재 항목명으로 맞춘다."""
    result = dict(data)
    for old, new in ALIASES.items():
        if new not in result and old in result:
            result[new] = result[old]
    return result


def _positive_number(value, key, *, optional=False):
    """숫자 항목이 유한한 양수인지 확인하고, 선택 항목은 빈값을 허용한다."""
    if optional and (value is None or (isinstance(value, str) and not value.strip())):
        return None
    if isinstance(value, bool):
        raise CalculationInputError(f"{key}: 유한한 양수가 필요합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise CalculationInputError(f"{key}: 숫자 또는 미확인(null/빈칸)이 필요합니다.") from error
    if not math.isfinite(number) or number <= 0:
        raise CalculationInputError(f"{key}: 유한한 양수가 필요합니다.")
    return number


def validate_motor_record(data):
    """불러온 전동기 한 건의 필수값과 숫자 범위를 검사한다."""
    if not isinstance(data, dict):
        raise CalculationInputError("전동기 DB 항목은 객체여야 합니다.")
    data = _normalise_aliases(data)
    missing = [key for key in REQUIRED_FIELDS if key not in data]
    if missing:
        raise CalculationInputError("전동기 DB 필수 항목 누락: " + ", ".join(missing))

    result = {}
    for key in ("maker", "model", "source", "verified_date"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise CalculationInputError(f"{key}: 값을 입력하세요.")
        result[key] = value.strip()[:500]

    result["rated_power_kw"] = _positive_number(data.get("rated_power_kw"), "rated_power_kw")
    for key in OPTIONAL_NUMERIC_FIELDS:
        result[key] = _positive_number(data.get(key), key, optional=True)

    # 이후 버전에서 사용하는 선택 항목도 버리지 않고 그대로 보존한다.
    for key in (
        "roping_ratio", "rated_load_kg", "car_speed_m_s", "traction_sheave_diameter_mm",
        "source_url", "note",
    ):
        if key in data:
            result[key] = data[key]
    return result


def motor_matches(records, power_kw, required_torque_nm=None, tolerance=1e-6):
    """필요 출력과 맞는 전동기를 찾고, 토크 자료가 있으면 함께 검토한다."""
    matches = []
    for item in records:
        payload = item.get("payload", item)
        try:
            motor = validate_motor_record(payload)
        except CalculationInputError:
            continue
        if abs(motor["rated_power_kw"] - float(power_kw)) <= tolerance:
            torque = motor.get("rated_torque_nm")
            if required_torque_nm is None:
                motor["torque_status"] = "not_required"
                motor["torque_ok"] = True
            elif torque is None:
                motor["torque_status"] = "unknown"
                motor["torque_ok"] = None
            elif torque >= float(required_torque_nm):
                motor["torque_status"] = "pass"
                motor["torque_ok"] = True
            else:
                motor["torque_status"] = "fail"
                motor["torque_ok"] = False
            matches.append(motor)
    return matches
