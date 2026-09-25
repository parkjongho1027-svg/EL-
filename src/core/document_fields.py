"""Extract *review candidates* from user-supplied drawings and certificates.

No value is trusted or written into a calculator until the user chooses it.
"""

from dataclasses import dataclass
import re

from .errors import CalculationInputError


@dataclass(frozen=True)
class FieldCandidate:
    key: str
    label: str
    value: float
    unit: str
    source_line: str


PATTERNS = (
    (
        "rated_load_kg",
        "정격하중",
        r"정격\s*(?:적재)?\s*하중\s*[:=]?\s*([\d,.]+)\s*(kg|㎏)",
        1,
    ),
    ("speed_m_s", "정격속도", r"정격\s*속도\s*[:=]?\s*([\d,.]+)\s*(m/s|m/min|m/분)", 1),
    (
        "distance_m",
        "승강행정",
        r"(?:승강\s*행정|주행\s*거리)\s*[:=]?\s*([\d,.]+)\s*(m|mm)\b",
        1,
    ),
    ("car_kg", "카 자중", r"(?:카\s*자중|카\s*질량)\s*[:=]?\s*([\d,.]+)\s*(kg|㎏)", 1),
    (
        "rope_count",
        "로프 가닥 수",
        r"로프\s*(?:가닥\s*수|본\s*수)\s*[:=]?\s*(\d+)\s*(?:가닥|본)?",
        1,
    ),
    (
        "motor_kw",
        "선정 전동기",
        r"(?:선정\s*)?전동기\s*(?:용량|출력)\s*[:=]?\s*([\d,.]+)\s*(kW|kw)",
        1,
    ),
)


def extract_fields(text):
    if not isinstance(text, str) or len(text) > 500_000:
        raise CalculationInputError("문서 텍스트는 50만 자 이하로 입력하세요.")
    candidates = []
    for line in text.splitlines():
        if len(line) > 500:
            continue
        for key, label, regex, _ in PATTERNS:
            for match in re.finditer(regex, line, flags=re.IGNORECASE):
                raw = match.group(1)
                unit = (
                    match.group(2)
                    if match.lastindex and match.lastindex >= 2
                    else "가닥"
                )
                try:
                    value = float(raw.replace(",", ""))
                except ValueError:
                    continue
                if value <= 0 or value > 1e9:
                    continue
                if key == "speed_m_s" and unit.lower() != "m/s":
                    value /= 60
                elif key == "distance_m" and unit.lower() == "mm":
                    value /= 1000
                if key == "rope_count" and not 1 <= value <= 100:
                    continue
                candidates.append(
                    FieldCandidate(
                        key,
                        label,
                        value,
                        "m/s"
                        if key == "speed_m_s"
                        else "m"
                        if key == "distance_m"
                        else unit,
                        line.strip()[:180],
                    )
                )
    return candidates
