"""앱에서 실행하는 독립 산술 점검. 실제 측정 정확도 검증은 아니다."""
import math
from src.core.calculators import (calculate_motor_value, calculate_traction_values,
    calculate_brake_values, calculate_traffic_values, traffic_pdf_reference,
    traffic_visible_input_fields)


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
