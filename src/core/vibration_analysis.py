"""Signal statistics for user supplied vibration CSV or *uncalibrated* PCM WAV.

No model is trained to recognise bearing faults and no RUL is estimated.
"""

import csv
import math
from pathlib import Path
import wave

from .errors import CalculationInputError

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_SAMPLES = 8192


def _safe_path(path):
    source = Path(path)
    if not source.is_file() or source.stat().st_size > MAX_FILE_BYTES:
        raise CalculationInputError("파일을 찾을 수 없거나 8 MiB를 초과했습니다.")
    return source


def load_csv_signal(path, sampling_hz=None):
    """Read time_s and acceleration_m_s2/vibration; require sampling rate if no time."""
    source = _safe_path(path)
    try:
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = reader.fieldnames or []
            column = next(
                (
                    key
                    for key in ("acceleration_m_s2", "vibration", "value")
                    if key in headers
                ),
                None,
            )
            if column is None:
                raise CalculationInputError(
                    "CSV에 acceleration_m_s2 또는 vibration 열이 필요합니다."
                )
            values, times = [], []
            for row in reader:
                if len(values) >= MAX_SAMPLES:
                    break
                values.append(float(row[column]))
                if "time_s" in headers:
                    times.append(float(row["time_s"]))
    except (OSError, UnicodeError, TypeError, ValueError, csv.Error) as error:
        raise CalculationInputError(f"CSV 읽기 실패: {error}") from error
    if times:
        gaps = [b - a for a, b in zip(times, times[1:])]
        if not gaps or not all(math.isfinite(v) and v > 0 for v in gaps):
            raise CalculationInputError("time_s는 유한하고 계속 증가해야 합니다.")
        average = sum(gaps) / len(gaps)
        if any(abs(v - average) > average * 0.05 for v in gaps):
            raise CalculationInputError(
                "일정 간격(±5%)으로 측정한 time_s가 필요합니다."
            )
        sampling_hz = 1 / average
    if sampling_hz is None:
        raise CalculationInputError(
            "time_s 열이 없으면 샘플링 주파수(Hz)를 입력하세요."
        )
    return analyse_signal(values, sampling_hz, source_kind="진동 CSV")


def load_wav_signal(path):
    source = _safe_path(path)
    try:
        with wave.open(str(source), "rb") as stream:
            width, channels, rate = (
                stream.getsampwidth(),
                stream.getnchannels(),
                stream.getframerate(),
            )
            if (
                stream.getcomptype() != "NONE"
                or width not in (1, 2, 3, 4)
                or channels < 1
                or channels > 2
            ):
                raise CalculationInputError(
                    "PCM 모노/스테레오 WAV(8~32비트)만 지원합니다."
                )
            data = stream.readframes(min(MAX_SAMPLES, stream.getnframes()))
    except (OSError, EOFError, wave.Error) as error:
        raise CalculationInputError(f"WAV 읽기 실패: {error}") from error
    frame_bytes = width * channels
    values = []
    for position in range(0, len(data) - frame_bytes + 1, frame_bytes):
        samples = []
        for channel in range(channels):
            raw = data[position + width * channel : position + width * (channel + 1)]
            if width == 1:
                sample = (raw[0] - 128) / 128
            else:
                sample = int.from_bytes(raw, "little", signed=True) / (
                    1 << (width * 8 - 1)
                )
            samples.append(sample)
        values.append(sum(samples) / channels)
    return analyse_signal(values, rate, source_kind="보정되지 않은 WAV 진폭")


def analyse_signal(values, sampling_hz, *, source_kind="진동 CSV"):
    if (
        isinstance(sampling_hz, bool)
        or not isinstance(sampling_hz, (int, float))
        or not math.isfinite(sampling_hz)
        or sampling_hz <= 0
    ):
        raise CalculationInputError("샘플링 주파수는 유한한 양수여야 합니다.")
    if not 16 <= len(values) <= MAX_SAMPLES or any(
        not isinstance(v, (float, int)) or not math.isfinite(v) for v in values
    ):
        raise CalculationInputError("유한한 숫자 샘플 16~8192개가 필요합니다.")
    count = len(values)
    average = sum(values) / count
    centered = [v - average for v in values]
    rms = math.sqrt(sum(v * v for v in centered) / count)
    peak = max(abs(v) for v in centered)
    # Bounded Goertzel/DFT scan. Frequency resolution is fs/N; the highest
    # plotted bin is limited for responsiveness and is not a full FFT spectrum.
    max_bin = min(128, count // 2)
    spectrum = []
    for index in range(1, max_bin + 1):
        real = imag = 0.0
        for position, value in enumerate(centered):
            angle = 2 * math.pi * index * position / count
            real += value * math.cos(angle)
            imag -= value * math.sin(angle)
        spectrum.append(
            (index * sampling_hz / count, math.hypot(real, imag) * 2 / count)
        )
    dominant_hz, dominant_amplitude = max(spectrum, key=lambda item: item[1])
    return dict(
        source_kind=source_kind,
        sample_count=count,
        sampling_hz=sampling_hz,
        mean=average,
        rms=rms,
        peak=peak,
        crest_factor=(peak / rms if rms else None),
        dominant_hz=dominant_hz,
        dominant_amplitude=dominant_amplitude,
        frequency_resolution_hz=sampling_hz / count,
        scanned_max_hz=spectrum[-1][0],
        waveform=tuple(centered[:: max(1, count // 256)]),
        spectrum=tuple(spectrum),
    )
