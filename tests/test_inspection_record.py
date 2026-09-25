"""Field notes survive project merging and cannot become automatic legal verdicts."""

from src.core.inspection_record import LOCATIONS, normalize_inspection_record
from src.ui.project_snapshot import merge_project_states


def test_observation_round_trip_through_project_snapshot():
    worksheet = normalize_inspection_record({
        "inspected_at": "2026-09-25 09:30", "inspector": "담당자",
        "locations": {
            "machine_room": {
                "status": "추가 확인 필요",
                "observation": "제동기 측정값은 현장 보고서 확인 필요",
                "evidence": "검사기록-1.pdf",
            },
        },
    })
    source = {
        "motor": {"values": {"Q": "1000", "V": "2", "OB": "40"}, "units": {"V": "m/s"}},
        "traction": {"values": {"Q": "1000", "n": "6", "OB": "40"}},
        "brake": {}, "traffic": {},
        "criteria": {"count": "6", "rated": "2", "__drive__": "권상식",
                     "__inspection_record__": worksheet},
        "scurve": {},
    }
    saved, _ = merge_project_states(source, "criteria")
    assert saved["criteria"]["__inspection_record__"] == worksheet
    assert saved["criteria"]["__inspection_record__"] is not worksheet
    assert saved["criteria"]["__inspection_record__"]["locations"]["machine_room"]["evidence"] == "검사기록-1.pdf"


def test_missing_and_malformed_old_project_fields_are_safe():
    blank = normalize_inspection_record(None)
    assert len(blank["locations"]) == len(LOCATIONS)
    assert all(row["status"] == "미확인" for row in blank["locations"].values())
    corrupt = normalize_inspection_record({
        "inspector": 17, "extra": "ignored",
        "locations": {"car": {"status": "적합", "observation": "x" * 2000,
                               "evidence": ["invalid"]}, "unknown": {"status": "관찰 기록"}},
    })
    assert corrupt["inspector"] == ""
    assert corrupt["locations"]["car"] == {
        "status": "미확인", "observation": "x" * 1500, "evidence": "",
    }
    assert "unknown" not in corrupt["locations"]
    assert "extra" not in corrupt
