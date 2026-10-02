"""Archive user-supplied vibration signals with reproducible comparison results."""

import hashlib
from pathlib import Path
import re
import tempfile

from src.core.errors import CalculationInputError
from src.core.vibration_analysis import MAX_FILE_BYTES, load_csv_signal, load_wav_signal


_BLOB_NAME = re.compile(r"[0-9a-f]{64}\.(?:csv|wav)\Z")


def archived_path(store, attachment):
    """Resolve only filenames produced by this application's content-addressed archive."""
    if not isinstance(attachment, dict):
        return None
    name = attachment.get("blob")
    if not isinstance(name, str) or not _BLOB_NAME.fullmatch(name):
        return None
    return store.path.parent / "vibration_files" / name


def _archive_file(directory, filename):
    source = Path(filename)
    extension = source.suffix.lower()
    if extension not in (".csv", ".wav"):
        raise CalculationInputError("진동 기록은 CSV 또는 WAV 파일만 저장할 수 있습니다.")
    temporary = None
    try:
        if not source.is_file() or source.stat().st_size > MAX_FILE_BYTES:
            raise CalculationInputError("파일을 찾을 수 없거나 8 MiB를 초과했습니다.")
        directory.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as input_stream, tempfile.NamedTemporaryFile(
            dir=directory, prefix=".vibration_", suffix=".tmp", delete=False
        ) as output_stream:
            temporary = Path(output_stream.name)
            while chunk := input_stream.read(256 * 1024):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise CalculationInputError("파일이 읽는 동안 8 MiB를 초과했습니다.")
                digest.update(chunk)
                output_stream.write(chunk)
        blob = f"{digest.hexdigest()}{extension}"
        destination = directory / blob
        if destination.is_file() and _file_digest(destination) == digest.hexdigest():
            pass
        else:
            temporary.replace(destination)
        return {"name": source.name[:150], "blob": blob, "sha256": digest.hexdigest()}
    except OSError as error:
        raise CalculationInputError(f"첨부 파일 저장 실패: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(256 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_vibration_record(store, primary_path, baseline_path, sampling_hz):
    """Copy first, then analyse the copies so the saved result matches the saved bytes."""
    folder = store.path.parent / "vibration_files"
    primary = _archive_file(folder, primary_path)
    baseline = _archive_file(folder, baseline_path) if baseline_path else None

    def analyse(attachment):
        path = archived_path(store, attachment)
        return load_wav_signal(path) if path.suffix == ".wav" else load_csv_signal(path, sampling_hz)

    data = analyse(primary)
    comparison = analyse(baseline) if baseline else None
    if comparison and data["source_kind"] != comparison["source_kind"]:
        raise CalculationInputError("비교하려면 두 파일의 신호 형식과 단위를 일치시키세요.")
    if comparison and abs(data["sampling_hz"] / comparison["sampling_hz"] - 1) > 0.05:
        raise CalculationInputError("비교 파일의 샘플링 주파수가 5% 이상 다릅니다.")
    return {"primary": primary, "baseline": baseline, "sampling_hz": sampling_hz,
            "data": data, "comparison": comparison}


def result_only_record(primary_path, baseline_path, sampling_hz, data, comparison, reason):
    """Keep the analysed numbers when an original file cannot be archived."""
    return {
        "primary": {"name": Path(primary_path).name[:150], "blob": None},
        "baseline": {"name": Path(baseline_path).name[:150], "blob": None} if baseline_path else None,
        "sampling_hz": sampling_hz,
        "data": data,
        "comparison": comparison,
        "archive_warning": str(reason)[:300],
    }


def remove_unreferenced_files(store):
    """Retain shared blobs until the last record referring to them is removed."""
    folder = store.path.parent / "vibration_files"
    if not folder.is_dir():
        return
    referenced = {
        attachment["blob"]
        for record in store.vibration_records()
        for attachment in (record.get("primary"), record.get("baseline"))
        if isinstance(attachment, dict) and isinstance(attachment.get("blob"), str)
    }
    for path in folder.iterdir():
        if path.is_file() and (_BLOB_NAME.fullmatch(path.name) or path.name.startswith(".vibration_")) \
                and path.name not in referenced:
            path.unlink()
