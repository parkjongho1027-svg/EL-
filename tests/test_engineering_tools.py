"""Independent checks for bounded design suggestions and uploaded-data parsing."""

import math
import struct
import wave

import pytest

from src.core.design_explorer import DesignRequest, explore_designs
from src.core.document_fields import extract_fields
from src.core.errors import CalculationInputError
from src.core.vibration_analysis import analyse_signal, load_csv_signal, load_wav_signal
from src.ui.document_reader import read_document


def test_design_candidates_are_recomputed_and_fit_selected_motor():
    request = DesignRequest(30, 2, 1000, 1000, 0.8, (7.5, 11, 15, 18.5, 22))
    report = explore_designs(request)
    assert report["tested_cases"] == 81
    assert report["feasible_count"] + report["rejected_count"] == 81
    assert report["holdout_max_error_pct"] >= report["holdout_mean_error_pct"] >= 0
    assert len(report["top"]) == 3
    assert (
        len({(item["ropes"], item["selected_motor_kw"]) for item in report["top"]}) == 3
    )
    for row in report["top"]:
        assert (
            row["selected_motor_kw"] >= request.power_margin * row["required_peak_kw"]
        )
        assert row["max_static_tension_n_per_rope"] > 0


def test_design_rejects_unusable_ratings_and_impossible_cycle():
    with pytest.raises(CalculationInputError):
        DesignRequest(30, 2, 1000, 1000, 0.8, (math.nan,))
    with pytest.raises(CalculationInputError):
        explore_designs(DesignRequest(30, 2, 1000, 1000, 0.8, (20,), cycle_s=1))
    no_motor = explore_designs(DesignRequest(30, 2, 1000, 1000, 0.8, (0.001,)))
    assert no_motor["top"] == []
    assert no_motor["rejected_count"] == 81


def test_csv_frequency_comes_from_time_and_invalid_time_is_rejected(tmp_path):
    path = tmp_path / "healthy.csv"
    path.write_text(
        "time_s,acceleration_m_s2\n"
        + "".join(
            f"{index / 1024},{math.sin(2 * math.pi * 64 * index / 1024)}\n"
            for index in range(1024)
        ),
        encoding="utf-8",
    )
    report = load_csv_signal(path)
    assert report["sampling_hz"] == pytest.approx(1024)
    assert report["rms"] == pytest.approx(1 / math.sqrt(2), rel=1e-4)
    assert report["dominant_hz"] == pytest.approx(64)
    path.write_text(
        "time_s,vibration\n0,1\n0,2\n"
        + "".join(f"{index},2\n" for index in range(1, 20)),
        encoding="utf-8",
    )
    with pytest.raises(CalculationInputError, match="time_s"):
        load_csv_signal(path)


def test_pcm_wav_is_marked_uncalibrated_and_bad_samples_trapped(tmp_path):
    path = tmp_path / "sound.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(struct.pack("<" + "h" * 32, *([1000, -1000] * 16)))
    report = load_wav_signal(path)
    assert "보정되지 않은" in report["source_kind"]
    assert report["rms"] > 0
    with pytest.raises(CalculationInputError):
        analyse_signal([math.nan] * 16, 8000)
    with pytest.raises(CalculationInputError, match="샘플링"):
        analyse_signal([0.0] * 16, math.inf)


def test_csv_requires_sampling_rate_when_time_is_missing(tmp_path):
    path = tmp_path / "samples.csv"
    path.write_text("vibration\n" + "0\n" * 20, encoding="utf-8")
    with pytest.raises(CalculationInputError, match="샘플링"):
        load_csv_signal(path)
    result = load_csv_signal(path, sampling_hz=200)
    assert result["crest_factor"] is None
    assert len(result["waveform"]) == 20


def test_document_extraction_keeps_original_lines_and_normalizes_units():
    matches = extract_fields(
        "정격하중: 1,000 kg\n정격속도: 120 m/min\n"
        "승강행정: 30,000 mm\n카 자중 1,450 kg\n로프 가닥 수: 6본\n"
        "선정 전동기 용량: 18.5 kW\n정격속도: 2.5 m/s"
    )
    assert [item.key for item in matches].count("speed_m_s") == 2
    by_key = {item.key: item for item in matches}
    assert by_key["rated_load_kg"].value == 1000
    assert by_key["distance_m"].value == 30
    assert by_key["rope_count"].value == 6
    assert by_key["motor_kw"].value == 18.5
    assert by_key["speed_m_s"].value == 2.5
    assert all(item.source_line for item in matches)


def test_document_rejects_oversize_input_and_ignores_unlabelled_values():
    with pytest.raises(CalculationInputError):
        extract_fields("x" * 500001)
    assert extract_fields("정격속도 0 m/s\n로프 가닥 수 101\n수치 300 kg") == []


def test_pdf_text_reader_routes_verified_candidates(tmp_path, monkeypatch):
    import pypdf

    source = tmp_path / "design.pdf"
    source.write_bytes(b"PDF test stub")

    class Page:
        def extract_text(self):
            return "정격속도: 120 m/min\n카 자중: 1000 kg"

    class Reader:
        def __init__(self, _path):
            self.pages = [Page()]

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    candidates = read_document(source)
    assert [(item.key, item.value) for item in candidates] == [
        ("speed_m_s", 2),
        ("car_kg", 1000),
    ]
