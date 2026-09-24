"""전동기·트랙션·브레이크·교통량의 순수 계산식. UI 독립."""
import math
from typing import Mapping
from errors import CalculationInputError


def _number(value: object, label: str, *, allow_zero: bool=False) -> float:
    """계산 모듈의 직접 호출에도 형식·범위 오류를 명확하게 전달한다."""
    if isinstance(value, bool):
        raise CalculationInputError(f"{label}은(는) 숫자여야 합니다.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise CalculationInputError(f"{label}은(는) 숫자여야 합니다.") from None
    if not math.isfinite(result) or result < 0 or (result == 0 and not allow_zero):
        condition = "0 이상" if allow_zero else "0보다 큰"
        raise CalculationInputError(f"{label}은(는) 유한한 {condition} 값이어야 합니다.")
    return result


def _required(values: Mapping[str, object], name: str, *, allow_zero: bool=False) -> float:
    if not isinstance(values, Mapping):
        raise CalculationInputError("계산 입력은 항목별 숫자 자료여야 합니다.")
    if name not in values:
        raise CalculationInputError(f"{name} 입력값이 없습니다.")
    return _number(values[name], name, allow_zero=allow_zero)

def calculate_motor_value(target_key: str, values: Mapping[str, object]) -> float:
    """전동기 기본식의 정방향 또는 역산 결과를 반환합니다."""
    if target_key not in ("P", "Q", "V", "eff", "OB"):
        raise CalculationInputError("지원하지 않는 전동기 계산 항목입니다.")
    data = {}
    for key in ("P", "Q", "V", "eff", "OB"):
        if key != target_key:
            data[key] = _required(values, key)
    if "eff" in data and data["eff"] > 1:
        raise CalculationInputError("효율 η는 0 초과 1 이하여야 합니다.")
    if "OB" in data and data["OB"] >= 1:
        raise CalculationInputError("오버밸런스율 OB는 0 초과 1 미만이어야 합니다.")
    values = data
    if target_key == "P":
        result = (values["Q"] * values["V"] * (1 - values["OB"])) / (6120 * values["eff"])
    elif target_key == "Q":
        result = (values["P"] * 6120 * values["eff"]) / (values["V"] * (1 - values["OB"]))
    elif target_key == "V":
        result = (values["P"] * 6120 * values["eff"]) / (values["Q"] * (1 - values["OB"]))
    elif target_key == "eff":
        result = (values["Q"] * values["V"] * (1 - values["OB"])) / (6120 * values["P"])
    else:
        result = 1 - (values["P"] * 6120 * values["eff"]) / (values["Q"] * values["V"])
    if not math.isfinite(result):
        raise CalculationInputError("전동기 계산 결과의 숫자 범위를 확인하세요.")
    if target_key == "eff" and not 0 < result <= 1:
        raise CalculationInputError("역산된 효율 η가 0 초과 1 이하 범위를 벗어납니다.")
    if target_key == "OB" and not 0 < result < 1:
        raise CalculationInputError("역산된 오버밸런스율 OB가 0 초과 1 미만 범위를 벗어납니다.")
    return result

def calculate_traction_values(values: Mapping[str, object]) -> dict[str, object]:
    """트랙션비의 모든 중간값과 최종값을 한 번에 반환합니다."""
    values = {key: _required(values, key, allow_zero=key in ("Wcomp", "Wm"))
              for key in ("OB", "Wc", "Q", "H", "wr", "n", "Wcomp", "Wm")}
    if values["OB"] >= 100:
        raise CalculationInputError("오버밸런스율은 100% 미만이어야 합니다.")
    if not values["n"].is_integer():
        raise CalculationInputError("로프 가닥 수는 정수여야 합니다.")
    ob = values["OB"] / 100
    wcw = values["Wc"] + values["Q"] * ob
    rope_total = values["H"] * values["wr"] * values["n"]
    front = (values["Wc"] + values["Q"] + rope_total) / (wcw + values["Wcomp"])
    rear = (wcw + rope_total) / (
        values["Wc"] + values["Wcomp"] + values["Wm"] / 2
    )
    final = max(front, rear)
    return {
        "ob": ob, "wcw": wcw, "rope_total": rope_total,
        "front": front, "rear": rear, "final": final,
        "basis": "전반부 Tf" if front >= rear else "후반부 Tr",
    }

def calculate_brake_values(v: object=None, t: object=None, d: object=None,
                           a: object=None, tolerance: object=0.01) -> dict[str, object]:
    """브레이크 입력 2개로 계산하거나 3개 이상이면 일치 여부를 검사합니다."""
    supplied = {key: _number(value, key) if value is not None else None
                for key, value in (("v", v), ("t", t), ("d", d), ("a", a))}
    v, t, d, a = (supplied[key] for key in ("v", "t", "d", "a"))
    tolerance = _number(tolerance, "허용 오차", allow_zero=True)
    known = [key for key, value in supplied.items() if value is not None]
    if len(known) < 2:
        raise CalculationInputError("입력칸 4개 중 알고 있는 값 2개 이상을 입력해주세요.")
    for key, value in supplied.items():
        if value is not None and value <= 0:
            raise CalculationInputError("브레이크 입력값은 0보다 커야 합니다.")

    # 어떤 두 값이든 같은 기준 결과(v,t,d,a)를 만들도록 여섯 조합을 처리합니다.
    if v is not None and t is not None:
        basis = "속도 v + 제동시간 t"
        solved = {"v": v, "t": t, "d": v * t / 2, "a": v / t}
    elif v is not None and d is not None:
        basis = "속도 v + 제동거리 d"
        solved_t = 2 * d / v
        solved = {"v": v, "t": solved_t, "d": d, "a": v / solved_t}
    elif d is not None and t is not None:
        basis = "제동거리 d + 제동시간 t"
        solved = {"v": 2 * d / t, "t": t, "d": d, "a": 2 * d / (t ** 2)}
    elif v is not None and a is not None:
        basis = "속도 v + 감속도 a"
        solved = {"v": v, "t": v / a, "d": v ** 2 / (2 * a), "a": a}
    elif d is not None and a is not None:
        basis = "제동거리 d + 감속도 a"
        solved_v = math.sqrt(2 * a * d)
        solved = {"v": solved_v, "t": solved_v / a, "d": d, "a": a}
    else:
        basis = "제동시간 t + 감속도 a"
        solved = {"v": a * t, "t": t, "d": a * t ** 2 / 2, "a": a}

    differences = {}
    for key, entered in supplied.items():
        if entered is None:
            continue
        expected = solved[key]
        relative_error = abs(entered - expected) / max(abs(expected), 1e-12)
        differences[key] = relative_error
    solved["basis"] = basis
    solved["differences"] = differences
    solved["consistent"] = all(error <= tolerance for error in differences.values())
    return solved

def calculate_traffic_values(values: Mapping[str, object]) -> dict[str, object]:
    """PDF의 RTT·수송능력 공식에 따라 교통량 계산값을 반환합니다."""
    if not isinstance(values, Mapping):
        raise CalculationInputError("교통량 입력은 항목별 숫자 자료여야 합니다.")
    required = ("A", "F", "S", "phi", "C", "board_rate", "n", "td", "tp", "Tr_travel")
    values = dict(values)
    for key in required:
        values[key] = _required(values, key, allow_zero=key == "A")
    for key, default in (("excluded_floors", 2), ("wait_factor", 0.5), ("express_stops", 0)):
        values[key] = _number(values.get(key, default), key, allow_zero=True)
    if not 0 < values["phi"] <= 1 or not 0 < values["board_rate"] <= 1:
        raise CalculationInputError("집중률과 탑승률은 0 초과 1 이하의 비율이어야 합니다.")
    if values["wait_factor"] > 1 or values["excluded_floors"] >= values["F"]:
        raise CalculationInputError("대기시간 환산율 또는 인구산정 제외층수를 확인하세요.")
    if values.get("population") is not None:
        values["population"] = _number(values["population"], "건물인구")
    values["floor_areas"] = [_number(area, "층별 유효면적") for area in (values.get("floor_areas") or [])]
    if not values["floor_areas"] and not values["A"] and values.get("population") is None:
        raise CalculationInputError("층별 면적, 동일 면적 또는 건물인구가 필요합니다.")
    A = values["A"]
    F = values["F"]
    S = values["S"]
    excluded = values.get("excluded_floors", 2)
    floor_areas = values.get("floor_areas") or []
    phi = values["phi"]
    C = values["C"]
    board_rate = values["board_rate"]
    n = values["n"]
    td = values["td"]
    tp = values["tp"]
    travel = values["Tr_travel"]
    wait_factor = values.get("wait_factor", 0.5)
    population_override = values.get("population")
    express_stops = values.get("express_stops", 0)

    included_floors = int(F - excluded)
    total_area = sum(floor_areas) if floor_areas else A * included_floors
    population = population_override if population_override is not None else total_area / S
    riders = C * board_rate
    local_stops = n * (1 - ((n - 1) / n) ** riders)
    expected_stops = local_stops + express_stops
    door_time = td * expected_stops
    passenger_time = tp * riders
    loss_time = 0.1 * (door_time + passenger_time)
    round_trip = travel + door_time + passenger_time + loss_time
    if not math.isfinite(round_trip) or round_trip <= 0:
        raise CalculationInputError("일주시간을 계산할 수 없습니다. 입력값의 크기를 확인하세요.")
    capacity = (5 * 60 * riders) / round_trip
    peak_users = phi * population
    if not all(math.isfinite(value) for value in (capacity, peak_users)) or capacity <= 0:
        raise CalculationInputError("수송능력과 수요의 숫자 범위를 확인하세요.")
    recommended = max(1, math.ceil(peak_users / capacity))

    def service_for(count):
        interval = round_trip / count
        return {"count": count, "interval": interval, "wait": interval * wait_factor}

    comparison_counts = sorted(set((1, 2, 3, recommended)))
    comparison = [service_for(count) for count in comparison_counts]
    selected = service_for(recommended)
    return {
        "included_floors": included_floors,
        "total_area": total_area,
        "population": population,
        "riders": riders,
        "local_stops": local_stops,
        "express_stops": express_stops,
        "expected_stops": expected_stops,
        "door_time": door_time,
        "passenger_time": passenger_time,
        "loss_time": loss_time,
        "round_trip": round_trip,
        "capacity": capacity,
        "peak_users": peak_users,
        "recommended": recommended,
        "interval": selected["interval"],
        "wait": selected["wait"],
        "comparison": comparison,
    }

def traffic_pdf_reference(building_use, floors, population=None, total_area=None,
                          households=None, rooms=None):
    """제공된 PDF 표 1-11~1-13의 참고 범위만 반환합니다.

    이 값들은 법정 최소기준이 아니라 PDF에 '목표 설정 예시'와
    '설치 대수/속도 설계 예시'로 제시된 참고값입니다.
    """
    demand_ranges = {
        "오피스-전용사옥": (20, 25), "오피스-복합사옥": (16, 20),
        "오피스-공공건물": (14, 18), "오피스-임대사무실": (11, 15),
        "공동주택": (3.5, 5.0), "호텔-고급": (9, 11),
        "호텔-중급": (9, 11), "호텔-비즈니스": (9, 11),
    }
    interval_targets = {
        "오피스": (30, 40), "공동주택": (60, 90), "호텔": (40, 40),
    }
    group = ("오피스" if building_use.startswith("오피스-") else
             "호텔" if building_use.startswith("호텔-") else building_use)

    def speed_range():
        if group == "오피스":
            rows = ((10, "60~90"), (15, "90~150"), (20, "120~210"),
                    (30, "180~300"), (40, "240~420"), (50, "360~540"),
                    (math.inf, "480 이상"))
        elif group == "호텔":
            rows = ((10, "60~90"), (15, "90~120"), (20, "105~150"),
                    (30, "150~240"), (40, "210~360"), (50, "300~420"),
                    (math.inf, "420 이상"))
        elif group == "공동주택":
            rows = ((15, "60 이하"), (20, "60~105"), (30, "90~150"),
                    (40, "120~210"), (math.inf, "210 이상"))
        else:
            return None
        return next(label for upper, label in rows if floors <= upper)

    rough_count = None
    rough_basis = ""
    if building_use.startswith("오피스-") and total_area and population:
        per_car = {
            "오피스-전용사옥": (1200, 150), "오피스-복합사옥": (1600, 200),
            "오피스-공공건물": (2000, 250), "오피스-임대사무실": (2400, 300),
        }[building_use]
        rough_count = max(math.ceil(total_area / per_car[0]),
                          math.ceil(population / per_car[1]))
        rough_basis = f"면적 {per_car[0]}m²/대·인구 {per_car[1]}인/대 중 큰 값"
    elif building_use == "공동주택" and households:
        rough_count, rough_basis = math.ceil(households / 70), "70가구/대"
    elif building_use.startswith("호텔-") and rooms:
        room_ratio = {"호텔-고급": 100, "호텔-중급": 150,
                      "호텔-비즈니스": 200}[building_use]
        rough_count, rough_basis = math.ceil(rooms / room_ratio), f"{room_ratio}실/대"

    return {
        "demand_range": demand_ranges.get(building_use),
        "interval_target": interval_targets.get(group),
        "speed_range_m_min": speed_range(),
        "rough_count": rough_count,
        "rough_basis": rough_basis,
    }

def traffic_visible_input_fields(building_use):
    """건물용도별로 화면에 표시할 교통량 입력항목을 결정합니다."""
    common = {
        "F", "phi", "C", "board_rate", "n", "td", "tp",
        "Tr_travel", "wait_factor", "N_current",
    }
    if building_use.startswith("오피스-"):
        specific = {"A", "excluded_floors", "floor_areas", "S"}
    elif building_use == "공동주택":
        specific = {"households", "persons_per_household"}
    elif building_use.startswith("호텔-"):
        specific = {"rooms", "guests_per_room"}
    elif building_use == "병원":
        specific = {"beds"}
    else:
        specific = {"direct_population"}
    return common | specific

def run_calculation_self_tests():
    """UI 변경과 무관하게 핵심 계산식이 유지되는지 빠르게 검증합니다."""
    def close(actual, expected, tolerance=1e-9):
        if not math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance):
            raise AssertionError(f"자동검사 불일치: {actual} != {expected}")

    motor = calculate_motor_value("P", {"Q": 1500, "V": 180, "OB": 0.45, "eff": 0.8})
    close(motor, 30.330882352941178)
    motor_values = {"P": motor, "Q": 1500, "V": 180, "OB": 0.45, "eff": 0.8}
    for target in ("Q", "V", "OB", "eff"):
        inputs = {key: value for key, value in motor_values.items() if key != target}
        close(calculate_motor_value(target, inputs), motor_values[target])
    traction = calculate_traction_values({
        "Q": 1500, "Wc": 2400, "H": 50, "wr": 1.1, "n": 6,
        "OB": 45, "Wcomp": 0, "Wm": 0,
    })
    close(traction["wcw"], 3075)
    close(traction["rope_total"], 330)
    close(traction["final"], 1.41875)
    brake = calculate_brake_values(v=3, t=0.6)
    close(brake["d"], 0.9)
    close(brake["a"], 5)
    for pair in ({"v": 3, "d": 0.9}, {"d": 0.9, "t": 0.6},
                 {"v": 3, "a": 5}, {"d": 0.9, "a": 5}, {"t": 0.6, "a": 5}):
        solved = calculate_brake_values(**pair)
        close(solved["v"], 3)
        close(solved["t"], 0.6)
        close(solved["d"], 0.9)
        close(solved["a"], 5)
    traffic = calculate_traffic_values({
        "A": 500, "F": 10, "S": 10, "excluded_floors": 2,
        "phi": 0.15, "C": 15, "board_rate": 0.8, "n": 10,
        "td": 4, "tp": 1, "Tr_travel": 60, "wait_factor": 0.5,
    })
    if traffic["recommended"] < 1 or len(traffic["comparison"]) < 3:
        raise AssertionError("교통량 자동검사 불일치")
    traffic_by_floor = calculate_traffic_values({
        "A": 0, "F": 5, "S": 10, "excluded_floors": 1,
        "floor_areas": [100, 200, 300, 400], "phi": 0.15,
        "C": 15, "board_rate": 0.8, "n": 5, "td": 4, "tp": 1,
        "Tr_travel": 60, "wait_factor": 0.4,
    })
    close(traffic_by_floor["total_area"], 1000)
    close(traffic_by_floor["population"], 100)
    textbook_example = calculate_traffic_values({
        "A": 0, "F": 10, "S": 1, "excluded_floors": 2,
        "population": 1000, "phi": 0.15, "C": 15, "board_rate": 0.8,
        "n": 8, "td": 2.7, "tp": 2.5, "Tr_travel": 37,
        "wait_factor": 0.5, "express_stops": 1,
    })
    close(textbook_example["local_stops"], 6.388662095966693)
    close(textbook_example["expected_stops"], 7.388662095966693)
    close(textbook_example["round_trip"], 91.94432642501748)
    office_reference = traffic_pdf_reference("오피스-전용사옥", 10, 300, 2400)
    if office_reference["demand_range"] != (20, 25) or office_reference["rough_count"] != 2:
        raise AssertionError("PDF 교통량 참고표 자동검사 불일치")
    use_field_tests = {
        "호텔-중급": {"rooms", "guests_per_room"},
        "공동주택": {"households", "persons_per_household"},
        "병원": {"beds"},
        "오피스-전용사옥": {"A", "excluded_floors", "floor_areas", "S"},
        "사용자 설정": {"direct_population"},
    }
    special_fields = {
        "A", "excluded_floors", "floor_areas", "S", "households",
        "persons_per_household", "rooms", "guests_per_room", "beds",
        "direct_population",
    }
    for building_use, expected in use_field_tests.items():
        visible = traffic_visible_input_fields(building_use) & special_fields
        if visible != expected:
            raise AssertionError(f"{building_use} 용도별 입력칸 자동검사 불일치")
    return True
