"""교통량 분석 입력, 가정, 결과 화면."""

from dataclasses import dataclass
from typing import Any, Callable, Mapping
import math
import tkinter as tk
from tkinter import ttk

from src.config.constants import FORMULA_VERSION
from src.core.calculators import (
    calculate_traffic_values,
    traffic_pdf_reference,
    traffic_visible_input_fields,
)
from src.ui.engineering_charts import show_capacity
from src.ui.graph_workspace import manage_graphs
from src.ui.theme_manager import bind_combobox_popdown_theme
from src.ui.ui_components import SkyButton, attach_numeric_validation, messagebox
from src.common.utils import parse_number, require_calculation, calculate_safely, ensure_positive


@dataclass(frozen=True)
class TrafficPanelServices:
    create_calculation_layout: Callable[..., Any]
    create_action_buttons: Callable[..., Any]
    create_result_display: Callable[..., Any]
    initial_result_text: Callable[..., Any]
    set_result_display: Callable[..., Any]
    push_undo_state: Callable[..., Any]
    undo_panel: Callable[..., Any]
    widget_language: Callable[..., Any]
    open_history_window: Callable[..., Any]
    show_unexpected_error: Callable[..., Any]
    choice_ko: Callable[[str], str]
    choice_en: Mapping[str, str]
    initial_result_message: str


