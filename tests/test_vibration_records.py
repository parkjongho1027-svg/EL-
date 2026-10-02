"""Saved vibration comparisons retain the original bytes and their analysis."""

import math

import pytest

from src.core.errors import CalculationInputError
from src.core.vibration_analysis import load_csv_signal
from src.persistence import storage
from src.services.vibration_records import (
    archived_path, prepare_vibration_record, remove_unreferenced_files, result_only_record,
)


def _signal(path, amplitude=1, rate=100):
    path.write_text(
        "time_s,acceleration_m_s2\n" + "".join(
            f"{index / rate},{amplitude * math.sin(index * 2 * math.pi / 10)}\n"
            for index in range(100)
        ), encoding="utf-8",
    )


def test_two_attached_signals_survive_source_deletion_and_record_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_data_file_path", lambda: tmp_path / "app" / "user_data.json")
    store = storage.PersistentStore()
    primary, baseline = tmp_path / "signal.csv", tmp_path / "baseline.csv"
    _signal(primary)
    _signal(baseline, amplitude=2)
    prepared = prepare_vibration_record(store, primary, baseline, None)
    assert prepared["comparison"]["rms"] == pytest.approx(prepared["data"]["rms"] * 2)
    saved = store.add_vibration_record("첫 진동 비교", "담당자", prepared)
    stored_files = [archived_path(store, saved[key]) for key in ("primary", "baseline")]
    assert all(path.is_file() for path in stored_files)
    assert stored_files[0].read_bytes() == primary.read_bytes()
    primary.unlink()
    baseline.unlink()
    reloaded = storage.PersistentStore()
    record = reloaded.vibration_records()[0]
    assert record["name"] == "첫 진동 비교"
    assert record["owner"] == "담당자"
    assert record["comparison"]["rms"] == pytest.approx(saved["comparison"]["rms"])
    assert load_csv_signal(archived_path(reloaded, record["primary"]))["rms"] == pytest.approx(record["data"]["rms"])
    reloaded.update_vibration_record(0, name="수정된 이름", owner="새 담당자")
    assert storage.PersistentStore().vibration_records()[0]["name"] == "수정된 이름"
    reloaded.delete_vibration_records([0])
    remove_unreferenced_files(reloaded)
    assert not any(path.exists() for path in stored_files)


def test_deduplicated_attachment_is_kept_until_last_record_is_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_data_file_path", lambda: tmp_path / "user_data.json")
    store = storage.PersistentStore()
    primary = tmp_path / "same.csv"
    _signal(primary)
    first = prepare_vibration_record(store, primary, "", None)
    second = prepare_vibration_record(store, primary, "", None)
    assert first["primary"]["blob"] == second["primary"]["blob"]
    store.add_vibration_record("A", "", first)
    store.add_vibration_record("B", "", second)
    archive = archived_path(store, first["primary"])
    store.delete_vibration_records([0])
    remove_unreferenced_files(store)
    assert archive.is_file()
    store.delete_vibration_records([0])
    remove_unreferenced_files(store)
    assert not archive.exists()


def test_bad_attachment_path_and_incompatible_signal_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_data_file_path", lambda: tmp_path / "user_data.json")
    store = storage.PersistentStore()
    assert archived_path(store, {"blob": "../../user_data.json"}) is None
    assert archived_path(store, {"blob": "else.csv"}) is None
    primary, baseline = tmp_path / "first.csv", tmp_path / "second.csv"
    _signal(primary)
    _signal(baseline, rate=120)
    with pytest.raises(CalculationInputError, match="주파수"):
        prepare_vibration_record(store, primary, baseline, None)
    with pytest.raises(CalculationInputError, match="CSV 또는 WAV"):
        prepare_vibration_record(store, tmp_path / "wrong.txt", "", None)


def test_failed_metadata_save_does_not_claim_record_was_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_data_file_path", lambda: tmp_path / "user_data.json")
    store = storage.PersistentStore()
    primary = tmp_path / "signal.csv"
    _signal(primary)
    prepared = prepare_vibration_record(store, primary, "", None)
    monkeypatch.setattr(store, "save", lambda: False)
    store.save_warning = "쓰기 오류"
    with pytest.raises(OSError, match="쓰기 오류"):
        store.add_vibration_record("A", "", prepared)
    assert store.vibration_records() == []


def test_result_only_fallback_retains_comparison_when_files_cannot_be_copied(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "get_data_file_path", lambda: tmp_path / "user_data.json")
    store = storage.PersistentStore()
    primary = tmp_path / "signal.csv"
    _signal(primary)
    report = load_csv_signal(primary)
    primary.unlink()
    prepared = result_only_record(primary, "", None, report, None, "파일을 찾을 수 없습니다.")
    saved = store.add_vibration_record("결과만 저장", "담당", prepared)
    assert archived_path(store, saved["primary"]) is None
    reloaded = storage.PersistentStore().vibration_records()[0]
    assert reloaded["data"]["rms"] == pytest.approx(report["rms"])
    assert "파일" in reloaded["archive_warning"]
