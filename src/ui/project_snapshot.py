"""여섯 화면의 프로젝트 입력값 동기화. Tk 객체는 전달하지 않는다."""
import copy
from src.common.utils import clean_number_text, parse_number


def _state_number(state, key):
    raw = state.get("values", {}).get(key, "")
    if str(raw).strip() == "":
        return None
    try:
        return parse_number(raw, key)
    except ValueError:
        return None


def merge_project_states(source_states, active_key):
    """프로젝트 저장용 사본의 공통 입력을 현재 탭 우선으로 정리한다."""
    states = copy.deepcopy(source_states)
    motor = states["motor"]
    traction = states["traction"]
    criteria = states["criteria"]

    def first_value(candidates):
        ordered = sorted(candidates, key=lambda item: item[0] != active_key)
        for source, state, key in ordered:
            value = _state_number(state, key)
            if value is not None:
                return value
        return None

    q_value = first_value((("motor", motor, "Q"), ("traction", traction, "Q")))
    ob_value = first_value((("motor", motor, "OB"), ("traction", traction, "OB")))
    wc_value = _state_number(traction, "Wc")
    rope_count = _state_number(traction, "n")
    if active_key == "criteria" and criteria.get("__drive__", "권상식") == "권상식":
        rope_count = _state_number({"values": criteria}, "count") or rope_count

    speed_ms = None
    motor_speed = _state_number(motor, "V")
    criteria_speed = _state_number({"values": criteria}, "rated")
    if active_key == "criteria" and criteria_speed is not None:
        speed_ms = criteria_speed
    elif motor_speed is not None:
        speed_ms = motor_speed / (60 if motor.get("units", {}).get("V") == "m/min" else 1)
    elif criteria_speed is not None:
        speed_ms = criteria_speed

    if q_value is not None:
        motor["values"]["Q"] = clean_number_text(q_value)
        traction["values"]["Q"] = clean_number_text(q_value)
    if ob_value is not None:
        motor["values"]["OB"] = clean_number_text(ob_value)
        traction["values"]["OB"] = clean_number_text(ob_value)
    if speed_ms is not None:
        motor_factor = 60 if motor.get("units", {}).get("V") == "m/min" else 1
        if not str(motor["values"].get("V", "")).strip() or active_key == "criteria":
            motor["values"]["V"] = clean_number_text(speed_ms * motor_factor)
        if not str(criteria.get("rated", "")).strip() or active_key == "motor":
            criteria["rated"] = clean_number_text(speed_ms)
    if rope_count is not None:
        if not str(traction["values"].get("n", "")).strip() or active_key == "criteria":
            traction["values"]["n"] = clean_number_text(rope_count)
        if criteria.get("__drive__", "권상식") == "권상식" and (
                not str(criteria.get("count", "")).strip() or active_key == "traction"):
            criteria["count"] = clean_number_text(rope_count)
    common = {"Q": q_value, "OB": ob_value, "Wc": wc_value,
              "speed_m_s": speed_ms, "rope_count": rope_count}
    return states, common
