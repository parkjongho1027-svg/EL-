"""User-authored, traceable component inputs; no bundled manufacturer claims."""

from dataclasses import dataclass
import json
import math
from pathlib import Path

from .errors import CalculationInputError


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    maker: str
    model: str
    source: str
    rope_kg_m: float
    sheave_radius_m: float
    motor_inertia_kg_m2: float
    motor_options_kw: tuple[float, ...]

    def __post_init__(self):
        if any(not isinstance(getattr(self, field), str) or not getattr(self, field).strip()
               for field in ("maker", "model", "source")):
            raise CalculationInputError("제조사·모델·출처를 모두 입력하세요.")
        for field in ("rope_kg_m", "sheave_radius_m", "motor_inertia_kg_m2"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise CalculationInputError(f"{field}: 유한한 양수가 필요합니다.")
        ratings = self.motor_options_kw
        if (not isinstance(ratings, tuple) or not 1 <= len(ratings) <= 30
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in ratings)):
            raise CalculationInputError("motor_options_kw: 유한한 양수 정격 목록이 필요합니다.")


def load_component_spec(path: str | Path) -> ComponentSpec:
    source = Path(path)
    try:
        if source.stat().st_size > 1_000_000:
            raise CalculationInputError("부품 명세 JSON은 1 MB 이하여야 합니다.")
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CalculationInputError(f"부품 명세를 읽을 수 없습니다: {error}") from error
    if not isinstance(data, dict):
        raise CalculationInputError("부품 명세는 JSON 객체여야 합니다.")
    expected = set(ComponentSpec.__dataclass_fields__)
    if set(data) != expected or not isinstance(data["motor_options_kw"], list):
        raise CalculationInputError("부품 명세의 필수 항목과 전동기 정격 배열을 확인하세요.")
    data["motor_options_kw"] = tuple(data["motor_options_kw"])
    return ComponentSpec(**data)
