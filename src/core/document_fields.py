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


# Only accept an explicit label followed by a number and its expected unit.
# Word boundaries also stop partial matches in e.g. "unrated load".
NUMBER = r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
LABEL_START = r"(?<![A-Za-z가-힣])"
SEPARATOR = r"\s*[:=]?\s*"
UNIT_END = r"(?![A-Za-z/²³^])"
LOAD_LABEL = r"(?:정격\s*(?:적재)?\s*하중|rated[\s_-]+load)"
SPEED_LABEL = r"(?:정격\s*속도|rated[\s_-]+speed)"
TRAVEL_LABEL = r"(?:승강\s*행정|주행\s*거리|travel(?:[\s_-]+(?:distance|height))?)"
CAR_LABEL = r"(?:카\s*자중|카\s*질량|car[\s_-]+(?:mass|weight))"
ROPE_LABEL = (r"(?:로프\s*(?:가닥\s*수|본\s*수)|"
              r"(?:number[\s_-]+of[\s_-]+ropes|rope[\s_-]+count|ropes))")
MOTOR_LABEL = (r"(?:(?:선정\s*)?전동기\s*(?:용량|출력)|"
               r"(?:(?:selected|rated)[\s_-]+)?motor[\s_-]+"
               r"(?:(?:rated[\s_-]+)?(?:power|capacity|rating)))")

LABELS = (
    ("rated_load_kg", LOAD_LABEL), ("speed_m_s", SPEED_LABEL),
    ("distance_m", TRAVEL_LABEL), ("car_kg", CAR_LABEL),
    ("rope_count", ROPE_LABEL), ("motor_kw", MOTOR_LABEL),
)

PATTERNS = (
    (
        "rated_load_kg",
        "정격하중",
        LABEL_START + LOAD_LABEL
        + SEPARATOR + NUMBER + r"\s*(kg|㎏)" + UNIT_END,
    ),
    (
        "speed_m_s", "정격속도",
        LABEL_START + SPEED_LABEL
        + SEPARATOR + NUMBER + r"\s*(m/s|m/min|m/분)" + UNIT_END,
    ),
    (
        "distance_m",
        "승강행정",
        LABEL_START + TRAVEL_LABEL
        + SEPARATOR + NUMBER + r"\s*(mm|m)" + UNIT_END,
    ),
    (
        "car_kg", "카 자중",
        LABEL_START + CAR_LABEL
        + SEPARATOR + NUMBER + r"\s*(kg|㎏)" + UNIT_END,
    ),
    (
        "rope_count",
        "로프 가닥 수",
        LABEL_START + ROPE_LABEL
        + SEPARATOR + r"(\d+)(?![\d,.])\s*(?:가닥|본|pcs)?",
    ),
    (
        "motor_kw",
        "선정 전동기",
        LABEL_START + MOTOR_LABEL
        + SEPARATOR + NUMBER + r"\s*(kW)" + UNIT_END,
    ),
)


def _candidates_in_line(line, source_line=None, whole_line=False):
    for key, label, regex in PATTERNS:
        if whole_line:
            match = re.fullmatch(regex, line, flags=re.IGNORECASE)
            matches = (match,) if match else ()
        else:
            matches = re.finditer(regex, line, flags=re.IGNORECASE)
        for match in matches:
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
            yield FieldCandidate(
                key, label, value,
                "m/s" if key == "speed_m_s" else "m" if key == "distance_m" else unit,
                " ".join((source_line or line.strip()).split())[:180],
            )


def extract_fields(text):
    if not isinstance(text, str) or len(text) > 500_000:
        raise CalculationInputError("문서 텍스트는 50만 자 이하로 입력하세요.")
    candidates = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if len(line) > 500:
            continue
        candidates.extend(_candidates_in_line(line))
        if index + 1 >= len(lines) or len(lines[index + 1]) > 500:
            continue
        label_line, value_line = line.strip(), lines[index + 1].strip()
        if not any(re.fullmatch(label + r"\s*[:=]?\s*", label_line,
                                flags=re.IGNORECASE) for _key, label in LABELS):
            continue
        combined = f"{label_line} {value_line}"
        candidates.extend(_candidates_in_line(
            combined, f"{label_line} | {value_line}", whole_line=True,
        ))
    return candidates
