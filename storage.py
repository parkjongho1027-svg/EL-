"""입력 기록·프로젝트 설정의 영구 저장."""
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from app_config import APP_BUILD, FORMULA_VERSION
from theme_manager import THEMES
from utils import clean_number_text

CALCULATOR_KEYS = ("motor", "traction", "brake", "traffic", "criteria", "scurve")

MAX_HISTORY_PER_CALCULATOR = 500

def get_data_file_path():
    """입력 기록과 화면 설정을 저장할 파일 위치를 반환합니다.

    Windows에서는 사용자별 LocalAppData 폴더를 사용하므로 프로그램 파일을
    다른 폴더로 옮겨도 기록이 유지되고, 관리자 권한 없이 저장할 수 있습니다.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        data_dir = Path(base) / "ElevatorIntegratedCalculator"
    else:
        data_dir = Path.home() / ".elevator_integrated_calculator"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "user_data.json"

def normalize_record(record):
    """같은 숫자를 2400 또는 2,400으로 입력해도 같은 기록으로 처리합니다."""
    normalized = {}
    for key, value in record.items():
        normalized[key] = value if key.startswith("__") else clean_number_text(value)
    return normalized

class PersistentStore:
    """이전 입력값·입력 기록·화면 모드를 종료 후에도 보관합니다."""

    def __init__(self):
        self.load_warning = ""
        try:
            self.path = get_data_file_path()
        except OSError as error:
            # 사용자 데이터 폴더에 접근할 수 없어도 계산 기능 자체는 사용할 수 있습니다.
            self.path = Path(tempfile.gettempdir()) / "elevator_calculator_user_data.json"
            self.load_warning = (
                "사용자 데이터 폴더를 열 수 없어 이번에는 임시 저장소를 사용합니다.\n"
                f"프로그램 종료 후 기록이 유지되지 않을 수 있습니다.\n{error}"
            )
        self.data = {
            "version": 2,
            "theme": "light",
            "always_on_top": False,
            "font_size": 10,
            "window_preset": "자동",
            # 새로 설치해 처음 실행할 때는 항상 한국어입니다. 사용자가 설정에서
            # 영어를 선택한 뒤에는 그 선택을 다음 실행에도 유지합니다.
            "language": "ko",
            "projects": [],
            "traffic_presets": {},
            "calculators": {
                key: {"previous": None, "history": []} for key in CALCULATOR_KEYS
            },
        }
        self.save_warning = ""
        self.on_save_error = None
        self._save_error_reported = ""
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("설정 파일의 최상위 항목이 객체가 아닙니다.")
            if loaded.get("theme") in THEMES:
                self.data["theme"] = loaded["theme"]
            if isinstance(loaded.get("always_on_top"), bool):
                self.data["always_on_top"] = loaded["always_on_top"]
            if loaded.get("font_size") in (9, 10, 11, 12, 13, 14):
                self.data["font_size"] = loaded["font_size"]
            if loaded.get("window_preset") in ("자동", "PC 1000×680", "데스크톱 1200×800"):
                self.data["window_preset"] = loaded["window_preset"]
            elif loaded.get("window_preset") in ("패드 900×650", "소형 760×600"):
                # 이전 빌드의 작은 화면 설정은 PC 전용 규격으로 자동 이전합니다.
                self.data["window_preset"] = "PC 1000×680"
            if loaded.get("language") in ("ko", "en"):
                self.data["language"] = loaded["language"]
            projects = loaded.get("projects", [])
            if isinstance(projects, list):
                self.data["projects"] = [item for item in projects if isinstance(item, dict)]
            presets = loaded.get("traffic_presets", {})
            if isinstance(presets, dict):
                self.data["traffic_presets"] = {
                    str(name): values for name, values in presets.items()
                    if isinstance(values, dict)
                }
            loaded_calculators = loaded.get("calculators", {})
            if not isinstance(loaded_calculators, dict):
                raise ValueError("계산 기록 형식이 올바르지 않습니다.")
            for key in CALCULATOR_KEYS:
                section = loaded_calculators.get(key, {})
                if not isinstance(section, dict):
                    raise ValueError(f"{key} 계산 기록 형식이 올바르지 않습니다.")
                previous = section.get("previous")
                history = section.get("history", [])
                if previous is None or isinstance(previous, dict):
                    self.data["calculators"][key]["previous"] = previous
                if isinstance(history, list):
                    valid_history = [item for item in history if isinstance(item, dict)]
                    self.data["calculators"][key]["history"] = \
                        valid_history[-MAX_HISTORY_PER_CALCULATOR:]
        except (OSError, ValueError, TypeError) as error:
            # 손상 파일을 그대로 두고 새 저장을 하면 기록을 덮어쓸 수 있으므로
            # 시각이 붙은 백업본을 먼저 만든 뒤 새 저장 파일을 사용합니다.
            backup_message = ""
            try:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup = self.path.with_name(f"user_data_corrupt_{stamp}.json")
                shutil.copy2(self.path, backup)
                backup_message = f"\n손상 파일 백업: {backup}"
            except OSError as backup_error:
                backup_message = f"\n손상 파일 백업도 실패했습니다: {backup_error}"
            self.load_warning = (
                f"기존 입력 기록이 손상되어 새 저장 공간으로 시작합니다.\n{error}"
                f"{backup_message}"
            )

    def save(self):
        """저장 중 중단되어도 원본이 손상되지 않도록 임시 파일을 거쳐 교체합니다."""
        try:
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(self.path)
            self.save_warning = ""
            return True
        except OSError as error:
            # 저장 실패가 계산 자체를 막지는 않도록 현재 실행 중 기록은 유지합니다.
            self.save_warning = f"입력 기록을 저장하지 못했습니다.\n{error}"
            if self.on_save_error and self._save_error_reported != self.save_warning:
                self._save_error_reported = self.save_warning
                self.on_save_error(self.save_warning)
            return False

    def simulation_history(self, mode=None):
        """시뮬레이션 입력 상태를 별도의 계산 기록 형식으로 유지한다."""
        history=self.data["calculators"]["scurve"]["history"]
        return [(i, item.copy()) for i,item in enumerate(history)
                if item.get("__simulation_mode__") in ("mechanical","electrical")
                and (mode is None or item["__simulation_mode__"]==mode)]

    def add_simulation(self, mode, state, summary):
        if mode not in ("mechanical","electrical"):
            raise ValueError("알 수 없는 시뮬레이션 종류입니다.")
        history=self.data["calculators"]["scurve"]["history"]
        record={"__simulation_mode__":mode,"__state__":state,
                "__result_summary__":str(summary),
                "__timestamp__":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "__formula_version__":FORMULA_VERSION}
        history.append(record)
        del history[:-MAX_HISTORY_PER_CALCULATOR]
        self.data["calculators"]["scurve"]["previous"]=record.copy()
        self.save()
        return record

    def delete_simulation(self, index):
        history=self.data["calculators"]["scurve"]["history"]
        if 0<=index<len(history) and history[index].get("__simulation_mode__") in ("mechanical","electrical"):
            del history[index]
            self.save()

    def previous(self, key):
        value = self.data["calculators"][key]["previous"]
        return value.copy() if isinstance(value, dict) else None

    def history(self, key):
        return [item.copy() for item in self.data["calculators"][key]["history"]]

    def set_previous(self, key, record):
        self.data["calculators"][key]["previous"] = normalize_record(record)
        self.save()

    def add_history(self, key, record, result_summary):
        if getattr(self, "_suppress_history", False):
            return
        stored = normalize_record(record)
        stored["__saved_at__"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stored["__result_summary__"] = result_summary
        stored["__app_build__"] = APP_BUILD
        stored["__formula_version__"] = FORMULA_VERSION
        history = self.data["calculators"][key]["history"]
        # 저장 시각과 결과 문구를 제외한 입력값이 직전 기록과 같으면 중복 저장하지 않습니다.
        ignored = {"__saved_at__", "__result_summary__"}
        comparable = {k: v for k, v in stored.items() if k not in ignored}
        if history:
            last = {k: v for k, v in history[-1].items() if k not in ignored}
        else:
            last = None
        if last != comparable:
            history.append(stored)
            del history[:-MAX_HISTORY_PER_CALCULATOR]
        self.data["calculators"][key]["previous"] = normalize_record(record)
        self.save()
        return self.history(key)

    def delete_history(self, key, index):
        history = self.data["calculators"][key]["history"]
        if 0 <= index < len(history):
            del history[index]
            self.save()
        return self.history(key)

    def clear_history(self, key):
        self.data["calculators"][key]["history"] = []
        self.save()

    def set_theme(self, mode):
        if mode in THEMES:
            self.data["theme"] = mode
            self.save()

    def set_always_on_top(self, enabled):
        self.data["always_on_top"] = bool(enabled)
        self.save()

    def set_ui_preferences(self, font_size=None, window_preset=None, language=None):
        """설정창에서 바꾼 화면 옵션을 한 번에 안전하게 저장합니다."""
        if font_size in (9, 10, 11, 12, 13, 14):
            self.data["font_size"] = int(font_size)
        if window_preset in ("자동", "PC 1000×680", "데스크톱 1200×800"):
            self.data["window_preset"] = window_preset
        if language in ("ko", "en"):
            self.data["language"] = language
        self.save()

    def rename_history(self, key, index, name):
        """선택한 계산 기록에 사용자가 알아볼 수 있는 이름을 붙입니다."""
        history = self.data["calculators"][key]["history"]
        if 0 <= index < len(history):
            history[index]["__name__"] = str(name).strip()
            self.save()
        return self.history(key)

    def projects(self):
        return [item.copy() for item in self.data.get("projects", [])]

    def save_project(self, project):
        """같은 ID의 프로젝트는 갱신하고, 새 ID면 목록 맨 뒤에 추가합니다."""
        projects = self.data.setdefault("projects", [])
        project = project.copy()
        project["__app_build__"] = APP_BUILD
        project["__formula_version__"] = FORMULA_VERSION
        project["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if str(project.get("manager", "")).strip():
            project["manager"] = str(project["manager"]).strip()
            self.data["last_project_manager"] = project["manager"]
        for index, existing in enumerate(projects):
            if existing.get("id") == project.get("id"):
                projects[index] = project
                break
        else:
            projects.append(project)
        self.save()
        return self.projects()

    def delete_project(self, project_id):
        projects = self.data.setdefault("projects", [])
        self.data["projects"] = [p for p in projects if p.get("id") != project_id]
        self.save()
        return self.projects()

    def delete_projects(self, project_ids):
        """선택한 여러 프로젝트를 한 번의 저장으로 삭제합니다."""
        project_ids = set(project_ids)
        projects = self.data.setdefault("projects", [])
        self.data["projects"] = [p for p in projects if p.get("id") not in project_ids]
        self.save()
        return self.projects()

    def rename_project(self, project_id, name):
        for project in self.data.setdefault("projects", []):
            if project.get("id") == project_id:
                project["name"] = str(name).strip()
                project["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.save()
                break
        return self.projects()

    def change_project_manager(self, project_id, manager):
        """프로젝트의 담당자만 바꾸고 원래 저장 시각은 유지합니다."""
        manager = str(manager).strip()
        for project in self.data.setdefault("projects", []):
            if project.get("id") == project_id:
                project["manager"] = manager
                if manager:
                    self.data["last_project_manager"] = manager
                self.save()
                break
        return self.projects()

    def save_traffic_preset(self, name, values):
        self.data.setdefault("traffic_presets", {})[str(name)] = normalize_record(values)
        self.save()

    def traffic_preset(self, name):
        value = self.data.get("traffic_presets", {}).get(str(name))
        return value.copy() if isinstance(value, dict) else None
