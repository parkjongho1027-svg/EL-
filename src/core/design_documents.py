"""Input-document references for design calculations before installation."""

from __future__ import annotations

from typing import Any


# Project-specific worksheet headings; not a reproduction of an NCS checklist.
DOCUMENT_AREAS = (
    ("motor", "전동기", "정격하중·속도·선정 전동기 사양의 자료 출처"),
    ("traction", "로프·권상", "로프 수·직경·파단하중·설계 장력의 자료 출처"),
    ("brake", "제동기", "제동기 사양과 설계 조건의 자료 출처"),
    ("traffic", "교통량", "건물 용도·층수·면적·인구 가정의 자료 출처"),
    ("simulation", "운행 시뮬레이션", "행정거리·가속도·효율 가정의 자료 출처"),
    ("standards", "기준 검토", "적용 기준의 판본과 제조사 설계도서의 자료 출처"),
)
STATES = ("자료 없음", "자료 있음", "추가 자료 필요")


def normalize_design_documents(raw: Any) -> dict[str, Any]:
    """Accept bounded references, never interpreting a document as proof of compliance."""
    raw = raw if isinstance(raw, dict) else {}

    def field(value: Any, limit: int) -> str:
        return value[:limit] if isinstance(value, str) else ""

    entries = raw.get("areas")
    entries = entries if isinstance(entries, dict) else {}
    normalized = {}
    for key, _, _ in DOCUMENT_AREAS:
        item = entries.get(key)
        item = item if isinstance(item, dict) else {}
        status = item.get("status")
        normalized[key] = {
            "status": status if status in STATES else STATES[0],
            "note": field(item.get("note"), 1500),
            "source": field(item.get("source"), 500),
        }
    return {
        "reviewed_at": field(raw.get("reviewed_at"), 80),
        "reviewer": field(raw.get("reviewer"), 100),
        "areas": normalized,
    }
