"""Optional field observations; these are not statutory inspection results."""

from __future__ import annotations

from typing import Any

# Original worksheet headings, organized by the locations in NCS module 1505010706.
LOCATIONS = (
    ("machine_room", "기계실", "권상기·제동기·제어반의 관찰 사항"),
    ("car", "카", "운행 상태·카 내부·카 상부의 관찰 사항"),
    ("shaft", "승강로", "레일·매다는 장치·균형추의 관찰 사항"),
    ("landing", "승강장", "출입문·표시 장치의 관찰 사항"),
    ("pit", "피트", "완충기·하부 공간의 관찰 사항"),
)
STATES = ("미확인", "관찰 기록", "추가 확인 필요")


def normalize_inspection_record(raw: Any) -> dict[str, Any]:
    """Discard unknown project keys and untrusted values without turning them into verdicts."""
    raw = raw if isinstance(raw, dict) else {}

    def field(value: Any, limit: int) -> str:
        return value[:limit] if isinstance(value, str) else ""

    entries = raw.get("locations")
    entries = entries if isinstance(entries, dict) else {}
    normalized = {}
    for key, _, _ in LOCATIONS:
        item = entries.get(key)
        item = item if isinstance(item, dict) else {}
        status = item.get("status")
        normalized[key] = {
            "status": status if status in STATES else STATES[0],
            "observation": field(item.get("observation"), 1500),
            "evidence": field(item.get("evidence"), 500),
        }
    return {
        "inspected_at": field(raw.get("inspected_at"), 80),
        "inspector": field(raw.get("inspector"), 100),
        "locations": normalized,
    }
