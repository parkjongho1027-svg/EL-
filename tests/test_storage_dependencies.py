"""프로젝트 저장 자료 계층이 Tk 초기화에 의존하지 않는지 확인한다."""
import subprocess
import sys


def test_storage_import_does_not_load_tk():
    script = "import storage,sys; assert 'tkinter' not in sys.modules"
    subprocess.run([sys.executable, '-c', script], check=True, timeout=10)
