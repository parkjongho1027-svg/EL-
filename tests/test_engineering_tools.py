"""Independent checks for bounded design suggestions and uploaded-data parsing."""

import math
import json
import struct
import wave

import pytest

from src.core.design_explorer import DesignRequest, candidates_under_peak, explore_designs
from src.core.component_spec import ComponentSpec, load_component_spec
from src.core.document_fields import extract_fields
from src.core.errors import CalculationInputError
from src.core.measured_speed import compare_speed_log, load_speed_log
from src.core.synthetic_log import SyntheticOptions, generate_synthetic_log, save_synthetic_log
from src.core.trajectory import scurve_profile
from src.core.vibration_analysis import analyse_signal, load_csv_signal, load_wav_signal
from src.ui.document_reader import read_document


def test_design_candidates_are_recomputed_and_fit_selected_motor():
    request = DesignRequest(30, 2, 1000, 1000, 0.8, (7.5, 11, 15, 18.5, 22))
    report = explore_designs(request)
    assert report["tested_cases"] == 81
    assert len(report["all_cases"]) == 81
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


def test_goal_search_only_uses_sampled_feasible_models():
    report = explore_designs(DesignRequest(30, 2, 1000, 1000, 0.8, (7.5, 11, 15, 18.5, 22)))
    target = min(row["required_peak_kw"] for row in report["all_cases"] if row["selected_motor_kw"])
    rows = candidates_under_peak(report, target + 1e-8)
    assert rows and all(row["required_peak_kw"] <= target + 1e-8 for row in rows)
    assert rows == sorted(rows, key=lambda row: (row["balance_pct"], row["selected_motor_kw"], row["ropes"]))
    with pytest.raises(CalculationInputError):
        candidates_under_peak(report, math.nan)


def test_encoder_speed_overlay_interpolation_and_boundaries(tmp_path):
    profile = scurve_profile(30, 2, 1, 0.8, 1000, step=0.2)
    log = tmp_path / "encoder.txt"
    log.write_text("time_s,speed_m_s\n" + "".join(
        f"{sample[0]},{sample[2]}\n" for sample in profile["samples"]
    ), encoding="utf-8")
    result = compare_speed_log(profile, load_speed_log(log))
    assert result["rmse_m_s"] == pytest.approx(0, abs=1e-10)
    assert result["max_error_m_s"] == pytest.approx(0, abs=1e-10)
    log.write_text("time_s,speed_m_s\n0,0\n0,1\n", encoding="utf-8")
    with pytest.raises(CalculationInputError):
        load_speed_log(log)
    with pytest.raises(CalculationInputError):
        compare_speed_log(profile, [(0, 0), (1, 1)])


def test_synthetic_log_is_reproducible_labelled_and_round_trips(tmp_path):
    profile = scurve_profile(8, 2, 1, 0.8, 1000)
    options = SyntheticOptions(seed=7, delay_s=0.02)
    first = generate_synthetic_log(profile, options)
    assert first == generate_synthetic_log(profile, options)
    assert first != generate_synthetic_log(profile, SyntheticOptions(seed=8))
    assert all(row["source"] == "SYNTHETIC_DEMO_NOT_MEASURED" for row in first)
    assert all(row["speed_m_s"] >= 0 for row in first)
    output = tmp_path / "synthetic.csv"
    assert save_synthetic_log(output, profile, options) == len(first)
    assert len(load_speed_log(output)) == len(first)
    assert compare_speed_log(profile, load_speed_log(output))["rmse_m_s"] > 0
    with pytest.raises(CalculationInputError):
        SyntheticOptions(joint_spacing_m=0)


def test_speed_log_rejects_corruption_and_preserves_interpolated_error(tmp_path):
    profile = scurve_profile(8, 2, 1, 0.8, 1000)
    log = tmp_path / "encoder.csv"
    log.write_text("time_s,wrong_unit\n0,0\n1,1\n", encoding="utf-8")
    with pytest.raises(CalculationInputError, match="머리글"):
        load_speed_log(log)
    log.write_text("time_s,speed_m_s\n0,0\n1,nan\n", encoding="utf-8")
    with pytest.raises(CalculationInputError, match="시간"):
        load_speed_log(log)
    log.write_text("time_s,speed_m_s\n0,0\n1,abc\n", encoding="utf-8")
    with pytest.raises(CalculationInputError, match="숫자"):
        load_speed_log(log)
    log.write_text("time_s,speed_m_s\n0,0\n", encoding="utf-8")
    with pytest.raises(CalculationInputError, match="두 개"):
        load_speed_log(log)
    log.write_text("time_s,speed_m_s\n" + "0,0\n" * 1_300_000, encoding="utf-8")
    with pytest.raises(CalculationInputError, match="5 MB"):
        load_speed_log(log)
    measured = [(sample[0], sample[2] + 0.1) for sample in profile["samples"]]
    result = compare_speed_log(profile, measured)
    assert result["rmse_m_s"] == pytest.approx(0.1, abs=1e-10)
    assert result["max_error_m_s"] == pytest.approx(0.1, abs=1e-10)