class TrafficPanel(tk.Frame):
    """입력 가정과 적용 기준을 분리하여 교통량을 추정하는 패널입니다."""

    def __init__(self, parent, store, services):
        super().__init__(parent, bg="white")
        self.store = store
        self.services = services
        self.storage_key = "traffic"
        self.undo_stack = []

        note = (
            "PDF 교재의 용도별 인구·RTT·5분 수송능력 공식에 따른 초기 설계용 추정입니다.\n"
            "※ 선택한 건물용도에 해당하는 인구 입력항목만 사용하며, 다른 용도의 입력값은 무시합니다.\n"
            "※ 예상 정지수는 로컬 정지수(fL)+운행형식별 급행 정지수(fE)이며 손실시간률은 10%입니다.\n"
            "※ 교재는 대기시간을 운전간격의 1/2와 약 60%로 각각 설명하므로 환산율을 직접 확인하세요."
        )
        left, right = self.services.create_calculation_layout(
            self, note, formula_key="traffic"
        )
        self.input_area = left

        fields = [
            ("A", "오피스 층별 이용면적", "m² (오피스만)"),
            ("F", "건물층수(총 층수)", "층"),
            ("excluded_floors", "인구산정 제외층수", "층 (오피스 기본 2)"),
            ("floor_areas", "오피스 층별 면적목록", "m² (; 구분, 선택)"),
            ("S", "오피스 1인당 면적", "m²/인"),
            ("households", "공동주택 세대수", "세대"),
            ("persons_per_household", "세대당 거주인구", "인/세대"),
            ("rooms", "호텔 객실수", "실"),
            ("guests_per_room", "객실당 수용인원", "인/실 (교재 예시 2)"),
            ("beds", "병원 병상수", "병상"),
            ("direct_population", "직접 입력 건물인구", "인 (기타 용도)"),
            ("phi", "집중률 φ", "%"),
            ("C", "카 정원", "인"),
            ("board_rate", "탑승률", "%"),
            ("n", "로컬 정지층수 n", "층"),
            ("td", "도어 개폐시간", "초/층"),
            ("tp", "승객 출입시간", "초/인"),
            ("Tr_travel", "주행시간", "초"),
            ("wait_factor", "대기시간 환산율", "% (운전간격 대비)"),
            ("N_current", "현재 설치대수", "대 (선택)"),
        ]
        self.field_order = [key for key, _label, _unit in fields]
        self.field_rows = {}
        self.entries = {}
        self.input_history = self.store.history(self.storage_key)
        self.previous_values = self.store.previous(self.storage_key)

        settings = tk.Frame(left, bg="white")
        settings.pack(fill="x", padx=10, pady=(1, 3))
        tk.Label(
            settings, text="건물용도", width=18, anchor="w", font=("맑은 고딕", 10)
        ).pack(side="left")
        self.building_use = tk.StringVar(value="사용자 설정")
        self.building_use_combo = ttk.Combobox(
            settings,
            textvariable=self.building_use,
            state="readonly",
            width=15,
            values=(
                "오피스-전용사옥",
                "오피스-복합사옥",
                "오피스-공공건물",
                "오피스-임대사무실",
                "공동주택",
                "호텔-고급",
                "호텔-중급",
                "호텔-비즈니스",
                "병원",
                "판매시설",
                "사용자 설정",
            ),
        )
        self.building_use_combo.pack(side="left", padx=5)
        bind_combobox_popdown_theme(self.building_use_combo)
        self.building_use_combo.bind(
            "<<ComboboxSelected>>", self._on_building_use_changed
        )
        SkyButton(
            settings,
            text="용도값 저장",
            command=self.save_use_preset,
            font=("맑은 고딕", 8),
            width=9,
            padx=2,
            pady=1,
        ).pack(side="left", padx=(3, 2))
        SkyButton(
            settings,
            text="용도값 적용",
            command=self.load_use_preset,
            font=("맑은 고딕", 8),
            width=9,
            padx=2,
            pady=1,
        ).pack(side="left")

        # 스크롤 입력영역보다 먼저 하단 공간을 예약해야 버튼이 입력박스
        # 경계에 눌려 잘리지 않습니다. 크기는 다른 세 계산창과 동일합니다.
        action_buttons = self.services.create_action_buttons(
            left,
            self.calculate,
            [
                ("clear", "입력값 삭제", self.clear, "normal"),
                ("previous", "이전 입력값", self.restore_previous, "disabled"),
                ("history", "입력 기록", self.show_history, "disabled"),
            ],
            side="bottom",
        )
        self.action_buttons = action_buttons
        self.previous_button = action_buttons["previous"]
        self.history_button = action_buttons["history"]
        if self.previous_values:
            self.previous_button.config(state="normal")
        if self.input_history:
            self.history_button.config(state="normal")

        chart_actions = tk.Frame(left, bg='white')
        chart_actions.pack(side='bottom', anchor='w', fill='x', padx=9, pady=2)
        for title, action in (
            ('층별 5분 수송 그래프', lambda: show_capacity(self)),
            ('그래프 관리', lambda: manage_graphs(self, 'traffic')),
        ):
            SkyButton(chart_actions, text=title, command=action,
                      font=('맑은 고딕', 9)).pack(side='left', padx=(0, 4))

        scroll_host = tk.Frame(left, bg="white")
        scroll_host.pack(fill="both", expand=True, padx=5)
        canvas = tk.Canvas(scroll_host, highlightthickness=0, height=400)
        vertical = ttk.Scrollbar(scroll_host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vertical.set)
        canvas.pack(side="left", fill="both", expand=True)
        vertical.pack(side="right", fill="y")
        form = tk.Frame(canvas, bg="white")
        form_window = canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind(
            "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>", lambda e: canvas.itemconfigure(form_window, width=e.width)
        )
        self.input_canvas = canvas

        def scroll_input(event):
            """입력칸에 포커스가 있어도 교통량 입력영역을 스크롤합니다."""
            if getattr(event, "num", None) == 4:
                direction = -1
            elif getattr(event, "num", None) == 5:
                direction = 1
            else:
                direction = int(-event.delta / 120) if event.delta else 0
            if direction:
                canvas.yview_scroll(direction, "units")
            return "break"

        canvas.bind("<MouseWheel>", scroll_input, add="+")
        canvas.bind("<Button-4>", scroll_input, add="+")
        canvas.bind("<Button-5>", scroll_input, add="+")

        self.stop_count_mode = tk.StringVar(value="실제 정지층수 직접 입력")
        self.service_type = tk.StringVar(value="로컬 운전 (fE=0)")
        self.traffic_choice_combos = []
        for label, variable, choices in (
            (
                "정지층수 산정",
                self.stop_count_mode,
                ("실제 정지층수 직접 입력", "교재 기준: 총 층수-2"),
            ),
            (
                "운행 서비스형식",
                self.service_type,
                ("로컬 운전 (fE=0)", "편도구간 급행 (fE=1)", "전층 자유 운전 (fE=2)"),
            ),
        ):
            row = tk.Frame(form, bg="white")
            row.pack(anchor="w", fill="x", pady=2)
            tk.Label(
                row, text=label, font=("맑은 고딕", 10), width=18, anchor="w"
            ).pack(side="left")
            combo = ttk.Combobox(
                row,
                textvariable=variable,
                values=choices,
                state="readonly",
                width=24,
                font=("맑은 고딕", 9),
            )
            combo.pack(side="left", padx=5)
            bind_combobox_popdown_theme(combo)
            self.traffic_choice_combos.append((variable, combo, tuple(choices)))
        for key, label, unit in fields:
            row = tk.Frame(form, bg="white")
            row.pack(anchor="w", fill="x", pady=2)
            tk.Label(
                row,
                text=label,
                font=("맑은 고딕", 10),
                bg="white",
                width=18,
                anchor="w",
            ).pack(side="left")
            entry_width = 23 if key == "floor_areas" else 12
            e = tk.Entry(
                row, font=("맑은 고딕", 10), width=entry_width, justify="right"
            )
            attach_numeric_validation(e, list_mode=key == "floor_areas")
            e.pack(side="left", padx=5)
            tk.Label(row, text=unit, font=("맑은 고딕", 10), bg="white").pack(
                side="left"
            )
            self.field_rows[key] = row
            self.entries[key] = e
            e.bind("<Return>", lambda _event: self.calculate())

        self.entries["excluded_floors"].insert(0, "2")
        self.entries["guests_per_room"].insert(0, "2")
        self.entries["wait_factor"].insert(0, "50")

        self.criterion_row = tk.Frame(form, bg="white")
        self.criterion_row.pack(anchor="w", fill="x", pady=2)
        tk.Label(
            self.criterion_row,
            text="서비스 판정",
            width=18,
            anchor="w",
            font=("맑은 고딕", 10),
        ).pack(side="left")
        self.criterion_mode = tk.StringVar(value="PDF 교재 기준")
        criterion_combo = ttk.Combobox(
            self.criterion_row,
            textvariable=self.criterion_mode,
            state="readonly",
            width=15,
            values=("PDF 교재 기준", "판정 안 함", "사용자 정의 기준"),
        )
        criterion_combo.pack(side="left", padx=5)
        bind_combobox_popdown_theme(criterion_combo)
        self.traffic_choice_combos.append(
            (
                self.criterion_mode,
                criterion_combo,
                ("PDF 교재 기준", "판정 안 함", "사용자 정의 기준"),
            )
        )

        for key, label, unit in (
            ("good_threshold", "양호 기준 이하", "초"),
            ("bad_threshold", "불량 기준 초과", "초"),
            ("criterion_source", "판정 기준 메모(선택)", "문서명·사내기준 등"),
        ):
            row = tk.Frame(form, bg="white")
            row.pack(anchor="w", fill="x", pady=2)
            tk.Label(
                row, text=label, width=18, anchor="w", font=("맑은 고딕", 10)
            ).pack(side="left")
            entry = tk.Entry(
                row,
                font=("맑은 고딕", 10),
                width=23 if key == "criterion_source" else 12,
                justify="right" if key != "criterion_source" else "left",
            )
            if key != "criterion_source":
                attach_numeric_validation(entry)
            entry.pack(side="left", padx=5)
            tk.Label(row, text=unit, font=("맑은 고딕", 10)).pack(side="left")
            self.entries[key] = entry
            entry.bind("<Return>", lambda _event: self.calculate())

        # Windows에서는 휠 이벤트가 포커스를 가진 Entry/Combobox에 전달됩니다.
        # 따라서 캔버스뿐 아니라 입력영역의 모든 자식에도 같은 핸들러를 연결합니다.
        def bind_input_wheel(widget):
            widget.bind("<MouseWheel>", scroll_input, add="+")
            widget.bind("<Button-4>", scroll_input, add="+")
            widget.bind("<Button-5>", scroll_input, add="+")
            for child in widget.winfo_children():
                bind_input_wheel(child)

        bind_input_wheel(form)

        self._update_use_fields()

        self.result_text = self.services.create_result_display(right)
        self.initial_result_message = self.services.initial_result_message
        self._show(self.services.initial_result_text(self))

    def _show(self, text, error=False):
        """교통량 결과와 오류를 공통 결과창 형식으로 표시합니다."""
        self.services.set_result_display(self.result_text, text, error)

    def _get(self, key, label):
        raw = self.entries[key].get().strip()
        if raw == "":
            raise ValueError(f"'{label}' 값을 입력해주세요.")
        return parse_number(raw, label)

    def _get_optional(self, key, label):
        raw = self.entries[key].get().strip()
        return None if raw == "" else parse_number(raw, label)

    def _visible_use_fields(self):
        """선택한 건물용도에서 실제로 사용하는 입력항목을 반환합니다."""
        return traffic_visible_input_fields(
            self.services.choice_ko(self.building_use.get())
        )

    def apply_choice_language(self, language):
        """교통량 선택항목은 표시만 번역하고 계산용 내부 의미는 유지합니다."""
        variables = [
            (
                self.building_use,
                self.building_use_combo,
                tuple(self.services.choice_en.keys())[:11],
            ),
            *self.traffic_choice_combos,
        ]
        seen = set()
        for variable, combo, korean_values in variables:
            if str(combo) in seen:
                continue
            seen.add(str(combo))
            current_ko = self.services.choice_ko(variable.get())
            display_values = (
                tuple(
                    self.services.choice_en.get(value, value) for value in korean_values
                )
                if language == "en"
                else tuple(korean_values)
            )
            combo.configure(values=display_values)
            variable.set(
                self.services.choice_en.get(current_ko, current_ko)
                if language == "en"
                else current_ko
            )

    def _update_use_fields(self):
        """다른 용도의 입력칸은 숨기고 현재 용도에 필요한 칸만 배치합니다."""
        visible = self._visible_use_fields()
        for row in self.field_rows.values():
            row.pack_forget()
        for key in self.field_order:
            if key in visible:
                self.field_rows[key].pack(
                    before=self.criterion_row, anchor="w", fill="x", pady=2
                )

    def _focus_first_use_field(self):
        """현재 용도에서 가장 먼저 입력할 항목으로 포커스를 이동합니다."""
        building_use = self.services.choice_ko(self.building_use.get())
        if building_use.startswith("오피스-"):
            key = "A"
        elif building_use == "공동주택":
            key = "households"
        elif building_use.startswith("호텔-"):
            key = "rooms"
        elif building_use == "병원":
            key = "beds"
        else:
            key = "direct_population"
        self.entries[key].focus_set()

    def _on_building_use_changed(self, _event=None):
        """건물용도를 바꾸는 즉시 필요한 입력칸만 다시 표시합니다."""
        self._update_use_fields()
        self._focus_first_use_field()

    def save_use_preset(self):
        """현재 입력을 선택한 건물용도의 사용자 기본값으로 저장합니다."""
        english = self.services.widget_language(self) == "en"
        use_name = self.services.choice_ko(self.building_use.get())
        display_name = (
            self.services.choice_en.get(use_name, use_name) if english else use_name
        )
        if use_name == "사용자 설정":
            messagebox.showinfo(
                "Building-use Preset" if english else "건물용도 기본값",
                "Select a specific building use first."
                if english
                else "먼저 구체적인 건물용도를 선택해주세요.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Building-use Preset" if english else "건물용도 기본값",
            (
                f"Save the current inputs as the preset for ‘{display_name}’?"
                if english
                else f"현재 입력값을 ‘{use_name}’의 사용자 기본값으로 저장할까요?"
            ),
            parent=self,
        ):
            return
        self.store.save_traffic_preset(use_name, self.capture_state())
        if self.store.save_warning:
            return
        messagebox.showinfo(
            "Building-use Preset" if english else "건물용도 기본값",
            (
                "Preset saved. You can maintain source-verified values directly."
                if english
                else "저장했습니다. 출처가 확인된 값을 직접 관리할 수 있습니다."
            ),
            parent=self,
        )

    def load_use_preset(self):
        """선택한 건물용도에 사용자가 저장한 값을 입력칸에 적용합니다."""
        english = self.services.widget_language(self) == "en"
        use_name = self.services.choice_ko(self.building_use.get())
        display_name = (
            self.services.choice_en.get(use_name, use_name) if english else use_name
        )
        preset = self.store.traffic_preset(use_name)
        if not preset:
            messagebox.showinfo(
                "Building-use Preset" if english else "건물용도 기본값",
                (
                    f"No preset is saved for ‘{display_name}’."
                    if english
                    else f"‘{use_name}’에 저장된 사용자 기본값이 없습니다."
                ),
                parent=self,
            )
            return
        self.apply_state(preset)
        self._show(
            f"Loaded the preset for ‘{display_name}’. Check the criteria and inputs."
            if english
            else f"‘{use_name}’ 사용자 기본값을 불러왔습니다. 기준과 입력값을 확인하세요."
        )

    def capture_state(self):
        state = {key: entry.get() for key, entry in self.entries.items()}
        state["__building_use__"] = self.services.choice_ko(self.building_use.get())
        state["__criterion_mode__"] = self.services.choice_ko(self.criterion_mode.get())
        state["__stop_count_mode__"] = self.services.choice_ko(
            self.stop_count_mode.get()
        )
        state["__service_type__"] = self.services.choice_ko(self.service_type.get())
        return state

    def apply_state(self, state, remember_undo=True):
        if remember_undo:
            self.services.push_undo_state(self)
        self.building_use.set(state.get("__building_use__", "사용자 설정"))
        self.criterion_mode.set(state.get("__criterion_mode__", "PDF 교재 기준"))
        self.stop_count_mode.set(
            state.get("__stop_count_mode__", "실제 정지층수 직접 입력")
        )
        self.service_type.set(state.get("__service_type__", "로컬 운전 (fE=0)"))
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            defaults = {
                "excluded_floors": "2",
                "guests_per_room": "2",
                "wait_factor": "50",
            }
            default = defaults.get(key, "")
            entry.insert(0, state.get(key, default) or default)
        self._update_use_fields()
        self.apply_choice_language(getattr(self.winfo_toplevel(), "_language", "ko"))

    def undo_last(self):
        self.services.undo_panel(self)

    def clear(self):
        self.services.push_undo_state(self)
        current = self.capture_state()
        if any(str(current.get(key, "")).strip() for key in self.entries):
            self.store.set_previous(self.storage_key, current)
            self.previous_values = self.store.previous(self.storage_key)
            self.previous_button.config(state="normal")
        for entry in self.entries.values():
            entry.delete(0, tk.END)
        self.entries["excluded_floors"].insert(0, "2")
        self.entries["guests_per_room"].insert(0, "2")
        self.entries["wait_factor"].insert(0, "50")
        self.building_use.set("사용자 설정")
        self.criterion_mode.set("PDF 교재 기준")
        self.stop_count_mode.set("실제 정지층수 직접 입력")
        self.service_type.set("로컬 운전 (fE=0)")
        self._update_use_fields()
        self.apply_choice_language(getattr(self.winfo_toplevel(), "_language", "ko"))
        self._show(self.services.initial_result_text(self))
        self._focus_first_use_field()

    def _remember_input(self, result_summary):
        record = self.capture_state()
        self.input_history = self.store.add_history(
            self.storage_key, record, result_summary
        )
        self.previous_values = self.store.previous(self.storage_key)
        self.previous_button.config(state="normal")
        self.history_button.config(state="normal")

    def restore_previous(self):
        """가장 최근에 계산하거나 삭제하기 전에 입력했던 조건을 복원합니다."""
        if self.previous_values is None:
            return
        self.apply_state(self.previous_values)
        self._show(
            "Previous inputs loaded. Check the values, then calculate."
            if self.services.widget_language(self) == "en"
            else "이전 입력값을 불러왔습니다. 값을 확인한 뒤 계산하세요."
        )
        self._focus_first_use_field()

    def show_history(self):
        specs = [
            ("__building_use__", "건물용도", 90),
            ("__criterion_mode__", "판정방식", 100),
            ("__stop_count_mode__", "정지층수 방식", 110),
            ("__service_type__", "서비스형식", 110),
            ("A", "오피스 층면적", 90),
            ("F", "총 층수", 70),
            ("excluded_floors", "제외층수", 70),
            ("floor_areas", "층별면적", 120),
            ("S", "점유면적", 90),
            ("phi", "집중률(%)", 85),
            ("households", "세대수", 70),
            ("persons_per_household", "세대당인원", 80),
            ("rooms", "객실수", 70),
            ("guests_per_room", "객실당인원", 80),
            ("beds", "병상수", 70),
            ("direct_population", "직접인구", 80),
            ("C", "카 정원", 70),
            ("board_rate", "탑승률(%)", 85),
            ("n", "정지층수", 80),
            ("td", "도어시간", 80),
            ("tp", "출입시간", 80),
            ("Tr_travel", "주행시간", 80),
            ("wait_factor", "대기환산율", 80),
            ("N_current", "현재대수", 70),
            ("good_threshold", "양호기준", 75),
            ("bad_threshold", "불량기준", 75),
            ("criterion_source", "판정기준 메모", 110),
        ]
        self.services.open_history_window(
            self,
            "교통량 분석 입력 기록",
            self.input_history,
            specs,
            self._load_history_record,
            self._delete_history_record,
            self._clear_history,
            self._rename_history_record,
        )

    def _rename_history_record(self, index, name):
        self.input_history = self.store.rename_history(self.storage_key, index, name)
        return self.input_history

    def _delete_history_record(self, index):
        self.input_history = self.store.delete_history(self.storage_key, index)
        if not self.input_history:
            self.history_button.config(state="disabled")
        return self.input_history

    def _clear_history(self):
        self.store.clear_history(self.storage_key)
        self.input_history.clear()
        self.history_button.config(state="disabled")

    def _load_history_record(self, record, record_number):
        self.apply_state(record)
        clean_record = self.capture_state()
        self.store.set_previous(self.storage_key, clean_record)
        self.previous_values = self.store.previous(self.storage_key)
        self.previous_button.config(state="normal")
        self._show(
            (
                f"Input record {record_number} loaded. Check the values, then calculate."
                if self.services.widget_language(self) == "en"
                else f"입력 기록 {record_number}번을 불러왔습니다. 값을 확인한 뒤 계산하세요."
            )
        )
        self._focus_first_use_field()

    def calculate(self):
        english = self.services.widget_language(self) == "en"
        self.last_capacity_inputs = None
        self._last_capacity_state = None
        try:
            building_use = self.services.choice_ko(self.building_use.get())
            A = self._get_optional("A", "오피스 층별 이용면적")
            F = self._get("F", "건물층수")
            excluded = self._get("excluded_floors", "인구산정 제외층수")
            S = self._get_optional("S", "오피스 1인당 면적")
            phi = self._get("phi", "집중률") / 100
            C = self._get("C", "카 정원")
            board_rate = self._get("board_rate", "탑승률") / 100
            td = self._get("td", "도어 개폐시간")
            tp = self._get("tp", "승객 출입시간")
            Tr_travel = self._get("Tr_travel", "주행시간")
            wait_factor = self._get("wait_factor", "대기시간 환산율") / 100
            current_cars = self._get_optional("N_current", "현재 설치대수")

            if (
                self.services.choice_ko(self.stop_count_mode.get())
                == "교재 기준: 총 층수-2"
            ):
                n = F - 2
                if n <= 0:
                    raise ValueError("교재식 정지층수는 총 층수가 2층보다 커야 합니다.")
            else:
                n = self._get("n", "실제 정지층수")
            express_stops = {
                "로컬 운전 (fE=0)": 0,
                "편도구간 급행 (fE=1)": 1,
                "전층 자유 운전 (fE=2)": 2,
            }[self.services.choice_ko(self.service_type.get())]

            floor_areas = []
            floor_areas_text = self.entries["floor_areas"].get().strip()
            if floor_areas_text:
                floor_areas = [
                    parse_number(item, "층별 유효면적")
                    for item in floor_areas_text.split(";")
                    if item.strip()
                ]

            included = int(F - excluded)
            population_basis = ""
            households = rooms = persons = guests = beds = None
            if building_use.startswith("오피스-"):
                if A is None and not floor_areas:
                    raise ValueError(
                        "오피스는 '층별 이용면적' 또는 '층별 면적목록'이 필요합니다."
                    )
                if S is None:
                    raise ValueError("오피스는 '1인당 면적'이 필요합니다.")
                total_area = sum(floor_areas) if floor_areas else A * included
                population = total_area / S
                population_basis = "PDF 오피스식: 총 사무실 이용면적÷1인당 면적"
            elif building_use == "공동주택":
                households = self._get("households", "공동주택 세대수")
                persons = self._get("persons_per_household", "세대당 거주인구")
                population = households * persons
                total_area = None
                population_basis = "PDF 공동주택식: 세대수×세대당 거주인구"
            elif building_use.startswith("호텔-"):
                rooms = self._get("rooms", "호텔 객실수")
                guests = self._get("guests_per_room", "객실당 수용인원")
                population = rooms * guests
                total_area = None
                population_basis = (
                    "PDF 호텔식: 객실수×객실당 수용인원(또는 숙박 가능 인원)"
                )
            elif building_use == "병원":
                beds = self._get("beds", "병원 병상수")
                population = beds
                total_area = None
                population_basis = "PDF 병원식: 병상수"
            else:
                population = self._get("direct_population", "직접 입력 건물인구")
                total_area = None
                population_basis = "사용자 직접 입력 인구"

            positive_values = [
                (F, "건물층수"),
                (population, "건물인구"),
                (phi, "집중률"),
                (C, "카 정원"),
                (board_rate, "탑승률"),
                (n, "정지층수"),
                (td, "도어 개폐시간"),
                (tp, "승객 출입시간"),
                (Tr_travel, "주행시간"),
            ]
            if building_use.startswith("오피스-"):
                positive_values.append((S, "오피스 1인당 면적"))
                if A is not None:
                    positive_values.append((A, "오피스 층별 이용면적"))
            for value, label in positive_values:
                ensure_positive(value, label)
            for area in floor_areas:
                ensure_positive(area, "층별 유효면적")
            for value, label in (
                (households, "공동주택 세대수"),
                (persons, "세대당 거주인구"),
                (rooms, "호텔 객실수"),
                (guests, "객실당 수용인원"),
                (beds, "병원 병상수"),
            ):
                if value is not None:
                    ensure_positive(value, label)
            if not 0 <= excluded < F:
                raise ValueError(
                    "'인구산정 제외층수'는 0 이상이며 총 층수보다 작아야 합니다."
                )
            if not 0 < phi <= 1 or not 0 < board_rate <= 1 or not 0 < wait_factor <= 1:
                raise ValueError(
                    "집중률·탑승률·대기시간 환산율은 0 초과 100 이하의 %여야 합니다."
                )
            for value, label in (
                (F, "건물층수"),
                (excluded, "이용인구 제외층수"),
                (C, "카 정원"),
                (n, "정지층수"),
            ):
                if not value.is_integer():
                    raise ValueError(f"'{label}'은(는) 정수로 입력해주세요.")
            for value, label in (
                (households, "공동주택 세대수"),
                (rooms, "호텔 객실수"),
                (beds, "병원 병상수"),
            ):
                if value is not None and not value.is_integer():
                    raise ValueError(f"'{label}'은(는) 정수로 입력해주세요.")
            if n > F:
                raise ValueError(f"'정지층수'는 총 {int(F)}층보다 클 수 없습니다.")
            if n + express_stops > F:
                raise ValueError(
                    "로컬 정지층수와 급행 정지수의 합은 총 층수보다 클 수 없습니다."
                )
            if (
                building_use.startswith("오피스-")
                and floor_areas
                and len(floor_areas) != included
            ):
                raise ValueError(
                    f"층별 유효면적은 제외 후 유효층수 {included}개와 같은 개수로 입력해주세요."
                )
            if current_cars is not None:
                ensure_positive(current_cars, "현재 설치대수")
                if not current_cars.is_integer():
                    raise ValueError("'현재 설치대수'는 정수로 입력해주세요.")

            calculated = require_calculation(
                calculate_safely(
                    calculate_traffic_values,
                    {
                        "A": A or 0,
                        "F": F,
                        "excluded_floors": excluded,
                        "floor_areas": floor_areas,
                        "S": S or 1,
                        "population": population,
                        "phi": phi,
                        "C": C,
                        "board_rate": board_rate,
                        "n": n,
                        "td": td,
                        "tp": tp,
                        "Tr_travel": Tr_travel,
                        "wait_factor": wait_factor,
                        "express_stops": express_stops,
                    },
                )
            )
            if not all(
                math.isfinite(value)
                for key, value in calculated.items()
                if isinstance(value, (int, float))
            ):
                raise ValueError(
                    "계산 결과의 숫자 범위가 너무 큽니다. 입력값을 확인하세요."
                )

            N = calculated["recommended"]
            self.last_capacity_inputs = {
                "floors": int(F),
                "cars": int(current_cars or N),
                "seats": int(C),
                "board_rate": board_rate,
                "travel_s": Tr_travel,
                "door_s": td,
                "passenger_s": tp,
            }
            self._last_capacity_state = self.capture_state()
            AIT = calculated["interval"]
            AWT = calculated["wait"]
            reference = traffic_pdf_reference(
                building_use,
                F,
                population=population,
                total_area=total_area,
                households=households,
                rooms=rooms,
            )

            criterion_line = "서비스 판정: 적용하지 않음 (확인된 기준을 선택하지 않음)"
            if self.services.choice_ko(self.criterion_mode.get()) == "PDF 교재 기준":
                target = reference["interval_target"]
                if target is None:
                    criterion_line = "PDF 운전간격 판정: 이 용도에 제시된 기준 없음"
                elif building_use == "공동주택":
                    if AIT < 60:
                        grade = "교재 목표범위보다 짧음"
                    elif AIT <= 90:
                        grade = "교재 목표범위 충족"
                    else:
                        grade = "교재 목표범위 초과"
                    criterion_line = (
                        f"PDF 운전간격 판정: {grade} "
                        "(표 1-11 공동주택 60~90초 이하 예시)"
                    )
                elif building_use.startswith("오피스-"):
                    if AIT <= 30:
                        grade = "목표 충족"
                    elif AIT <= 40:
                        grade = "수송능력 충분 여부 추가 확인"
                    else:
                        grade = "교재 목표 초과"
                    criterion_line = (
                        f"PDF 운전간격 판정: {grade} "
                        "(표 1-11 오피스 30초 이하, 수송능력 충분 시 40초까지)"
                    )
                elif building_use.startswith("호텔-"):
                    grade = "목표 충족" if AIT <= 40 else "교재 목표 초과"
                    criterion_line = (
                        f"PDF 운전간격 판정: {grade} (표 1-11 호텔 40초 이하 예시)"
                    )
            elif (
                self.services.choice_ko(self.criterion_mode.get()) == "사용자 정의 기준"
            ):
                good = self._get("good_threshold", "양호 기준")
                bad = self._get("bad_threshold", "불량 기준")
                source = self.entries["criterion_source"].get().strip()
                ensure_positive(good, "양호 기준")
                ensure_positive(bad, "불량 기준")
                if good > bad:
                    raise ValueError("양호 기준은 불량 기준보다 작거나 같아야 합니다.")
                grade = "양호" if AIT <= good else ("불량" if AIT > bad else "보통")
                criterion_line = f"사용자 기준 판정: {grade}"
                if source:
                    criterion_line += f" (메모: {source})"

            self._remember_input(
                (
                    f"Recommended cars {N}, interval {AIT:.2f} s, average wait {AWT:.2f} s"
                    if english
                    else f"수송능력 산정 {N}대, 운전간격 {AIT:.2f}초, 평균대기 {AWT:.2f}초"
                )
            )

            result = "[교통량 분석 결과 — 입력 가정에 따른 추정]\n\n"
            result += f"건물용도 분류             = {self.services.choice_ko(self.building_use.get())}\n"
            result += f"이용인구 산정근거         = {population_basis}\n"
            if building_use.startswith("오피스-"):
                area_mode = "층별 개별 면적" if floor_areas else "모든 유효층 동일 면적"
                result += f"면적 적용                 = {area_mode}\n"
                result += (
                    f"인구산정 유효층 / 총 면적 = {included}층 / "
                    f"{calculated['total_area']:.1f} m²\n"
                )
            elif building_use == "공동주택":
                result += (
                    f"세대수 × 세대당 인원      = {int(households)} × {persons:g}\n"
                )
            elif building_use.startswith("호텔-"):
                result += f"객실수 × 객실당 인원      = {int(rooms)} × {guests:g}\n"
            elif building_use == "병원":
                result += f"병상수                     = {int(beds)} 병상\n"
            result += f"예상 이용인구 M           = {calculated['population']:.1f} 인\n"
            result += f"승객수 r                  = {calculated['riders']:.2f} 인\n"
            result += (
                f"예상 정지수 fL+fE         = {calculated['local_stops']:.2f} + "
                f"{calculated['express_stops']:g} = {calculated['expected_stops']:.2f}\n"
            )
            result += f"도어 / 출입 / 손실시간    = {calculated['door_time']:.2f} / {calculated['passenger_time']:.2f} / {calculated['loss_time']:.2f} 초\n"
            result += (
                f"일주시간 RTT              = {calculated['round_trip']:.2f} 초\n\n"
            )
            result += (
                f"대당 5분 수송능력 P'      = {calculated['capacity']:.2f} 인/5분\n"
            )
            result += f"혼잡 5분 이용자수 Q       = {calculated['peak_users']:.1f} 인\n"
            result += f"수송능력 기준 산정대수 N  = {N} 대\n"
            result += f"산정대수 운전간격 / 대기  = {AIT:.2f} / {AWT:.2f} 초\n\n"

            result += "[PDF 설계 참고값]\n"
            demand_range = reference["demand_range"]
            if demand_range:
                low, high = demand_range
                demand_status = (
                    "범위 내"
                    if low <= phi * 100 <= high
                    else "범위 밖 — 입력 근거 확인"
                )
                result += (
                    f"피크 5분 집중률 예시      = {low:g}~{high:g}% "
                    f"(현재 {phi * 100:.1f}%, {demand_status})\n"
                )
            else:
                result += "피크 5분 집중률 예시      = 해당 용도 표 제시 없음\n"
            speed_range = reference["speed_range_m_min"]
            result += (
                f"층수별 권장속도 예시       = "
                f"{speed_range + ' m/min' if speed_range else '해당 용도 표 제시 없음'}\n"
            )
            if reference["rough_count"] is not None:
                rough = reference["rough_count"]
                result += (
                    f"규모별 개략 설치대수      = {rough}대 "
                    f"({reference['rough_basis']})\n"
                )
                result += (
                    f"두 산정값 비교             = 수송능력식 {N}대 / "
                    f"규모 참고표 {rough}대\n"
                )
            result += criterion_line + "\n\n"

            result += "[설치대수별 비교]\n"
            for row in calculated["comparison"]:
                result += f"{row['count']}대: 운전간격 {row['interval']:.2f}초 / 예상대기 {row['wait']:.2f}초\n"
            if current_cars is not None:
                current_interval = calculated["round_trip"] / current_cars
                capacity_status = (
                    f"수송능력 산정값보다 {N - int(current_cars)}대 부족"
                    if current_cars < N
                    else f"수송능력 산정값 충족, {int(current_cars) - N}대 여유"
                )
                result += (
                    f"현재 {int(current_cars)}대: 운전간격 {current_interval:.2f}초 / "
                    f"예상대기 {current_interval * wait_factor:.2f}초 ({capacity_status})\n"
                )

            result += "\n[계산 가정]\n"
            result += (
                f"정지층수 방식: {self.services.choice_ko(self.stop_count_mode.get())}, "
                f"서비스형식: {self.services.choice_ko(self.service_type.get())}\n"
            )
            result += f"손실시간률 10%, 대기시간 환산율 {wait_factor * 100:.1f}%\n"
            if building_use.startswith("오피스-"):
                result += f"오피스 인구산정 제외층수: {int(excluded)}층\n"
            result += (
                "※ PDF 안에서도 평균대기시간을 운전간격의 1/2와 약 60%로 각각 "
                "설명하므로 선택한 환산율을 함께 표시합니다.\n"
            )
            result += (
                "※ 규모별 대수·권장속도·서비스 판정은 법정 최소기준이 아니라 "
                "교재의 초기 설계 예시입니다.\n"
            )
            result += (
                "출처: LM1505010802_23v1 설비계획 수립, 표 1-11~1-13 및 교통량 산식\n"
            )
            result += f"계산식 버전: {FORMULA_VERSION}"

            if english:
                use_name = self.services.choice_en.get(building_use, building_use)
                population_basis_en = {
                    "공동주택": "Households × people per household",
                    "병원": "Number of hospital beds",
                    "판매시설": "Directly entered building population",
                    "사용자 설정": "Directly entered building population",
                }.get(building_use)
                if building_use.startswith("오피스-"):
                    population_basis_en = "Total office usable area ÷ area per person"
                elif building_use.startswith("호텔-"):
                    population_basis_en = "Rooms × guests per room"

                criterion_mode = self.services.choice_ko(self.criterion_mode.get())
                if criterion_mode == "판정 안 함":
                    criterion_line_en = "Service rating: Not applied"
                elif criterion_mode == "사용자 정의 기준":
                    grade_en = (
                        "Good" if AIT <= good else ("Poor" if AIT > bad else "Fair")
                    )
                    criterion_line_en = f"Custom service rating: {grade_en}"
                    source = self.entries["criterion_source"].get().strip()
                    if source:
                        criterion_line_en += f" (note: {source})"
                else:
                    if reference["interval_target"] is None:
                        criterion_line_en = (
                            "PDF interval rating: No target is listed for this use"
                        )
                    elif building_use == "공동주택":
                        grade_en = (
                            "Shorter than the example range"
                            if AIT < 60
                            else "Within the example range"
                            if AIT <= 90
                            else "Above the example range"
                        )
                        criterion_line_en = (
                            f"PDF interval rating: {grade_en} (residential: 60–90 s)"
                        )
                    elif building_use.startswith("오피스-"):
                        grade_en = (
                            "Target met"
                            if AIT <= 30
                            else "Verify handling capacity"
                            if AIT <= 40
                            else "Above the reference target"
                        )
                        criterion_line_en = f"PDF interval rating: {grade_en} (office: 30 s; up to 40 s when capacity is sufficient)"
                    else:
                        grade_en = (
                            "Target met" if AIT <= 40 else "Above the reference target"
                        )
                        criterion_line_en = (
                            f"PDF interval rating: {grade_en} (hotel: 40 s)"
                        )

                lines = [
                    "[Traffic Analysis Result — Initial Design Estimate]",
                    "",
                    f"Building use                = {use_name}",
                    f"Population basis            = {population_basis_en}",
                ]
                if building_use.startswith("오피스-"):
                    area_mode_en = (
                        "Individual floor areas"
                        if floor_areas
                        else "Same area for all included floors"
                    )
                    lines.extend(
                        [
                            f"Area method                 = {area_mode_en}",
                            f"Included floors / total area = {included} / {calculated['total_area']:.1f} m²",
                        ]
                    )
                elif building_use == "공동주택":
                    lines.append(
                        f"Households × people        = {int(households)} × {persons:g}"
                    )
                elif building_use.startswith("호텔-"):
                    lines.append(
                        f"Rooms × guests             = {int(rooms)} × {guests:g}"
                    )
                elif building_use == "병원":
                    lines.append(f"Hospital beds              = {int(beds)}")
                lines.extend(
                    [
                        f"Estimated population M      = {calculated['population']:.1f} people",
                        f"Passengers per trip r       = {calculated['riders']:.2f} people",
                        (
                            f"Expected stops fL+fE        = {calculated['local_stops']:.2f} + "
                            f"{calculated['express_stops']:g} = {calculated['expected_stops']:.2f}"
                        ),
                        (
                            f"Door / transfer / loss time = {calculated['door_time']:.2f} / "
                            f"{calculated['passenger_time']:.2f} / {calculated['loss_time']:.2f} s"
                        ),
                        f"Round-trip time RTT         = {calculated['round_trip']:.2f} s",
                        "",
                        f"5-minute capacity per car P'= {calculated['capacity']:.2f} people",
                        f"Peak 5-minute demand Q      = {calculated['peak_users']:.1f} people",
                        f"Recommended number of cars N = {N}",
                        f"Interval / expected wait    = {AIT:.2f} / {AWT:.2f} s",
                        "",
                        "[PDF Design Reference]",
                    ]
                )
                demand_range = reference["demand_range"]
                if demand_range:
                    low, high = demand_range
                    demand_status_en = (
                        "within range"
                        if low <= phi * 100 <= high
                        else "outside range — verify the assumption"
                    )
                    lines.append(
                        f"Peak-rate example          = {low:g}–{high:g}% (current {phi * 100:.1f}%, {demand_status_en})"
                    )
                else:
                    lines.append("Peak-rate example          = Not listed for this use")
                speed_range = reference["speed_range_m_min"]
                lines.append(
                    f"Speed example by floor count = {speed_range + ' m/min' if speed_range else 'Not listed for this use'}"
                )
                if reference["rough_count"] is not None:
                    rough = reference["rough_count"]
                    lines.extend(
                        [
                            f"Scale-table rough count     = {rough} cars",
                            f"Calculated / rough count    = {N} / {rough} cars",
                        ]
                    )
                lines.extend([criterion_line_en, "", "[Car-count Comparison]"])
                for row in calculated["comparison"]:
                    lines.append(
                        f"{row['count']} cars: interval {row['interval']:.2f} s / expected wait {row['wait']:.2f} s"
                    )
                if current_cars is not None:
                    current_interval = calculated["round_trip"] / current_cars
                    capacity_status_en = (
                        f"short by {N - int(current_cars)} cars"
                        if current_cars < N
                        else f"requirement met, {int(current_cars) - N} spare"
                    )
                    lines.append(
                        f"Existing {int(current_cars)} cars: interval {current_interval:.2f} s / "
                        f"expected wait {current_interval * wait_factor:.2f} s ({capacity_status_en})"
                    )
                lines.extend(
                    [
                        "",
                        "[Assumptions]",
                        (
                            f"Stop method: {self.services.choice_en.get(self.services.choice_ko(self.stop_count_mode.get()), self.stop_count_mode.get())}; "
                            f"service type: {self.services.choice_en.get(self.services.choice_ko(self.service_type.get()), self.service_type.get())}"
                        ),
                        f"Lost-time rate 10%; waiting-time factor {wait_factor * 100:.1f}%",
                    ]
                )
                if building_use.startswith("오피스-"):
                    lines.append(f"Office population excludes {int(excluded)} floors")
                lines.extend(
                    [
                        "The reference describes average waiting time as both one-half and about 60% of the interval; the selected factor is shown above.",
                        "Counts, speeds, and service ratings are initial design references, not statutory minimums.",
                        "Source: LM1505010802_23v1 Equipment Planning, Tables 1-11–1-13 and traffic formulas",
                        f"Formula version: {FORMULA_VERSION}",
                    ]
                )
                result = "\n".join(lines)

            result += "\n[설계평가] 운전간격·수송능력은 선택한 교재/사용자 기준에 따른 초기 검토입니다.\n"
            result += "[법령검토] 건축물 용도·규모·층수 등 별도 입력과 건축법령 대조가 필요하여 현재 판정 불가. 비상용·장애인용 요구도 별도 확인하세요.\n"
            result += (
                "KS B ISO 8100-32는 계획·선정용 표준이며 법정 검사 판정값이 아닙니다."
            )
            self._show(result)

        except ZeroDivisionError:
            self._show(
                "Error: A value causes division by zero. Check the inputs."
                if english
                else "오류: 0으로 나누는 값이 있습니다. 입력값을 확인하세요.",
                error=True,
            )
        except ValueError as e:
            self._show(
                "Input error: Check the required values, ranges, and selected units."
                if english
                else f"입력 오류: {e}",
                error=True,
            )
        except Exception as e:
            self.services.show_unexpected_error(self, "교통량 분석", e)
