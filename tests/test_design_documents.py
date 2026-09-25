"""Pre-installation document references survive save without legal verdicts."""

from src.core.design_documents import DOCUMENT_AREAS, normalize_design_documents
from src.ui.project_snapshot import merge_project_states


def test_document_references_survive_project_snapshot():
    worksheet = normalize_design_documents({
        "reviewed_at": "2026-09-25", "reviewer": "설계 담당자",
        "areas": {"brake": {
            "status": "추가 자료 필요", "note": "선정 제동기 정격 토크의 자료 확인 필요",
            "source": "제동기 사양서 Rev.2 p.3",
        }},
    })
    source = {
        "motor": {"values": {"Q": "1000", "V": "2", "OB": "40"}, "units": {"V": "m/s"}},
        "traction": {"values": {"Q": "1000", "n": "6", "OB": "40"}},
        "brake": {}, "traffic": {},
        "criteria": {"count": "6", "rated": "2", "__drive__": "권상식",
                     "__design_documents__": worksheet},
        "scurve": {},
    }
    saved, _ = merge_project_states(source, "criteria")
    assert saved["criteria"]["__design_documents__"] == worksheet
    assert saved["criteria"]["__design_documents__"] is not worksheet
    assert saved["criteria"]["__design_documents__"]["areas"]["brake"]["source"] == "제동기 사양서 Rev.2 p.3"


def test_invalid_and_old_project_fields_cannot_claim_compliance():
    blank = normalize_design_documents(None)
    assert len(blank["areas"]) == len(DOCUMENT_AREAS)
    assert all(row["status"] == "자료 없음" for row in blank["areas"].values())
    corrupt = normalize_design_documents({
        "reviewer": 17, "extra": "ignored",
        "areas": {"motor": {"status": "적합", "note": "x" * 2000,
                             "source": ["invalid"]}, "unknown": {"status": "자료 있음"}},
    })
    assert corrupt["reviewer"] == ""
    assert corrupt["areas"]["motor"] == {
        "status": "자료 없음", "note": "x" * 1500, "source": "",
    }
    assert "unknown" not in corrupt["areas"]
    assert "extra" not in corrupt
    assert "__inspection_record__" not in normalize_design_documents({
        "__inspection_record__": {"locations": {"car": {"status": "관찰 기록"}}}
    })