def test_component_spec_needs_provenance_and_physical_units(tmp_path):
    spec = {
        "motor_maker": "Motor Co", "motor_model": "M1", "motor_source": "motor catalog p.2",
        "rope_maker": "Rope Co", "rope_model": "R1", "rope_source": "rope catalog p.4",
        "sheave_maker": "Sheave Co", "sheave_model": "S1", "sheave_source": "drawing A-1",
        "rope_kg_m": 0.8, "sheave_radius_m": 0.4,
        "motor_inertia_kg_m2": 2, "motor_options_kw": [11, 15]
    }
    file = tmp_path / "parts.json"
    file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    loaded = load_component_spec(file)
    assert loaded.motor_maker == "Motor Co"
    assert loaded.rope_model == "R1"
    assert loaded.sheave_source == "drawing A-1"
    assert loaded.motor_options_kw == (11, 15)
    for invalid in ({**spec, "motor_source": ""}, {**spec, "rope_source": ""},
                    {**spec, "rope_kg_m": -1}, {**spec, "motor_options_kw": [True]},
                    {**spec, "unknown": 7}):
        file.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(CalculationInputError):
            load_component_spec(file)


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


def test_english_drawing_labels_extract_all_six_fields():
    matches = extract_fields(
        "Rated load 1000 kg\nRated speed 1.75 m/s\nTravel 30 m\n"
        "Car mass 1,200 kg\nMotor power 15 kW\nNumber of ropes 6\n"
    )
    assert [(item.key, item.value, item.unit) for item in matches] == [
        ("rated_load_kg", 1000, "kg"),
        ("speed_m_s", 1.75, "m/s"),
        ("distance_m", 30, "m"),
        ("car_kg", 1200, "kg"),
        ("motor_kw", 15, "kW"),
        ("rope_count", 6, "가닥"),
    ]
    assert matches[1].source_line == "Rated speed 1.75 m/s"


def test_english_label_units_convert_and_unrelated_text_is_ignored():
    matches = extract_fields(
        "RATED SPEED: 120 m/min\nTRAVEL DISTANCE = 30,000 mm\n"
        "Selected motor capacity: 18.5 KW\nCar weight 1450 kg\n"
        "Rope count 8\n"
        "unrated load 900 kg\nTravel time 20 s\n"
        "Rope diameter 10 mm\nMotor power 150 W\n"
        "Rated load 3 kg/m\nCar mass 0 kg\nRopes 6.5\n"
        "Travel 200 m²\nRated speed 0.8 m/s²\n"
    )
    assert [(item.key, item.value) for item in matches] == [
        ("speed_m_s", 2),
        ("distance_m", 30),
        ("motor_kw", 18.5),
        ("car_kg", 1450),
        ("rope_count", 8),
    ]


def test_pdf_table_with_labels_and_values_on_separate_lines():
    # pypdf's ordinary extraction of the user's synthetic two-column PDF
    # produces these alternating lines, even though the visible rows align.
    extracted_text = (
        "Item\nSpecified value\nRated load\n1000 kg\nRated speed\n1.75 m/s\n"
        "Travel\n30 m\nCar mass\n1400 kg\n"
        "Traction sheave diameter\n600 mm\nRope diameter\n10 mm\n"
        "Number of ropes\n6\nMotor rated power\n22 kW\n"
        "Motor voltage\n380 V\nDoor opening width\n900 mm\n"
    )
    candidates = extract_fields(extracted_text)
    assert [(item.key, item.value) for item in candidates] == [
        ("rated_load_kg", 1000), ("speed_m_s", 1.75),
        ("distance_m", 30), ("car_kg", 1400),
        ("rope_count", 6), ("motor_kw", 22),
    ]
    assert candidates[0].source_line == "Rated load | 1000 kg"
    assert extract_fields("Rated load\nMotor voltage\n380 V") == []


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


def test_pdf_text_reader_accepts_english_drawing_lines(tmp_path, monkeypatch):
    import pypdf

    source = tmp_path / "english_design.pdf"
    source.write_bytes(b"PDF test stub")

    class Page:
        def extract_text(self):
            return ("Rated load 1000 kg\nRated speed 1.75 m/s\n"
                    "Travel 30 m\nCar mass 1200 kg\nMotor power 15 kW")

    class Reader:
        def __init__(self, _path):
            self.pages = [Page()]

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    assert [(item.key, item.value) for item in read_document(source)] == [
        ("rated_load_kg", 1000), ("speed_m_s", 1.75),
        ("distance_m", 30), ("car_kg", 1200), ("motor_kw", 15),
    ]


def test_pdf_reader_prefers_table_layout_and_falls_back_to_plain(tmp_path, monkeypatch):
    import pypdf

    source = tmp_path / "two_columns.pdf"
    source.write_bytes(b"PDF test stub")

    class Page:
        def __init__(self, layout, plain):
            self.layout, self.plain = layout, plain

        def extract_text(self, extraction_mode=None):
            return self.layout if extraction_mode == "layout" else self.plain

    class Reader:
        def __init__(self, _path):
            self.pages = [
                Page("Rated load      1000 kg\nMotor rated power     22 kW",
                     "Rated load\n1000 kg\nMotor rated power\n22 kW"),
                Page("Header\nNo matches", "Rated speed\n120 m/min"),
            ]

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    matches = read_document(source)
    assert [(match.key, match.value) for match in matches] == [
        ("rated_load_kg", 1000), ("motor_kw", 22), ("speed_m_s", 2),
    ]
    assert matches[0].source_line == "Rated load 1000 kg"
