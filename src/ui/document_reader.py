"""Optional PDF/OCR input adapters; extracted fields remain untrusted.

Uses Tesseract for scanned files and pypdf for text PDFs.
"""

from pathlib import Path
import shutil
import subprocess
import tempfile

from src.core.document_fields import extract_fields
from src.core.errors import CalculationInputError


def _ocr(path):
    program = shutil.which("tesseract")
    if program is None:
        raise CalculationInputError("스캔 이미지 OCR에는 Tesseract 설치가 필요합니다.")
    try:
        languages = subprocess.run(
            [program, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
        language = "kor+eng" if "kor" in languages.split() else "eng"
        result = subprocess.run(
            [program, str(path), "stdout", "-l", language],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        raise CalculationInputError(f"문서 OCR 실패: {error}") from error
    return result.stdout


def read_document(path):
    source = Path(path)
    if not source.is_file() or source.stat().st_size > 12 * 1024 * 1024:
        raise CalculationInputError("문서를 찾을 수 없거나 12 MiB를 초과했습니다.")
    suffix = source.suffix.lower()
    if suffix in (".png", ".jpg", ".jpeg"):
        return extract_fields(_ocr(source))
    if suffix != ".pdf":
        raise CalculationInputError("PDF, PNG, JPG 파일만 지원합니다.")
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise CalculationInputError(
            "PDF 텍스트 읽기에는 pypdf 설치가 필요합니다."
        ) from error
    try:
        reader = PdfReader(str(source))
        page_candidates = []
        has_text = False
        for page in reader.pages[:5]:
            try:
                page_text = page.extract_text(extraction_mode="layout") or ""
            except TypeError:
                # Lightweight readers and older adapters may lack layout mode.
                page_text = ""
            has_text |= bool(page_text.strip())
            candidates = extract_fields(page_text)
            if not candidates:
                plain_text = page.extract_text() or ""
                has_text |= bool(plain_text.strip())
                candidates = extract_fields(plain_text)
            page_candidates.extend(candidates)
    except Exception as error:
        raise CalculationInputError(f"PDF 텍스트 읽기 실패: {error}") from error
    if has_text:
        # Do not pair labels on one page with values on another page.
        return page_candidates
    try:
        import fitz
    except ImportError as error:
        raise CalculationInputError(
            "스캔 PDF에는 PyMuPDF와 Tesseract 설치가 필요합니다."
        ) from error
    with tempfile.TemporaryDirectory() as folder:
        try:
            with fitz.open(str(source)) as doc:
                pages = []
                for index in range(min(5, len(doc))):
                    rendered = Path(folder) / f"page_{index}.png"
                    doc[index].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(
                        str(rendered)
                    )
                    pages.append(_ocr(rendered))
        except (RuntimeError, ValueError, OSError) as error:
            raise CalculationInputError(f"스캔 PDF 처리 실패: {error}") from error
    return extract_fields("\n".join(pages))
