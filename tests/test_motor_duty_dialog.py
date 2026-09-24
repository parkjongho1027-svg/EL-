"""Motor duty UI adapter keeps input history independent from motor sizing."""

import storage
from src.core.motor_dynamics import MotorDutyInput, estimate_motor_duty
from src.ui.motor_duty_dialog import FIELD_SPECS, format_duty_result


def test_duty_result_and_previous_input(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "get_data_file_path", lambda: tmp_path / "user_data.json"
    )
    store = storage.PersistentStore()
    raw = {key: default for key, _label, default in FIELD_SPECS}
    raw["direction"] = "상승"
    result = estimate_motor_duty(MotorDutyInput(**raw))
    message = format_duty_result(result)
    assert "N·m" in message and "운전율" in message and "kW" in message
    store.add_history("motor_duty", raw, message.splitlines()[0])
    restored = storage.PersistentStore()
    assert restored.previous("motor_duty")["distance_m"] == raw["distance_m"]
    assert len(restored.history("motor")) == 0
    assert len(restored.history("motor_duty")) == 1
