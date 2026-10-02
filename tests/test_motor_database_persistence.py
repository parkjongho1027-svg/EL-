import json
from src.persistence import storage


def test_motor_component_survives_restart(tmp_path, monkeypatch):
    data_file = tmp_path / "user_data.json"
    monkeypatch.setattr(storage, "get_data_file_path", lambda: data_file)
    first = storage.PersistentStore()
    motor = {
        "maker": "Test Maker", "model": "T-22", "rated_power_kw": 22.0,
        "rated_torque_nm": 2100.0, "rated_speed_rpm": 78.0,
        "inertia_kg_m2": None, "source": "https://example.com/spec",
        "verified_date": "2026-09-25",
    }
    first.add_engineering_record("motor_component", "Test Maker T-22", "", motor)
    second = storage.PersistentStore()
    rows = second.engineering_records("motor_component")
    assert len(rows) == 1
    assert rows[0]["payload"]["model"] == "T-22"
