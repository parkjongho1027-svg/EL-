# -*- coding: utf-8 -*-
"""
승강기 주요 설계값 계산·검토 및 S-Curve 운행 시뮬레이션 프로그램

이 프로그램은 다음 네 가지 계산을 한곳에서 수행합니다.
1. 전동기 용량: 적재하중과 속도 등을 이용해 필요한 모터 용량을 계산
2. 트랙션비: 카와 균형추 양쪽의 트랙션비를 구하고 큰 값을 최종값으로 선택
3. 브레이크 제동: 알고 있는 두 값으로 속도·시간·거리·감속도를 계산
4. 교통량 분석: 건물과 승강기 조건으로 필요한 설치대수와 대기시간을 계산

계산식은 calculators.py, KC 기준의 개별 조항 검토는 elevator_review_engine.py에 있습니다.
초기 설계 계산의 출처로 사용자가 제공한 아래 자료를 참조합니다.
  1) "승강기_적정수치_탐색_프로그램_계산공식_정리.pdf"
     -> 전동기 용량, 트랙션비, 브레이크 제동 계산식
  2) 승강기기사·산업기사 교재 캡처 이미지 13장
     -> 교통량 분석(RTT, 5분간 수송능력, 설치대수, 평균대기시간 등) 계산식

필수 입력값이 비어 있거나 잘못된 경우에는 계산을 진행하지 않고
어느 입력값을 확인해야 하는지 오류 메시지로 알려줍니다.
"""

import ctypes
import csv
import json
import math
import os
import shutil
import sys
import tempfile
import tkinter as tk
import tkinter.font as tkfont
import traceback
from concurrent.futures import ThreadPoolExecutor, CancelledError
from queue import Empty, SimpleQueue
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk
from src.config.assets import FORMULA_IMAGE_DATA, FORMULA_TEXT_EN
from src.config.constants import APP_BUILD, FORMULA_VERSION, BUTTON_BG, BUTTON_ACTIVE_BG, BUTTON_TEXT
from src.ui.theme_manager import (THEMES, get_theme, apply_theme, style_combobox_popdown,
                           bind_combobox_popdown_theme, configure_ttk_theme, apply_font_scale)
from src.ui.ui_components import (SkyButton, WindowManager, center_child_window,
                           app_ask_string, app_ask_project_info, messagebox, set_dialog_root,
                           attach_numeric_validation)
from src.persistence.storage import (PersistentStore, get_data_file_path, normalize_record,
                     CALCULATOR_KEYS, MAX_HISTORY_PER_CALCULATOR)
from src.common.utils import (clean_number_text, parse_number, ensure_positive,
                   calculate_safely, require_calculation)
from src.core.calculators import (
    calculate_motor_value, calculate_traction_values, calculate_brake_values,
    calculate_traffic_values, traffic_pdf_reference, traffic_visible_input_fields,
    run_calculation_self_tests,
)
from src.ui.simulation_plot import draw_scurve_plot, draw_energy_comparison
from src.core.energy_model import compare_trips, read_measurement
from src.ui.motor_duty_dialog import open_motor_duty_dialog
from src.ui.engineering_charts import show_tension, show_capacity
from src.ui.keyboard_navigation import KeyboardNavigationMixin, focus_input_for_replacement
from src.ui.project_snapshot import merge_project_states, _state_number as project_state_number
from src.ui.brake_panel import BrakePanel, BrakePanelServices, build_brake_tab as build_brake_panel
from src.ui.traction_panel import IntegratedTractionPanel, TractionPanelServices
from src.ui.criteria_panel import CriteriaPanel, CriteriaPanelServices
from src.ui.scurve_panel import SCurvePanel, SCurvePanelServices
from src.ui.motor_panel import SolverPanel, MotorPanelServices
from src.ui.traffic_panel import TrafficPanel, TrafficPanelServices
from src.ui.graph_workspace import refresh_live_graphs
from src.services.background_jobs import calculate_snapshot


INITIAL_RESULT_MESSAGE = (
    "문제의 값을 입력한 뒤 ‘계산’을 누르세요.\n"
    "최근 값은 ‘이전 입력값’, 누적된 값은 ‘입력 기록’에서 불러올 수 있습니다."
)
INITIAL_RESULT_MESSAGE_EN = (
    "Enter the problem values, then select Calculate.\n"
    "Use Previous Inputs for the latest values or Input History for saved records."
)

# 왼쪽 네 계산은 2×2, 오른쪽은 긴 KC 검토·시뮬레이션 결과를 세로로 둔다.
INTEGRATED_RESULT_CELLS = ((0, 0), (0, 1), (1, 0), (1, 1), (0, 2), (1, 2))


def initial_result_text(widget):
    return INITIAL_RESULT_MESSAGE_EN if widget_language(widget) == "en" else INITIAL_RESULT_MESSAGE


# 화면 오른쪽 아래에 표시되는 빌드 번호입니다.
# 같은 파일명으로 여러 번 내려받았을 때 최신 수정본인지 쉽게 확인할 수 있습니다.

# 첨부 계산식 이미지는 assets.py에 포함됩니다. 실행 시 모든 모듈을 같은 폴더에 둡니다.























# 기본 Tk 대화창은 Windows 표시 언어를 따라가므로 버튼이 한국어로 남을 수 있습니다.
# 프로그램 내부에서 사용하는 모든 안내창을 위의 다국어 대화창으로 통일합니다.






















def get_log_file_path():
    """예상하지 못한 프로그램 오류를 기록할 파일 위치를 반환합니다."""
    return get_data_file_path().with_name("error.log")


def log_unexpected_error(context, error):
    """사용자 입력 오류와 구분되는 프로그램 오류를 파일에 남깁니다."""
    try:
        path = get_log_file_path()
        with path.open("a", encoding="utf-8") as log:
            log.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] {context}\n")
            log.write("".join(traceback.format_exception(type(error), error, error.__traceback__)))
    except OSError:
        return None
    return path


def show_unexpected_error(panel, context, error):
    """내부 오류는 상세 내용을 화면에 노출하지 않고 로그 위치를 안내합니다."""
    log_path = log_unexpected_error(context, error)
    english = widget_language(panel) == "en"
    message = ("An internal program error occurred. Your inputs were preserved."
               if english else
               "프로그램 내부 오류가 발생했습니다. 입력값은 그대로 유지됩니다.")
    if log_path:
        message += (f"\nError log: {log_path}" if english else f"\n오류 기록: {log_path}")
    panel._show(message, error=True)








# ===================================================================
# 계산 핵심부: 화면 코드와 분리된 순수 계산 함수
# ===================================================================














def push_undo_state(panel):
    """패널의 현재 상태를 최대 20단계까지 실행 취소 목록에 보관합니다."""
    state = panel.capture_state()
    stack = getattr(panel, "undo_stack", None)
    if stack is None:
        panel.undo_stack = []
        stack = panel.undo_stack
    if not stack or stack[-1] != state:
        stack.append(state)
        del stack[:-20]


def undo_panel(panel):
    """현재 탭에서 가장 최근에 변경되기 전 상태를 복원합니다."""
    stack = getattr(panel, "undo_stack", [])
    if not stack:
        panel._show("There is nothing to undo." if widget_language(panel) == "en"
                    else "실행 취소할 작업이 없습니다.")
        return
    panel.apply_state(stack.pop(), remember_undo=False)
    panel._show("The last input change was undone." if widget_language(panel) == "en"
                else "마지막 입력 변경을 실행 취소했습니다.")


def _set_formula_preview_language(label, language):
    """한국어에서는 첨부 원본을, 영어에서는 같은 식의 영문판을 표시합니다."""
    key = getattr(label, "_formula_key", "")
    if not key:
        return
    if language == "en":
        label.configure(
            image="", text=FORMULA_TEXT_EN[key], justify="left", anchor="w",
            font=("맑은 고딕", 9, "bold"), padx=10, pady=7,
        )
    else:
        label.configure(image=label._formula_photo, text="", padx=2, pady=2)


def update_formula_previews(widget, language):
    if hasattr(widget, "_formula_key"):
        _set_formula_preview_language(widget, language)
    for child in widget.winfo_children():
        update_formula_previews(child, language)


def create_calculation_layout(parent, note, result_title="계산 결과", formula_key=None):
    """네 계산 탭에서 공통으로 쓰는 안내문과 좌우 박스를 만듭니다.

    안내문은 입력 박스 밖의 위쪽에 먼저 표시합니다. 그 아래에는 입력값과
    계산 결과 박스를 같은 폭으로 두어 탭을 바꿔도 위치가 움직이지 않게 합니다.
    """
    # 기존 안내문은 그대로 두고 F1 도움말은 같은 줄 오른쪽에 고정합니다.
    note_row = tk.Frame(parent, bg="white")
    note_row.pack(fill="x", padx=16, pady=(14, 8))
    note_label = tk.Label(
        note_row, text=note, font=("맑은 고딕", 10), bg="white",
        fg="#555555", justify="left", anchor="w", wraplength=600
    )
    note_label._theme_role = "muted"
    note_label.pack(side="left", anchor="w", fill="x", expand=True)
    right_guide = tk.Frame(note_row)
    right_guide.pack(side="right", anchor="ne", padx=(10, 0))
    def fit_note(event):
        # 화면 폭이 커지면 안내문의 불필요한 줄바꿈을 줄여 입력 영역을 늘린다.
        available=max(380,event.width-right_guide.winfo_reqwidth()-24)
        if int(note_label.cget("wraplength"))!=available:
            note_label.configure(wraplength=available)
    note_row.bind("<Configure>",fit_note,add="+")
    help_label = tk.Label(
        right_guide, text="F1 단축키 도움말", font=("맑은 고딕", 9, "bold"),
        cursor="hand2", anchor="e", padx=4
    )
    help_label._theme_role = "muted"
    help_label.pack(anchor="e", pady=(0, 3))
    help_label.bind("<Button-1>", lambda _event: parent.winfo_toplevel().event_generate("<F1>"))
    # 수식 이미지는 작은 탭 공간에서 자르지 않고 설정의 전용 가이드에서 표시합니다.

    body = tk.Frame(parent, bg="white")
    body.pack(fill="both", expand=True, padx=16, pady=(0, 12))
    body.grid_rowconfigure(0, weight=1)
    body.grid_columnconfigure(0, weight=1, uniform="calculation_box")
    body.grid_columnconfigure(1, weight=1, uniform="calculation_box")

    left = tk.LabelFrame(
        body, text=" 입력값 ", font=("맑은 고딕", 11, "bold"),
        bg="white", padx=10, pady=8
    )
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
    right = tk.LabelFrame(
        body, text=f" {result_title} ", font=("맑은 고딕", 11, "bold"),
        bg="white", padx=12, pady=10
    )
    right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
    return left, right



def show_input_status(panel, message):
    """프로젝트/기록 불러오기 안내를 결과창이 아닌 입력값 박스 하단에 표시합니다."""
    parent = getattr(panel, "input_area", None)
    if parent is None:
        return
    label = getattr(panel, "_input_status_label", None)
    if label is None or not label.winfo_exists():
        label = tk.Label(
            parent, text="", font=("맑은 고딕", 9),
            anchor="w", justify="left", padx=10, pady=5, wraplength=430
        )
        label._theme_role = "muted"
        label.pack(side="bottom", fill="x", padx=2, pady=(4, 0))
        panel._input_status_label = label
    label.configure(text=message)


def create_result_display(parent, *, copy_width=10):
    """트랙션비 화면을 기준으로 통일한 계산 결과 표시창을 만듭니다."""
    toolbar = tk.Frame(parent, bg="white")
    toolbar.pack(side="bottom", fill="x", pady=(8, 0))

    result_area = tk.Frame(parent, bg="white")
    result_area.pack(fill="both", expand=True)

    result = tk.Text(
        result_area, font=("맑은 고딕", 10), bg="#f7faff", fg="#1f1f1f",
        relief="flat", padx=10, pady=10, wrap="word",
        selectbackground=THEMES["light"]["selection_bg"],
        selectforeground=THEMES["light"]["selection_fg"]
    )
    result_scrollbar = ttk.Scrollbar(
        result_area, orient="vertical", command=result.yview
    )
    result.configure(yscrollcommand=result_scrollbar.set)
    result_scrollbar.pack(side="right", fill="y")
    result.pack(side="left", fill="both", expand=True)
    # 결과 위젯에서 필요할 때 스크롤바에 접근할 수 있도록 함께 보관합니다.
    result._vertical_scrollbar = result_scrollbar

    def copy_result():
        text = result.get("1.0", "end-1c").strip()
        if not text:
            return
        result.clipboard_clear()
        result.clipboard_append(text)
        english = widget_language(result) == "en"
        copy_button.config(text="Copied" if english else "복사 완료")
        result.after(1200, lambda: copy_button.config(
            text="Copy Result" if widget_language(result) == "en" else "결과 복사"
        ))

    copy_button = SkyButton(
        toolbar, text="결과 복사", command=copy_result,
        font=("맑은 고딕", 10), width=copy_width
    )
    copy_button.pack(side="right")
    return result


def set_result_display(widget, text, error=False):
    """결과 표시창의 글을 바꾸고 사용자가 내용을 편집하지 못하게 잠급니다."""
    _mode, colors = get_theme(widget)
    widget._result_error = error
    widget.config(state="normal", bg=colors["result"],
                  fg="#ff6b6b" if error and _mode == "dark" else
                     ("red" if error else colors["text"]))
    widget.delete("1.0", tk.END)
    widget.insert("1.0", text)
    widget.config(state="disabled")


def create_action_buttons(parent, calculate_command, auxiliary_specs, padx=10, pady=10,
                          button_width=11, button_pady=4, button_gap=6,
                          side="top"):
    """각 계산 화면의 실행·보조 버튼을 같은 모양과 위치로 만듭니다.

    계산 버튼은 왼쪽, 입력값 삭제·이전 입력값·입력 기록 같은 보조 버튼은
    오른쪽에 정렬합니다. 색상은 현재 라이트·다크 모드의 공통 스타일을 따릅니다.
    auxiliary_specs는 (구분 이름, 버튼 글자, 실행 함수, 초기 상태) 목록입니다.
    """
    row = tk.Frame(parent, bg="white")
    row.pack(side=side, fill="x", padx=padx, pady=pady)

    calculate_button = SkyButton(
        row, text="계산", command=calculate_command,
        font=("맑은 고딕", 10, "bold"), width=button_width,
        pady=button_pady
    )
    calculate_button.pack(side="left")

    auxiliary_area = tk.Frame(row, bg="white")
    auxiliary_area.pack(side="right")
    buttons = {"calculate": calculate_button}
    for key, text, command, state in auxiliary_specs:
        button = SkyButton(
            auxiliary_area, text=text, command=command,
            font=("맑은 고딕", 10), width=button_width,
            pady=button_pady, state=state
        )
        button.pack(side="left", padx=(button_gap, 0))
        buttons[key] = button

    return buttons


def open_history_window(parent, title, history, field_specs, load_record,
                        delete_record, clear_records, rename_record=None):
    """모든 계산 화면에서 공통으로 사용하는 입력 기록 창을 엽니다.

    입력 화면과 같은 순서로 항목명과 값을 세로로 나열한 기록 카드를 만듭니다.
    사용자가 카드의 어느 부분이든 클릭하면 해당 기록을 입력칸에 적용합니다.
    """
    main_window = parent.winfo_toplevel()
    english = getattr(main_window, "_language", "ko") == "en"

    def history_value(key, value):
        """저장 데이터의 내부 한국어 선택값이 영어 화면에 노출되지 않게 합니다."""
        text = str(value or "")
        if not english:
            return text
        if text in CHOICE_EN:
            return CHOICE_EN[text]
        if text in ENGLISH_UI:
            return ENGLISH_UI[text]
        if key == "__result_summary__" and any("가" <= char <= "힣" for char in text):
            return "Saved result was created in Korean mode. Recalculate to view it in English."
        return text
    if not history:
        messagebox.showinfo(
            "Input History" if english else "입력 기록",
            "No input history has been saved yet." if english else "아직 저장된 입력 기록이 없습니다.",
        )
        return

    history_titles_en = {
        "전동기 용량 입력 기록": "Motor Capacity Input History",
        "트랙션비 입력 기록": "Traction Ratio Input History",
        "브레이크 제동 입력 기록": "Brake Input History",
        "교통량 분석 입력 기록": "Traffic Analysis Input History",
        "기준 검토 입력 기록": "KC Clause Review Input History",
    }
    window = tk.Toplevel(parent)
    window.title(history_titles_en.get(title, title) if english else title)
    history_width = min(1000, max(720, window.winfo_screenwidth() - 40))
    history_height = min(580, max(480, window.winfo_screenheight() - 100))
    WindowManager.center(window, parent, history_width, history_height)
    window.minsize(700, 460)
    window.resizable(True, True)
    window.transient(parent.winfo_toplevel())
    window._language = "en" if english else "ko"
    window._ui_theme = getattr(main_window, "_ui_theme", "light")

    guide_row = tk.Frame(window)
    guide_row.pack(fill="x", padx=12, pady=(12, 6))
    tk.Label(guide_row,
             text=("Click a card to load it. Only checked records are compared or deleted; newest records are on the left."
                   if english else
                   "카드 본문을 누르면 입력칸에 적용됩니다. 체크한 기록만 비교·삭제할 수 있으며 최신 기록은 가장 왼쪽입니다."),
             font=("맑은 고딕", 10), anchor="w").pack(side="left", fill="x", expand=True)
    clear_all_button = SkyButton(
        guide_row, text="전체 기록 삭제", font=("맑은 고딕", 9), width=13
    )
    clear_all_button.pack(side="right")

    tools_row = tk.Frame(window)
    tools_row.pack(fill="x", padx=12, pady=(0, 5))
    tk.Label(tools_row, text="검색", font=("맑은 고딕", 9)).pack(side="left")
    search_var = tk.StringVar()
    search_entry = tk.Entry(tools_row, textvariable=search_var, width=28,
                            font=("맑은 고딕", 9))
    search_entry.pack(side="left", padx=(6, 10))

    def export_csv():
        path = filedialog.asksaveasfilename(
            parent=window, title="Export Input History CSV" if english else "입력 기록 CSV 저장",
            defaultextension=".csv", filetypes=[("CSV File" if english else "CSV 파일", "*.csv")]
        )
        if not path:
            return
        keys = [key for key, _heading, _width in field_specs]
        headings = [ENGLISH_UI.get(heading, heading) if english else heading
                    for _key, heading, _width in field_specs]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow((["Record Name", "Saved At", *headings, "Result",
                                  "Program Build", "Formula Version"] if english else
                                 ["기록 이름", "저장 시각", *headings, "결과",
                                  "프로그램 빌드", "계산식 버전"]))
                for record in reversed(history):
                    writer.writerow([
                        record.get("__name__", ""), record.get("__saved_at__", ""),
                        *[history_value(key, record.get(key, "")) for key in keys],
                        history_value("__result_summary__", record.get("__result_summary__", "")),
                        record.get("__app_build__", ""),
                        record.get("__formula_version__", ""),
                    ])
            messagebox.showinfo(
                "Input History" if english else "입력 기록",
                "Saved as a CSV file." if english else "CSV 파일로 저장했습니다.", parent=window)
        except OSError as error:
            messagebox.showerror("History Save Error" if english else "입력 기록 저장 오류", str(error), parent=window)

    SkyButton(tools_row, text="CSV 저장", command=export_csv,
              font=("맑은 고딕", 9), width=10).pack(side="right")

    selected_indices = set()

    def selected_in_card_order():
        """화면의 왼쪽(최신)부터 체크된 원본 기록 번호를 반환합니다."""
        return sorted(selected_indices, reverse=True)

    def compare_selected():
        indexes = selected_in_card_order()
        if len(indexes) < 2:
            messagebox.showinfo(
                "Compare History" if english else "기록 비교",
                "Select at least two records to compare." if english else "비교할 기록을 2개 이상 체크해주세요.",
                parent=window,
            )
            return

        compare_window = tk.Toplevel(window)
        compare_window.title(
            f"Compare Selected ({len(indexes)})" if english else f"선택 기록 비교 ({len(indexes)}개)"
        )
        compare_width = min(980, max(700, compare_window.winfo_screenwidth() - 50))
        compare_height = min(560, max(420, compare_window.winfo_screenheight() - 110))
        WindowManager.center(compare_window, window, compare_width, compare_height)
        compare_window.minsize(700, 420)
        compare_window.transient(window)
        compare_window._ui_theme = getattr(window, "_ui_theme", "light")

        host = tk.Frame(compare_window, bd=1, relief="solid")
        host.pack(fill="both", expand=True, padx=12, pady=12)
        table_canvas = tk.Canvas(host, highlightthickness=0)
        ybar = ttk.Scrollbar(host, orient="vertical", command=table_canvas.yview)
        xbar = ttk.Scrollbar(host, orient="horizontal", command=table_canvas.xview)
        table_canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        ybar.pack(side="right", fill="y")
        xbar.pack(side="bottom", fill="x")
        table_canvas.pack(side="left", fill="both", expand=True)

        table = tk.Frame(table_canvas)
        table_window = table_canvas.create_window((0, 0), window=table, anchor="nw")
        table.bind("<Configure>", lambda _e: table_canvas.configure(
            scrollregion=table_canvas.bbox("all")))

        header_values = ["Item" if english else "항목"]
        for record_index in indexes:
            record = history[record_index]
            header_values.append(record.get("__name__") or
                                 (f"Input Record {record_index + 1}" if english else f"입력 기록 {record_index + 1}"))
        rows = [("Saved At" if english else "저장 시각", "__saved_at__"),
                *[(ENGLISH_UI.get(heading, heading) if english else heading, key)
                  for key, heading, _w in field_specs],
                ("Result" if english else "계산 결과", "__result_summary__")]

        line_color = "#386b91" if compare_window._ui_theme == "dark" else "#d6e0e8"

        def add_cell(row, column, value, header=False, field=False):
            cell = tk.Label(
                table, text=value, anchor="w", justify="left",
                font=("맑은 고딕", 9, "bold" if header or field else "normal"),
                padx=9, pady=7, wraplength=260,
                highlightthickness=1, highlightbackground=line_color,
            )
            if header:
                cell._theme_role = "header_1" if column % 2 else "header_2"
            elif field:
                cell._theme_role = "subtle"
            cell.grid(row=row, column=column, sticky="nsew")
            table.grid_columnconfigure(column, minsize=165 if column == 0 else 210)

        for column, value in enumerate(header_values):
            add_cell(0, column, value, header=True)
        for row_number, (heading, key) in enumerate(rows, start=1):
            add_cell(row_number, 0, heading, field=True)
            for column, record_index in enumerate(indexes, start=1):
                value = history_value(key, history[record_index].get(key, "")) or ("(blank)" if english else "(빈칸)")
                add_cell(row_number, column, value)

        def scroll_compare(event):
            table_canvas.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        def scroll_compare_horizontal(event):
            table_canvas.xview_scroll(int(-event.delta / 120), "units")
            return "break"

        compare_window.bind("<MouseWheel>", scroll_compare)
        compare_window.bind("<Shift-MouseWheel>", scroll_compare_horizontal)
        SkyButton(compare_window, text="Close" if english else "닫기", command=compare_window.destroy,
                  width=10).pack(pady=(8, 12))
        apply_theme(compare_window, compare_window._ui_theme)
        apply_font_scale(compare_window, getattr(main_window, "_font_size", 10))
        apply_language(compare_window, getattr(main_window, "_language", "ko"))

    def remove_selected():
        indexes = selected_in_card_order()
        if not indexes:
            messagebox.showinfo(
                "Delete History" if english else "입력 기록 삭제",
                "Select at least one record to delete." if english else "삭제할 기록을 하나 이상 체크해주세요.",
                parent=window)
            return
        if not messagebox.askyesno(
                "Delete Selected" if english else "선택 기록 삭제",
                (f"Delete {len(indexes)} selected input records?" if english else
                 f"체크한 입력 기록 {len(indexes)}개를 삭제할까요?"), parent=window):
            return
        # 큰 번호부터 지우면 앞쪽 기록의 원본 번호가 변하지 않습니다.
        for record_index in indexes:
            history[:] = delete_record(record_index)
        selected_indices.clear()
        render_cards()

    SkyButton(tools_row, text="선택 기록 삭제", command=remove_selected,
              font=("맑은 고딕", 9), width=12).pack(side="right")
    SkyButton(tools_row, text="선택 기록 비교", command=compare_selected,
              font=("맑은 고딕", 9), width=12).pack(side="right", padx=(0, 6))

    scroll_frame = tk.Frame(window)
    scroll_frame.pack(fill="both", expand=True, padx=12, pady=4)
    canvas = tk.Canvas(scroll_frame, bg="#f2f4f7", highlightthickness=0)
    vertical_scrollbar = ttk.Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
    scrollbar = ttk.Scrollbar(scroll_frame, orient="horizontal", command=canvas.xview)
    canvas.configure(xscrollcommand=scrollbar.set, yscrollcommand=vertical_scrollbar.set)
    vertical_scrollbar.pack(side="right", fill="y")
    scrollbar.pack(side="bottom", fill="x")
    canvas.pack(side="left", fill="both", expand=True)

    cards = tk.Frame(canvas, bg="#f2f4f7")
    cards._theme_role = "canvas"
    canvas.create_window((0, 0), window=cards, anchor="nw")
    cards.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))

    def apply_record(record_index):
        load_record(history[record_index], record_index + 1)
        window.destroy()

    def remove_one(record_index):
        if not messagebox.askyesno("Delete History" if english else "입력 기록 삭제",
                                   "Delete this input record?" if english else "선택한 입력 기록을 삭제할까요?",
                                   parent=window):
            return
        history[:] = delete_record(record_index)
        selected_indices.discard(record_index)
        # 삭제된 카드보다 뒤에 있던 원본 번호는 한 칸씩 앞으로 이동합니다.
        shifted = {index - 1 if index > record_index else index for index in selected_indices}
        selected_indices.clear()
        selected_indices.update(shifted)
        render_cards()

    def remove_all():
        if not messagebox.askyesno("Delete All History" if english else "전체 기록 삭제",
                                   "Delete all saved input records?" if english else "저장된 입력 기록을 모두 삭제할까요?",
                                   parent=window):
            return
        clear_records()
        history.clear()
        selected_indices.clear()
        render_cards()

    def rename_one(record_index):
        if rename_record is None:
            return
        current = history[record_index].get("__name__", "")
        name = app_ask_string(
            "Record Name" if english else "기록 이름",
            "Enter a recognizable name for this record." if english else "이 기록을 알아보기 쉬운 이름으로 지정하세요.",
            initialvalue=current, parent=window
        )
        if name is None:
            return
        history[:] = rename_record(record_index, name)
        render_cards()

    clear_all_button.config(command=remove_all)

    def render_cards():
        """삭제 후에도 창을 닫지 않고 남은 기록 카드를 즉시 다시 그립니다."""
        for child in cards.winfo_children():
            child.destroy()
        clear_all_button.config(state="normal" if history else "disabled")
        if not history:
            tk.Label(cards, text="No saved input history." if english else "저장된 입력 기록이 없습니다.",
                     font=("맑은 고딕", 11)).pack(padx=30, pady=40)
            window._ui_theme = getattr(parent.winfo_toplevel(), "_ui_theme", "light")
            apply_theme(window, window._ui_theme)
            window.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            return

        query = search_var.get().strip().lower()
        indexes = []
        for original_index in range(len(history) - 1, -1, -1):
            searchable = " ".join(str(value) for value in history[original_index].values()).lower()
            if not query or query in searchable:
                indexes.append(original_index)
        if not indexes:
            tk.Label(cards, text="No records match the search." if english else "검색 조건과 일치하는 기록이 없습니다.",
                     font=("맑은 고딕", 11)).pack(padx=30, pady=40)
        # 카드 내부 항목은 세로, 카드 자체는 최신 기록부터 가로로 배치합니다.
        for original_index in indexes:
            record = history[original_index]
            # 카드마다 별도의 외부 프레임을 만들고, 그 안에 실제 카드를
            # 2픽셀 띄워 넣습니다. 외부 프레임의 파란 배경이 사방의 선이 됩니다.
            card_border = tk.Frame(cards, bd=0, relief="flat", cursor="hand2")
            card_border._theme_role = "history_card_border"
            card_border.pack(side="left", anchor="n", fill="y", padx=7, pady=8)

            card = tk.Frame(card_border, bg="white", bd=0, relief="flat", cursor="hand2")
            card._theme_role = "surface"
            card.pack(fill="both", expand=True, padx=2, pady=2)
            widgets = [card_border, card]
            header_row = tk.Frame(card, bg="white")
            header_row.pack(fill="x")
            checked = tk.BooleanVar(value=original_index in selected_indices)

            def toggle_record(i=original_index, variable=checked):
                if variable.get():
                    selected_indices.add(i)
                else:
                    selected_indices.discard(i)

            selector = tk.Checkbutton(
                header_row, variable=checked, command=toggle_record,
                cursor="hand2", padx=5, pady=3, takefocus=True
            )
            selector.pack(side="left")
            header = tk.Label(
                header_row, text=record.get("__name__") or
                (f"Input Record {original_index + 1}" if english else f"입력 기록 {original_index + 1}"),
                font=("맑은 고딕", 10, "bold"), anchor="w", padx=8, pady=5,
                cursor="hand2"
            )
            header._theme_role = "header_1" if original_index % 2 == 0 else "header_2"
            header.pack(side="left", fill="x", expand=True)
            widgets.extend((header_row, header))

            saved_at = record.get("__saved_at__", "No saved time" if english else "저장 시각 없음")
            time_label = tk.Label(card, text=saved_at, anchor="w", padx=9,
                                  font=("맑은 고딕", 8), cursor="hand2")
            time_label._theme_role = "muted"
            time_label.pack(fill="x", pady=(3, 2))
            widgets.append(time_label)

            version_label = tk.Label(
                card,
                text=((f"Formula {record.get('__formula_version__', 'earlier version')} · "
                       f"Build {record.get('__app_build__', 'earlier version')}") if english else
                      (f"공식 {record.get('__formula_version__', '이전 버전')} · "
                       f"빌드 {record.get('__app_build__', '이전 버전')}")),
                anchor="w", padx=9, font=("맑은 고딕", 8), cursor="hand2"
            )
            version_label._theme_role = "muted"
            version_label.pack(fill="x", pady=(0, 3))
            widgets.append(version_label)

            for key, heading, _width in field_specs:
                row = tk.Frame(card, bg="white", cursor="hand2")
                row.pack(fill="x", padx=10, pady=2)
                label = tk.Label(row, text=ENGLISH_UI.get(heading, heading) if english else heading,
                                 width=17, anchor="w", bg="white",
                                 font=("맑은 고딕", 9), cursor="hand2")
                value = tk.Label(row, text=history_value(key, record.get(key, "")), width=14, anchor="w",
                                 bg="white", font=("맑은 고딕", 9, "bold"),
                                 cursor="hand2")
                label.pack(side="left")
                value.pack(side="left", fill="x", expand=True)
                widgets.extend((row, label, value))

            summary = history_value("__result_summary__", record.get("__result_summary__", ""))
            if summary:
                summary_label = tk.Label(
                    card, text=(f"Result: {summary}" if english else f"결과: {summary}"), anchor="w", justify="left",
                    wraplength=250, padx=9, pady=5, font=("맑은 고딕", 8, "bold"),
                    cursor="hand2"
                )
                widgets.append(summary_label)
                summary_label.pack(fill="x")

            card_buttons = tk.Frame(card)
            card_buttons.pack(fill="x", padx=9, pady=(5, 9))
            if rename_record is not None:
                SkyButton(card_buttons, text="Name Record" if english else "이름 지정", font=("맑은 고딕", 9),
                          command=lambda i=original_index: rename_one(i)).pack(
                              side="left", fill="x", expand=True, padx=(0, 3))
            SkyButton(card_buttons, text="Delete Record" if english else "기록 삭제", font=("맑은 고딕", 9),
                      command=lambda i=original_index: remove_one(i)).pack(
                          side="left", fill="x", expand=True, padx=(3, 0))

            for widget in widgets:
                widget.bind("<Button-1>", lambda _event, i=original_index: apply_record(i))

        window._ui_theme = getattr(parent.winfo_toplevel(), "_ui_theme", "light")
        apply_theme(window, window._ui_theme)
        window.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.xview_moveto(0.0)

    # 기록이 창 너비를 넘으면 아래 가로 바 또는 마우스 휠로 좌우 이동합니다.
    window.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"))
    window.bind("<Shift-MouseWheel>", lambda event: canvas.xview_scroll(int(-event.delta / 120), "units"))
    search_var.trace_add("write", lambda *_args: render_cards())
    render_cards()
    SkyButton(window, text="Close" if english else "닫기", command=window.destroy,
              font=("맑은 고딕", 10), padx=12).pack(pady=(4, 12))

    # 새로 연 기록 창도 메인 창에서 사용 중인 테마를 그대로 이어받습니다.
    main_window = parent.winfo_toplevel()
    window._ui_theme = getattr(main_window, "_ui_theme", "light")
    apply_theme(window, window._ui_theme)
    apply_font_scale(window, getattr(main_window, "_font_size", 10))
    apply_language(window, getattr(main_window, "_language", "ko"))


# ===================================================================
# 공통 위젯: "무엇을 구할지 선택 -> 나머지 값 입력 -> 계산" 패턴 패널
#   전동기 용량 / 균형추 중량 / 로프 총중량 / 전반부·후반부 트랙션비에서
#   공통으로 사용 (변수 N개 중 1개를 구하고, 나머지 N-1개를 입력하는 구조)
# ===================================================================


# ===================================================================
# 탭 1. 전동기 용량 계산
#   P = [Q x V x (1-OB)] / (6120 x η)
# ===================================================================
def build_motor_tab(notebook, store):
    """전동기 용량 계산 탭을 만듭니다.

    V 입력칸 하나에서 m/s와 m/min을 선택하며, 단위를 바꾸면 값도 변환합니다.
    """
    vars_spec = [
        {"key": "P", "label": "전동기 용량 P", "unit": "kW"},
        {"key": "Q", "label": "적재하중 Q", "unit": "kg"},
        {"key": "V", "label": "정격속도 V",
         "unit_factors": {"m/min": 1.0, "m/s": 60.0}, "default_unit": "m/s"},
        {"key": "OB", "label": "오버밸런스율 OB", "percent": True},
        {"key": "eff", "label": "전체효율 η", "percent": True},
    ]

    formulas = {
        key: (lambda values, target=key: calculate_motor_value(target, values))
        for key in ("P", "Q", "V", "eff", "OB")
    }

    def validate_motor_values(values, _target_key):
        for key, label in (("P", "전동기 용량"), ("Q", "적재하중"),
                           ("V", "정격속도")):
            if key in values:
                ensure_positive(values[key], label)
        if "OB" in values and not 0 < values["OB"] < 1:
            raise ValueError("'오버밸런스율'은 0보다 크고 100보다 작은 % 값이어야 합니다.")
        if "eff" in values and not 0 < values["eff"] <= 1:
            raise ValueError("'전체효율'은 0보다 크고 100 이하인 % 값이어야 합니다.")

    def validate_motor_result(result, target_key):
        labels = {"P": "전동기 용량", "Q": "적재하중", "V": "정격속도",
                  "OB": "오버밸런스율", "eff": "전체효율"}
        if target_key in ("P", "Q", "V") and result <= 0:
            raise ValueError(f"계산된 '{labels[target_key]}'이 0보다 크지 않습니다.")
        if target_key == "OB" and not 0 < result < 1:
            raise ValueError("계산된 오버밸런스율이 0% 초과 100% 미만 범위를 벗어납니다.")
        if target_key == "eff" and not 0 < result <= 1:
            raise ValueError("계산된 전체효율이 0% 초과 100% 이하 범위를 벗어납니다.")

    note = ("기본식: P = [Q × V × (1-OB)] / (6120 × η)\n"
            "속도 단위는 입력칸 옆에서 m/s 또는 m/min을 선택합니다. OB와 η는 %입니다.\n"
            "※ 숫자칸에는 50*1.1*6처럼 간단한 계산식을 직접 입력할 수 있습니다.")
    panel = SolverPanel(
        notebook, vars_spec, formulas, note, store, "motor",
        validate_motor_values, validate_motor_result, formula_key="motor",
        services=MotorPanelServices(
            create_calculation_layout=create_calculation_layout,
            create_action_buttons=create_action_buttons,
            create_result_display=create_result_display,
            initial_result_text=initial_result_text,
            set_result_display=set_result_display,
            push_undo_state=push_undo_state,
            widget_language=widget_language,
            open_history_window=open_history_window,
            undo_panel=undo_panel,
            show_unexpected_error=show_unexpected_error,
            log_unexpected_error=log_unexpected_error,
            initial_result_message=INITIAL_RESULT_MESSAGE,
            english_ui=ENGLISH_UI,
        )
    )
    SkyButton(panel.input_area, text='관성·가속 토크 / 열부하',
              command=lambda: open_motor_duty_dialog(panel)).pack(anchor='w', padx=12, pady=5)
    notebook.add(panel, text="전동기 용량")
    return panel


# ===================================================================
# 탭 2. 트랙션비 통합 계산
# ===================================================================
def build_traction_tab(notebook, store):
    """중간 단계 탭 없이 트랙션비 통합 계산 화면을 바로 표시합니다."""
    services = TractionPanelServices(
        create_calculation_layout=create_calculation_layout,
        create_action_buttons=create_action_buttons,
        create_result_display=create_result_display,
        initial_result_text=initial_result_text,
        set_result_display=set_result_display,
        push_undo_state=push_undo_state,
        widget_language=widget_language,
        open_history_window=open_history_window,
        undo_panel=undo_panel,
        show_unexpected_error=show_unexpected_error,
        log_unexpected_error=log_unexpected_error,
    )
    panel = IntegratedTractionPanel(notebook, store, services)
    notebook.add(panel, text="트랙션비 계산")
    return panel


# ===================================================================
# 탭 3. 브레이크 제동 계산
#   d = v x t / 2 ,  t = 2d / v ,  v = 2d / t ,  a = v / t
#   (d,t 주어짐) -> v = 2d/t , a = 2d/t^2
#   (v,a 주어짐) -> t = v/a , d = v^2/(2a)
# ===================================================================
def build_brake_tab(notebook, store):
    services = BrakePanelServices(
        create_calculation_layout=create_calculation_layout,
        create_action_buttons=create_action_buttons,
        create_result_display=create_result_display,
        initial_result_text=initial_result_text,
        set_result_display=set_result_display,
        push_undo_state=push_undo_state,
        widget_language=widget_language,
        show_unexpected_error=show_unexpected_error,
        open_history_window=open_history_window,
        undo_panel=undo_panel,
        initial_result_message=INITIAL_RESULT_MESSAGE,
    )
    return build_brake_panel(notebook, store, services)


# ===================================================================
# 탭 4. 교통량 분석
#   건물인구 M: 오피스=유효면적/점유면적, 공동주택=세대수x세대당인원,
#               호텔=객실수x객실당인원, 병원=병상수, 그 밖의 용도=직접입력
#   승객수 r = 카정원 x 탑승률
#   예상 정지수 f = 로컬 정지수 fL + 운행형식별 급행 정지수 fE(0,1,2)
#   도어개폐시간 Td = td x f  /  승객출입시간 Tp = tp x r  /  손실시간 Te = 0.1x(Td+Tp)
#   일주시간 RTT = 주행시간 + Td + Tp + Te
#   대당 5분간 수송능력 P' = (5x60xr) / RTT
#   러시아워 5분간 이용자수 Q = 집중률 x M
#   설치대수 N = Q / P'  (올림)
#   평균 운전간격 = RTT / N / 예상 대기시간 = 운전간격 x 사용자 환산율
# ===================================================================


def build_traffic_tab(notebook, store):
    panel = TrafficPanel(notebook, store, TrafficPanelServices(
        create_calculation_layout=create_calculation_layout,
        create_action_buttons=create_action_buttons,
        create_result_display=create_result_display,
        initial_result_text=initial_result_text,
        set_result_display=set_result_display,
        push_undo_state=push_undo_state,
        undo_panel=undo_panel,
        widget_language=widget_language,
        open_history_window=open_history_window,
        show_unexpected_error=show_unexpected_error,
        choice_ko=choice_ko,
        choice_en=CHOICE_EN,
        initial_result_message=INITIAL_RESULT_MESSAGE,
    ))
    notebook.add(panel, text="교통량 분석")
    return panel


# 영어 모드는 계산식의 내부 키를 바꾸지 않고 화면에 보이는 문구만 바꿉니다.
# 따라서 언어를 전환해도 저장된 프로젝트와 계산 결과의 호환성이 유지됩니다.
ENGLISH_UI = {
    "대칭 S-Curve: 일정 저크로 가감속하는 단순화 운행 모델": "Symmetric S-Curve: simplified jerk-limited motion",
    "운행거리 m":"Travel distance m", "설정 최고속도 m/s":"Set peak speed m/s",
    "최대 가속도 m/s²":"Maximum acceleration m/s²", "저크 한계 m/s³":"Jerk limit m/s³",
    "등가 이동질량 kg":"Equivalent moving mass kg", "불평형·저항 합력 N":"Imbalance and resistance N",
    "시뮬레이션 실행":"Run Simulation", "이전 시뮬레이션":"Previous Simulation",
    "시뮬레이션 기록":"Simulation History", "시뮬레이션 삭제":"Clear Simulation",
    "시뮬레이션 복사 (PNG)":"Save Simulation (PNG)",
    "운행거리: 기계동력 탭의 입력값 사용. 나머지 하중·방향·효율은 두 곡선에 동일 적용.":
        "Distance comes from the mechanical plot; load, direction, and efficiencies apply to both curves.",
    "운행 방향":"Direction", "카 질량 kg":"Car mass kg", "적재 질량 kg":"Payload mass kg",
    "균형추 질량 kg":"Counterweight mass kg", "로프·회전부 등가질량 kg":"Rope/rotating equivalent mass kg",
    "이동 저항력 N":"Travel resistance N", "구동 효율 (0~1)":"Drive efficiency (0–1)",
    "회생 효율 (0~1; 미설치 0)":"Regeneration efficiency (0–1; 0 if absent)",
    "운행 중 보조전력 kW":"Auxiliary power during trip kW", "기준 최고속도 m/s":"Reference peak speed m/s",
    "기준 최대 가속도 m/s²":"Reference max acceleration m/s²", "기준 저크 m/s³":"Reference jerk m/s³",
    "후보 최고속도 m/s":"Candidate peak speed m/s", "후보 최대 가속도 m/s²":"Candidate max acceleration m/s²",
    "후보 저크 m/s³":"Candidate jerk m/s³", "기준 실측 CSV":"Reference measured CSV",
    "후보 실측 CSV":"Candidate measured CSV", "찾기":"Browse", "불러오기":"Load",
    "승강기 통합 계산 프로그램": "Integrated Elevator Calculator",
    "승강기 주요 설계값 계산·검토 및 S-Curve 운행 시뮬레이션 프로그램":
        "Elevator Design Values & Performance Analysis",
    "전동기 용량": "Motor Capacity", "트랙션비 계산": "Traction Ratio",
    "브레이크 제동": "Brake Deceleration", "교통량 분석": "Traffic Analysis",
    " 입력값 ": " Inputs ", " 계산 결과 ": " Results ",
    "계산": "Calculate", "입력값 삭제": "Clear Inputs",
    "이전 입력값": "Previous Inputs", "입력 기록": "Input History",
    "F1 단축키 도움말": "F1 Shortcut Help", "구하고자 하는 값 :": "Solve for:",
    "프로젝트 관리 Ctrl+P": "Projects  Ctrl+P", "프로젝트 저장": "Save Project",
    "입력값 전체 삭제": "Clear All Inputs", "통합 계산": "Calculate All",
    "창 고정": "Pin Window", "고정 해제": "Unpin Window",
    "다크 모드": "Dark Mode", "라이트 모드": "Light Mode", "⚙ 설정": "⚙ Settings",
    "닫기": "Close", "적용": "Apply", "프로그램 설정": "Program Settings",
    "폰트 사이즈": "Font Size", "화면 규격": "Window Size", "언어": "Language",
    " 바로가기와 도움말 ": " Shortcuts & Help ", "단축키 모음": "Shortcut List",
    "기초 개념 설명": "Basic Concepts", "프로그램을 종료하시겠습니까?": "Exit the program?",
    "선택 기록 삭제": "Delete Selected", "선택 기록 비교": "Compare Selected",
    "전체 기록 삭제": "Delete All History", "CSV 저장": "Export CSV",
    "항목": "Item", "저장 시각": "Saved At", "계산 결과": "Result",
    "키보드 단축키": "Keyboard Shortcuts", "수식 이미지 가이드": "Formula Visual Guide",
    "결과 복사": "Copy Result", "복사 완료": "Copied",
    "가닥": "ropes", "층": "floors", "세대": "households", "실": "rooms",
    "병상": "beds", "인": "people", "초": "s", "대": "cars",
    "층 (오피스 기본 2)": "floors (office default: 2)",
    "m² (오피스만)": "m² (office only)",
    "m² (; 구분, 선택)": "m² (; separated, optional)",
    "m²/인": "m²/person", "인/세대": "people/household",
    "인/실 (교재 예시 2)": "people/room (reference example: 2)",
    "인 (기타 용도)": "people (other uses)", "초/층": "s/floor",
    "초/인": "s/person", "% (운전간격 대비)": "% of interval",
    "대 (선택)": "cars (optional)", "문서명·사내기준 등": "document or company standard",
    "검색": "Search", "선택": "Select", "프로젝트 이름": "Project Name",
    "저장 시각": "Saved At", "계산식 버전": "Formula Version",
    "현재 입력 새로 저장": "Save Current Inputs",
    "선택 프로젝트 불러오기": "Load Selected Project",
    "통합 보고서": "Integrated Report", "이름 변경": "Rename", "삭제": "Delete",
    "담당자": "Manager", "담당자 변경": "Change Manager",
    "구한 값": "Solved Value", "적재하중": "Rated Load", "카 자중": "Car Weight",
    "승강행정": "Travel Height", "로프 단위중량": "Rope Unit Weight",
    "로프 수": "Number of Ropes", "보상체인": "Compensation Chain",
    "이동케이블": "Traveling Cable", "속도 단위": "Speed Unit",
    "속도": "Speed", "제동시간(s)": "Braking Time (s)",
    "제동거리(m)": "Braking Distance (m)", "감속도(m/s²)": "Deceleration (m/s²)",
    "판정방식": "Rating Method", "정지층수 방식": "Stop-floor Method",
    "서비스형식": "Service Type", "오피스 층면적": "Office Floor Area",
    "총 층수": "Total Floors", "제외층수": "Excluded Floors",
    "층별면적": "Floor Areas", "점유면적": "Area per Person",
    "집중률(%)": "Peak Rate (%)", "세대수": "Households",
    "세대당인원": "People per Household", "객실수": "Rooms",
    "객실당인원": "Guests per Room", "병상수": "Beds", "직접인구": "Direct Population",
    "정지층수": "Stops", "도어시간": "Door Time", "출입시간": "Transfer Time",
    "주행시간": "Travel Time", "대기환산율": "Waiting Factor",
    "현재대수": "Existing Cars", "양호기준": "Good Threshold",
    "불량기준": "Poor Threshold", "판정기준 메모": "Criteria Note",
    "건물용도": "Building Use", "용도값 저장": "Save Preset", "용도값 적용": "Load Preset",
    "정지층수 산정": "Stop-floor Method", "운행 서비스형식": "Service Type",
    "서비스 판정": "Service Rating", "양호 기준 이하": "Good Threshold",
    "불량 기준 초과": "Poor Threshold", "판정 기준 메모(선택)": "Criteria Note (optional)",
    "적재하중 Q": "Rated Load Q", "카 자중 Wc": "Car Weight Wc",
    "전동기 용량 P": "Motor Capacity P", "정격속도 V": "Rated Speed V",
    "전체효율 η": "Overall Efficiency η",
    "승강행정 H": "Travel Height H", "로프 단위중량 wr": "Rope Unit Weight wr",
    "로프 가닥 수 n": "Number of Ropes n", "오버밸런스율 OB": "Overbalance OB",
    "보상체인 중량": "Compensation Chain", "이동케이블 중량": "Traveling Cable",
    "속도 v": "Speed v", "제동시간 t": "Braking Time t",
    "제동거리 d": "Braking Distance d", "감속도 a": "Deceleration a",
    "오피스 층별 이용면적": "Office Floor Area", "건물층수(총 층수)": "Total Floors",
    "인구산정 제외층수": "Excluded Floors", "오피스 층별 면적목록": "Floor-area List",
    "오피스 1인당 면적": "Area per Person", "공동주택 세대수": "Households",
    "세대당 거주인구": "People per Household", "호텔 객실수": "Hotel Rooms",
    "객실당 수용인원": "Guests per Room", "병원 병상수": "Hospital Beds",
    "직접 입력 건물인구": "Building Population", "집중률 φ": "Peak Rate φ",
    "카 정원": "Car Capacity", "탑승률": "Boarding Rate",
    "로컬 정지층수 n": "Local Stops n", "도어 개폐시간": "Door Time",
    "승객 출입시간": "Passenger Transfer Time", "주행시간": "Travel Time",
    "대기시간 환산율": "Waiting-time Factor", "현재 설치대수": "Existing Cars",
    ("기본식: P = [Q × V × (1-OB)] / (6120 × η)\n"
     "속도 단위는 입력칸 옆에서 m/s 또는 m/min을 선택합니다. OB와 η는 %입니다.\n"
     "※ 숫자칸에는 50*1.1*6처럼 간단한 계산식을 직접 입력할 수 있습니다."):
        ("Base formula: P = [Q × V × (1-OB)] / (6120 × η)\n"
         "Select m/s or m/min beside the speed field. OB and η are percentages.\n"
         "You may enter simple expressions such as 50*1.1*6 in numeric fields."),
    ("문제에서 주어진 값만 입력하면 균형추·로프·전반부·후반부·최종 트랙션비를 한 번에 계산합니다.\n"
     "※ 문제에 값이 없으면 보상체인 중량과 이동케이블 중량은 0으로 입력합니다."):
        ("Enter the values given in the problem to calculate counterweight, rope, front/rear, and final traction ratios.\n"
         "Enter 0 for compensation-chain and traveling-cable weight when omitted."),
    ("속도(v), 제동시간(t), 제동거리(d), 감속도(a) 중 알고 있는 값 2개 이상을 입력하세요.\n"
     "※ 일정한 감속도로 정지한다고 가정합니다. 3개 이상 입력하면 공식 일치 여부도 검사합니다.\n"
     "※ 속도 단위는 입력칸 옆에서 m/s 또는 m/min을 선택할 수 있습니다."):
        ("Enter at least two known values among speed, braking time, distance, and deceleration.\n"
         "Constant deceleration is assumed; three or more inputs are also checked for consistency.\n"
         "Select m/s or m/min beside the speed field."),
    ("PDF 교재의 용도별 인구·RTT·5분 수송능력 공식에 따른 초기 설계용 추정입니다.\n"
     "※ 선택한 건물용도에 해당하는 인구 입력항목만 사용하며, 다른 용도의 입력값은 무시합니다.\n"
     "※ 예상 정지수는 로컬 정지수(fL)+운행형식별 급행 정지수(fE)이며 손실시간률은 10%입니다.\n"
     "※ 교재는 대기시간을 운전간격의 1/2와 약 60%로 각각 설명하므로 환산율을 직접 확인하세요."):
        ("Initial design estimate based on occupancy, RTT, and five-minute handling-capacity formulas.\n"
         "Only population fields for the selected building use are applied.\n"
         "Expected stops = local stops (fL) + express stops (fE); lost-time rate is 10%.\n"
         "Verify the waiting-time factor because the reference presents both 1/2 and about 60% of interval."),
}

CHOICE_EN = {
    "오피스-전용사옥": "Office - Single Tenant", "오피스-복합사옥": "Office - Mixed Use",
    "오피스-공공건물": "Office - Public", "오피스-임대사무실": "Office - Rental",
    "공동주택": "Residential", "호텔-고급": "Hotel - Luxury", "호텔-중급": "Hotel - Midscale",
    "호텔-비즈니스": "Hotel - Business", "병원": "Hospital", "판매시설": "Retail",
    "사용자 설정": "Custom", "실제 정지층수 직접 입력": "Enter Actual Stops",
    "교재 기준: 총 층수-2": "Reference: Total Floors - 2",
    "로컬 운전 (fE=0)": "Local Service (fE=0)",
    "편도구간 급행 (fE=1)": "One-way Express (fE=1)",
    "전층 자유 운전 (fE=2)": "All-floor Service (fE=2)",
    "PDF 교재 기준": "PDF Reference", "판정 안 함": "No Rating",
    "사용자 정의 기준": "Custom Criteria",
}
CHOICE_KO = {english: korean for korean, english in CHOICE_EN.items()}
WINDOW_PRESET_EN = {
    "자동": "Auto Fit", "PC 1000×680": "PC 1000×680",
    "데스크톱 1200×800": "Desktop 1200×800",
}
WINDOW_PRESET_KO = {english: korean for korean, english in WINDOW_PRESET_EN.items()}


def choice_ko(value):
    """영어로 표시된 선택값을 계산 로직의 기존 한국어 키로 되돌립니다."""
    return CHOICE_KO.get(value, value)


def widget_language(widget):
    try:
        return getattr(widget.winfo_toplevel(), "_language", "ko")
    except (AttributeError, tk.TclError):
        return "ko"


def apply_language(widget, language):
    """현재 존재하는 창의 고정 UI 문구를 한국어 또는 영어로 전환합니다."""
    try:
        if isinstance(widget, SkyButton):
            if not hasattr(widget, "_ko_text"):
                widget._ko_text = widget.cget("text")
            widget.config(text=ENGLISH_UI.get(widget._ko_text, widget._ko_text)
                          if language == "en" else widget._ko_text)
            return
        if isinstance(widget, (tk.Label, tk.LabelFrame, tk.Button, tk.Checkbutton)):
            if not hasattr(widget, "_ko_text"):
                widget._ko_text = widget.cget("text")
            widget.configure(text=ENGLISH_UI.get(widget._ko_text, widget._ko_text)
                             if language == "en" else widget._ko_text)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        apply_language(child, language)




# ===================================================================
# UI 컨트롤러
# ===================================================================
class LiveCalculationController:
    """입력 변경 후 지연 계산. 기록은 수동 실행 때만 남긴다."""
    def __init__(self,app,delay_ms=450):
        self.app=app;self.root=app.root;self.delay_ms=delay_ms;self.job=None
        self._executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='elevator-simulation')
        self._messages=SimpleQueue();self._serial=0;self._future=None;self._delivery_job=None

    def close(self):
        self._serial+=1
        if self.job:
            try:self.root.after_cancel(self.job)
            except tk.TclError:pass
        if self._delivery_job:
            try:self.root.after_cancel(self._delivery_job)
            except tk.TclError:pass
        self._executor.shutdown(wait=False,cancel_futures=True)

    def install(self):
        for panel in self.app.panels:
            for entry in getattr(panel,'entries',{}).values():
                entry.bind('<KeyRelease>',lambda _e,p=panel:self.schedule(p),add='+')
            for combo_name in ('target_combo','building_use_combo'):
                combo=getattr(panel,combo_name,None)
                if combo is not None:
                    combo.bind('<<ComboboxSelected>>',lambda _e,p=panel:self.schedule(p),add='+')
            for var_name in ('criterion_mode','speed_unit'):
                variable=getattr(panel,var_name,None)
                if hasattr(variable,'trace_add'):
                    variable.trace_add('write',lambda *_args,p=panel:self.schedule(p))
        criteria=self.app.criteria_panel
        for entry in (*criteria.entries.values(),*criteria.traction_entries.values()):
            entry.bind('<KeyRelease>',lambda _e,p=criteria:self.schedule(p),add='+')
        for variable in (criteria.drive,criteria.speed_conditions,*criteria.brake_checks.values()):
            variable.trace_add('write',lambda *_args,p=criteria:self.schedule(p))
        simulator=self.app.scurve_panel
        for entry in simulator.entries.values():
            entry.bind('<KeyRelease>',lambda _e,p=simulator:self.schedule(p,'mechanical'),add='+')
        for entry in simulator.energy_entries.values():
            entry.bind('<KeyRelease>',lambda _e,p=simulator:self.schedule(p,'electrical'),add='+')
        for entry in simulator.measurement_paths.values():
            entry.bind('<FocusOut>',lambda _e,p=simulator:self.schedule(p,'electrical'),add='+')
        simulator.direction.trace_add('write',lambda *_args,p=simulator:self.schedule(p,'electrical'))

    def schedule(self,panel,mode=None):
        self._serial+=1
        if self.job:
            try:self.root.after_cancel(self.job)
            except tk.TclError:pass
        self.job=self.root.after(self.delay_ms,lambda:self.run(panel,mode))

    def _submit_simulation(self,panel,mode):
        try:
            if mode=='electrical':
                values={key:parse_number(entry.get(),key) for key,entry in panel.energy_entries.items()}
                shared=dict(distance=parse_number(panel.entries['distance'].get(),'운행거리'),
                    car_mass=values['car_mass'],load_mass=values['load_mass'],
                    counterweight_mass=values['counterweight_mass'],
                    equivalent_extra_mass=values['equivalent_extra_mass'],resistance=values['resistance'],
                    direction=panel.direction.get(),drive_efficiency=values['drive_efficiency'],
                    regen_efficiency=values['regen_efficiency'],auxiliary_kw=values['auxiliary_kw'])
                reference=dict(vmax=values['ref_vmax'],amax=values['ref_amax'],jerk=values['ref_jerk'])
                candidate=dict(vmax=values['candidate_vmax'],amax=values['candidate_amax'],jerk=values['candidate_jerk'])
                paths={key:entry.get().strip() for key,entry in panel.measurement_paths.items()}
                snapshot=(shared,reference,candidate,paths)
            else:
                snapshot=tuple(parse_number(panel.entries[key].get(),key)
                               for key in ('distance','vmax','amax','jerk','mass','force'))
        except (ValueError,OverflowError):
            return
        if self._future and not self._future.done():self._future.cancel()
        serial=self._serial
        future=self._executor.submit(calculate_snapshot,mode,snapshot)
        self._future=future
        future.add_done_callback(lambda done:self._messages.put((serial,mode,done)))
        if self._delivery_job is None:
            self._delivery_job=self.root.after(40,self._deliver_simulation)

    def _deliver_simulation(self):
        self._delivery_job=None
        simulator=self.app.scurve_panel
        while True:
            try:serial,mode,future=self._messages.get_nowait()
            except Empty:break
            if serial!=self._serial or not simulator.winfo_exists():continue
            try:result,measurements=future.result()
            except CancelledError:continue
            except (ValueError,OverflowError,OSError) as error:
                if mode=='electrical':
                    simulator._energy_profile=None;simulator._reference_energy_profile=None
                    simulator.redraw_energy_plot();simulator._show_energy(f'입력/실측 오류: {error}',True)
                else:
                    simulator._profile=None;simulator.redraw_plot();simulator._show(f'입력 오류: {error}',True)
                continue
            except Exception as error:
                log_unexpected_error('실시간 시뮬레이션',error)
                if mode=='electrical':simulator._show_energy('계산 오류가 발생했습니다. 오류 로그를 확인하세요.',True)
                else:simulator._show('계산 오류가 발생했습니다. 오류 로그를 확인하세요.',True)
                continue
            if mode=='electrical':simulator.calculate_energy(precomputed=result,premeasurements=measurements)
            else:
                simulator.calculate(precomputed=result)
                if simulator._energy_profile is not None:self.schedule(simulator,'electrical')
        if self._future is not None and not self._future.done():
            self._delivery_job=self.root.after(40,self._deliver_simulation)

    def run(self,panel,mode=None):
        self.job=None
        simulator=self.app.scurve_panel
        if panel is simulator:
            entries=(list(simulator.entries.values()) if mode=='mechanical' else
                     [simulator.entries['distance'],*simulator.energy_entries.values()])
            if any(not entry.get().strip() for entry in entries):return
            for entry in entries:
                try:parse_number(entry.get(),'시뮬레이션 입력')
                except (ValueError,OverflowError):return
        elif panel is self.app.brake_panel:
            if sum(bool(entry.get().strip()) for entry in panel.entries.values())<2:return
        elif panel is self.app.criteria_panel:
            entries=(*panel.entries.values(),*panel.traction_entries.values())
            if not any(entry.get().strip() for entry in entries):return
            for entry in entries:
                if entry.get().strip():
                    try:parse_number(entry.get(),'기준 검토 입력')
                    except (ValueError,OverflowError):return
        elif panel is self.app.traffic_panel:
            if not any(entry.get().strip() for entry in panel.entries.values()):return
            for key,entry in panel.entries.items():
                if entry.get().strip() and key not in ('floor_areas','criterion_source'):
                    try:parse_number(entry.get(),key)
                    except (ValueError,OverflowError):return
        elif any(not entry.get().strip() for entry in panel.entries.values()):
            return
        store=getattr(panel,'store',None)
        previous=getattr(store,'_suppress_history',False) if store is not None else False
        if store is not None:store._suppress_history=True
        try:
            if panel is simulator:
                self._submit_simulation(panel,mode)
            else:panel.calculate()
        finally:
            if store is not None:store._suppress_history=previous


class ProjectManager:
    """프로젝트 관리 창의 진입점을 전담하여 메인 앱의 책임을 분리합니다."""
    def __init__(self, app):
        self.app = app
        self.window = None

    def open(self):
        # 기존 프로젝트 관리 로직은 계산/저장 호환성을 위해 private 구현으로 유지합니다.
        return self.app._open_project_manager_impl()


# ===================================================================
# 메인 앱
# ===================================================================
from src.core.elevator_review_engine import (KC_SOURCE, KC_URL, INTERNAL_NOTICE, compare_criterion,
    evaluate_rope_clause, evaluate_actual_speed, evaluate_brake_evidence,
    evaluate_traction_case, evaluate_motor_capacity, scurve_profile, review_guidance)





class ElevatorApp(KeyboardNavigationMixin):
    def __init__(self, root):
        self.root = root
        run_calculation_self_tests()
        self.store = PersistentStore()
        # v46: 실시간 계산은 상시 기능이므로 과거 ON/OFF 설정값은 더 이상 사용하지 않습니다.
        self.store.data.pop("auto_calc", None)
        self.store.on_save_error = lambda warning: self.root.after_idle(
            lambda: messagebox.showerror(
                "Data Save Failed" if self.language == "en" else "데이터 저장 실패",
                ("Could not save user data. Check folder permissions and free space."
                 if self.language == "en" else warning), parent=self.root)
        )
        self.current_project_id = None
        self.ui_theme = self.store.data.get("theme", "light")
        self.always_on_top = bool(self.store.data.get("always_on_top", False))
        self.font_size = int(self.store.data.get("font_size", 10))
        self.window_preset = self.store.data.get("window_preset", "자동")
        self.language = self.store.data.get("language", "ko")
        self.root._ui_theme = self.ui_theme
        self.root._language = self.language
        # 윈도우 화면 맨 위 제목 표시줄에는 짧은 이름을 사용합니다.
        self.root.title("승강기 주요 설계값 계산·검토 및 S-Curve 운행 시뮬레이션 프로그램")
        # PC 전용 자동 맞춤/1000×680 규격을 지원하며 가장자리를 직접 늘릴 수도 있습니다.
        window_width, window_height = self._window_size_for_preset(self.window_preset)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - window_width) // 2)
        y = max(0, (screen_height - window_height) // 2)
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(min(920, max(640, screen_width - 24)),
                          min(640, max(480, screen_height - 72)))
        self.root.resizable(True, True)
        self.root.attributes("-topmost", self.always_on_top)
        self.root.configure(bg="white")

        # 혹시 남아 있는 기본 Tk 버튼도 라이트 모드에서는 회색으로 표시합니다.
        # 실제 화면 버튼은 모두 외곽선을 직접 그리는 SkyButton을 사용합니다.
        self.root.option_add("*Button.background", BUTTON_BG)
        self.root.option_add("*Button.foreground", BUTTON_TEXT)
        self.root.option_add("*Button.activeBackground", BUTTON_ACTIVE_BG)
        self.root.option_add("*Button.activeForeground", "#111111")
        self.root.option_add("*Button.relief", "flat")
        self.root.option_add("*Button.borderWidth", 0)

        self.title_label = tk.Label(
            self.root,
            # 프로그램 내부의 큰 제목은 전체 기능의 목적을 정확히 설명합니다.
            text="승강기 주요 설계값 계산·검토 및 S-Curve 운행 시뮬레이션 프로그램",
            font=("맑은 고딕", 12, "bold"), bg="white", wraplength=950
        )
        self.title_label.pack(pady=(12, 8))

        # 파일명이 같아도 이 번호를 보면 최신 수정본 실행 여부를 확인할 수 있습니다.
        self.footer_bar = tk.Frame(self.root, bg="white")
        self.footer_bar.pack(side="bottom", fill="x")
        self.shortcut_label = tk.Label(
            self.footer_bar, text=self._shortcut_text(),
            font=("맑은 고딕", 9), anchor="w", justify="left", padx=10, pady=3
        )
        self.shortcut_label._theme_role = "muted"
        self.shortcut_label.pack(side="left", fill="x", expand=True)
        self.build_label = tk.Label(
            self.footer_bar, text=f"빌드 {APP_BUILD}",
            font=("맑은 고딕", 9, "bold"), anchor="e", padx=10, pady=3
        )
        self.build_label._theme_role = "muted"
        self.build_label.pack(side="right")

        style = ttk.Style(self.root)
        style.configure("TNotebook.Tab", font=("맑은 고딕", 11))

        # Notebook과 테마 버튼을 같은 컨테이너에 두면 버튼이 탭 그림 뒤로
        # 가려지지 않고 탭 줄의 오른쪽 끝에 안정적으로 표시됩니다.
        self.notebook_container = tk.Frame(self.root, bg="white")
        self.notebook_container.pack(fill="both", expand=True, padx=15, pady=10)
        # 상단 도구줄은 Notebook보다 먼저 실제 배치합니다.
        # 기존처럼 Notebook을 먼저 expand로 배치한 뒤 before= 로 끼워 넣으면 일부 Windows/Tk 환경에서
        # 초기 geometry 계산이 늦어져 버튼이 한동안 보이지 않는 현상이 생길 수 있습니다.
        self.header_controls = tk.Frame(self.notebook_container, bg="white", height=34)
        self.header_controls.pack(fill="x", pady=(0, 4))
        self.header_controls.pack_propagate(True)
        self.notebook = ttk.Notebook(self.notebook_container)
        self.notebook.pack(fill="both", expand=True)

        # 계산 탭을 가리지 않는 전용 도구줄입니다. 프로젝트 관리는 요청대로
        # 프로젝트 저장의 바로 왼쪽에 둡니다.
        self.project_manager_button = SkyButton(
            self.header_controls, text="프로젝트 관리 Ctrl+P", command=self.open_project_manager,
            font=("맑은 고딕", 9), width=15, padx=3, pady=2
        )

        self.project_button = SkyButton(
            self.header_controls, text="프로젝트 저장", command=self.save_current_project,
            font=("맑은 고딕", 9), width=10, padx=3, pady=2
        )

        self.clear_all_button = SkyButton(
            self.header_controls, text="입력값 전체 삭제", command=self.clear_all_inputs,
            font=("맑은 고딕", 9), width=13, padx=3, pady=2
        )

        self.integrated_button = SkyButton(
            self.header_controls, text="통합 계산", command=self.calculate_all,
            font=("맑은 고딕", 9, "bold"), width=9, padx=3, pady=2
        )

        self.settings_button = SkyButton(
            self.header_controls, text="⚙ 설정", command=self.open_settings,
            font=("맑은 고딕", 9), width=7, padx=3, pady=2
        )

        self.topmost_button = SkyButton(
            self.header_controls,
            text="창 고정" if not self.always_on_top else "고정 해제",
            command=self.toggle_always_on_top,
            font=("맑은 고딕", 9), width=9, padx=3, pady=2
        )

        self._header_buttons = (
            self.project_manager_button, self.project_button, self.clear_all_button,
            self.integrated_button, self.topmost_button, self.settings_button,
        )
        self._layout_header_controls()
        self.header_controls.lift()

        # 무거운 계산 탭을 만들기 전에 상단 버튼을 실제 화면에 먼저 그립니다.
        self.root.update_idletasks()
        self.root.update()

        self.motor_panel = build_motor_tab(self.notebook, self.store)
        self.traction_panel = build_traction_tab(self.notebook, self.store)
        self.brake_panel = build_brake_tab(self.notebook, self.store)
        self.traffic_panel = build_traffic_tab(self.notebook, self.store)
        self.criteria_panel = CriteriaPanel(self.notebook, self.store, CriteriaPanelServices(
            create_result_display=create_result_display,
            set_result_display=set_result_display,
            push_undo_state=push_undo_state,
            open_history_window=open_history_window,
            undo_panel=undo_panel,
        ))
        self.notebook.add(self.criteria_panel, text="KC 기준 검토")
        self.scurve_panel = SCurvePanel(self.notebook, self.store, SCurvePanelServices(
            create_result_display=create_result_display,
            set_result_display=set_result_display,
            push_undo_state=push_undo_state,
            undo_panel=undo_panel,
            log_unexpected_error=log_unexpected_error,
        ))
        self.notebook.add(self.scurve_panel, text="S-Curve 시뮬레이션")
        self.root._elevator_app = self
        self.panels = [self.motor_panel, self.traction_panel,
                       self.brake_panel, self.traffic_panel]
        # 자동 전달값은 사용자가 직접 수정한 값을 덮어쓰지 않도록
        # '프로그램이 마지막으로 자동 입력한 값'을 항목별로 따로 기억합니다.
        self._auto_filled_values = {}
        self._last_tab_index = 0
        self._tab_after_enter = None
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        self.root.bind_all("<Control-Return>", self._shortcut_calculate)
        self.root.bind_all("<Control-l>", self._shortcut_clear)
        self.root.bind_all("<Control-L>", self._shortcut_clear)
        self.root.bind_all("<Control-z>", self._shortcut_undo)
        self.root.bind_all("<Control-Z>", self._shortcut_undo)
        self.root.bind_all("<Control-h>", self._shortcut_history)
        self.root.bind_all("<Control-H>", self._shortcut_history)
        self.root.bind_all("<Control-p>", self._shortcut_projects)
        self.root.bind_all("<Control-P>", self._shortcut_projects)
        self.root.bind_all("<Control-i>", self._shortcut_integrated)
        self.root.bind_all("<Control-I>", self._shortcut_integrated)
        self.root.bind_all("<Alt-t>", self._shortcut_theme)
        self.root.bind_all("<Alt-T>", self._shortcut_theme)
        self.root.bind_all("<Control-Right>", self._shortcut_next_tab)
        self.root.bind_all("<space>", self._shortcut_next_tab)
        for panel in (*self.panels, self.criteria_panel, self.scurve_panel):
            entries = list(panel.entries.items())
            if panel is self.criteria_panel:
                entries += list(panel.traction_entries.items())
            if panel is self.scurve_panel:
                entries += list(panel.energy_entries.items())
                entries += list(panel.measurement_paths.items())
            for key, entry in entries:
                # 메모칸에는 공백을 입력할 수 있게 유지하고, 모든 입력칸에 Tab 이동을 연결합니다.
                if not ((panel is self.traffic_panel and key == "criterion_source") or
                        (panel is self.scurve_panel and entry in panel.measurement_paths.values())):
                    entry.bind("<space>", self._shortcut_next_tab, add="+")
                entry.bind("<Tab>", lambda e, p=panel: self._focus_adjacent_input(p, e.widget, 1), add="+")
                entry.bind("<Shift-Tab>", lambda e, p=panel: self._focus_adjacent_input(p, e.widget, -1), add="+")
                entry.bind("<ISO_Left_Tab>", lambda e, p=panel: self._focus_adjacent_input(p, e.widget, -1), add="+")
                entry.bind("<KeyRelease-Return>",
                           lambda e,p=panel:self._mark_calculated_input(p,e.widget),add="+")
                entry.bind("<KeyPress>",self._clear_calculated_on_edit,add="+")
            for result in (getattr(panel,'result_text',None),
                           getattr(panel,'energy_result',None)):
                if result is not None:
                    result.bind("<Tab>",lambda _event:self._move_to_next_tab(),add="+")
        self.root.bind_all("<F1>", self.show_shortcut_help)
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.confirm_exit)
        # 시작 화면에도 라이트 모드 색상표가 바로 보이도록 적용합니다.
        # 지원하지 않는 Windows Tk 옵션은 테마 함수 내부에서 안전하게 건너뜁니다.
        self.apply_current_theme()
        self.apply_font_size(self.font_size)
        self.apply_current_language()
        self.window_manager = WindowManager
        self.project_manager = ProjectManager(self)
        self.live_calculation = LiveCalculationController(self)
        self.live_calculation.install()
        self._install_motor_secondary_speed()
        self._layout_header_controls()
        self.header_controls.update_idletasks()
        self.root.after_idle(self._layout_header_controls)
        self.root.after_idle(self._fit_main_window_to_controls)
        if self.store.load_warning:
            self.root.after(
                150,
                lambda: messagebox.showwarning(
                    "Load Input History" if self.language == "en" else "입력 기록 불러오기",
                    ("Stored user data could not be loaded. A new local data file will be used."
                     if self.language == "en" else self.store.load_warning))
            )

    def _window_size_for_preset(self, preset):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        sizes = {
            "PC 1000×680": (1000, 680),
            "데스크톱 1200×800": (1200, 800),
        }
        if preset == "자동":
            width = min(max(640,screen_w-24),min(1280,max(1100,screen_w-72)))
            height = min(max(480,screen_h-72),min(900,max(780,screen_h-110)))
        else:
            width, height = sizes.get(preset, (1000, 680))
            width = min(max(width, 1200), max(640, screen_w - 24))
            height = min(max(height, 840), max(480, screen_h - 72))
        return width, height

    def set_window_preset(self, preset):
        """PC 화면 규격을 적용하고 화면 중앙에 배치합니다."""
        width, height = self._window_size_for_preset(preset)
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.window_preset = preset
        self._layout_header_controls(width)
        self._fit_main_window_to_controls()

    def _fit_main_window_to_controls(self):
        """버튼의 실제 요청 폭을 재어 최소 창 너비와 시작 크기를 맞춘다."""
        if not hasattr(self,'_header_buttons'):
            return
        self.root.update_idletasks()
        available_w=max(640,self.root.winfo_screenwidth()-24)
        available_h=max(480,self.root.winfo_screenheight()-72)
        required_w=max(960,self.header_controls.winfo_reqwidth()+36)
        required_h=max(820,self.title_label.winfo_reqheight()
                       +self.header_controls.winfo_reqheight()
                       +self.footer_bar.winfo_reqheight()+520)
        minimum_w=min(required_w,available_w)
        minimum_h=min(required_h,available_h)
        self.root.minsize(minimum_w,minimum_h)
        if self.root.winfo_width()<minimum_w or self.root.winfo_height()<minimum_h:
            self.root.geometry(f'{max(self.root.winfo_width(),minimum_w)}x'
                               f'{max(self.root.winfo_height(),minimum_h)}')

    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        if hasattr(self, "_layout_job"):
            self.root.after_cancel(self._layout_job)
        self._layout_job = self.root.after(80, lambda: self._layout_header_controls(event.width))

    def _layout_header_controls(self, width=None):
        """실제 버튼 글자 폭으로 1·2줄을 결정해 어느 해상도에서도 잘리지 않게 한다."""
        if not hasattr(self,"_header_buttons"):
            return
        width=width or max(self.root.winfo_width(),self._window_size_for_preset(self.window_preset)[0])
        for button in self._header_buttons:
            button.grid_forget()
            button.config(width=0)  # 글자 전체를 표시하도록 자연 너비 사용
        for column in range(8):
            self.header_controls.grid_columnconfigure(column,weight=0)
        requested=sum(button.winfo_reqwidth()+6 for button in self._header_buttons)
        compact=requested>width-60 or self.font_size>=12
        if compact:
            rows=((self.project_manager_button,self.project_button,self.clear_all_button),
                  (self.integrated_button,self.topmost_button,self.settings_button))
        else:
            rows=(self._header_buttons,)
        for row_index,buttons in enumerate(rows):
            for column,button in enumerate(buttons):
                button.grid(row=row_index,column=column,padx=(0 if column==0 else 6,0),
                            pady=2,sticky="w")


    def apply_font_size(self, size):
        self.font_size = max(9, min(14, int(size)))
        self.root._font_size = self.font_size
        apply_font_scale(self.root, self.font_size)
        style = ttk.Style(self.root)
        style.configure("TNotebook.Tab", font=("맑은 고딕", self.font_size + 1))
        style.configure("TCombobox", font=("맑은 고딕", self.font_size))
        style.configure("Project.Treeview", font=("맑은 고딕", self.font_size),
                        rowheight=max(26, self.font_size * 3))
        style.configure("Project.Treeview.Heading",
                        font=("맑은 고딕", max(9, self.font_size - 1), "bold"))
        self._layout_header_controls()
        self._fit_main_window_to_controls()

    def apply_current_language(self):
        self.root._language = self.language
        apply_language(self.root, self.language)
        update_formula_previews(self.root, self.language)
        motor_labels = [item["label"] for item in self.motor_panel.vars_spec]
        target_index = max(0, self.motor_panel.target_combo.current())
        self.motor_panel.target_combo.configure(
            values=tuple(ENGLISH_UI.get(label, label) for label in motor_labels)
            if self.language == "en" else tuple(motor_labels)
        )
        self.motor_panel.target_combo.current(target_index)
        self.traffic_panel.apply_choice_language(self.language)
        self.scurve_panel.mode_tabs.tab(0,text="Mechanical Plot" if self.language=="en" else "기계동력 곡선")
        self.scurve_panel.mode_tabs.tab(1,text="Electrical Energy" if self.language=="en" else "전기에너지 비교")
        tab_names = (("전동기 용량", "Motor Capacity"),
                     ("트랙션비 계산", "Traction Ratio"),
                     ("브레이크 제동", "Brake Deceleration"),
                     ("교통량 분석", "Traffic Analysis"),
                     ("KC 기준 검토", "KC Clause Review"),
                     ("S-Curve 시뮬레이션", "S-Curve Simulation"))
        for index, names in enumerate(tab_names):
            self.notebook.tab(index, text=names[1] if self.language == "en" else names[0])
        if self.language == "en":
            self.root.title("Elevator Design Calculations and S-Curve Simulation")
            self.shortcut_label.config(text=self._shortcut_text())
            self.build_label.config(text=f"Build {APP_BUILD}")
            self.topmost_button.config(text="Unpin Window" if self.always_on_top else "Pin Window")
        else:
            self.root.title("승강기 주요 설계값 계산·검토 및 S-Curve 운행 시뮬레이션 프로그램")
            self.shortcut_label.config(text=self._shortcut_text())
            self.build_label.config(text=f"빌드 {APP_BUILD}")
            self.topmost_button.config(text="고정 해제" if self.always_on_top else "창 고정")
        prompt = ("Enter the required values, then select Calculate.\n"
                  "Results and validation details will appear here."
                  if self.language == "en" else INITIAL_RESULT_MESSAGE)
        for panel in self.panels:
            panel._show(prompt)
        self._layout_header_controls()

    def clear_all_inputs(self):
        english = self.language == "en"
        if not messagebox.askyesno(
                "Clear All Inputs" if english else "입력값 전체 삭제",
                ("Clear all inputs in Motor, Traction, Brake, and Traffic?\n"
                 "You can restore the values from Previous Inputs in each tab."
                 if english else
                "여섯 탭의 입력값을 모두 삭제할까요?\n"
                "기존 계산 탭과 기준 검토 탭은 ‘이전 입력값’으로 복원할 수 있습니다."),
                parent=self.root):
            return
        for panel in (*self.panels, self.criteria_panel, self.scurve_panel):
            clear_command = getattr(panel, "clear", None) or getattr(panel, "reset", None)
            if clear_command:
                clear_command()
        self._auto_filled_values.clear()
        self._show_transfer_status(
            "All inputs were cleared." if english else "여섯 탭의 입력값을 모두 삭제했습니다."
        )

    def _panel_report_text(self,panel):
        result=panel.result_text.get("1.0","end-1c").strip()
        if panel is self.scurve_panel:result += "\n\n"+panel.energy_result.get("1.0","end-1c").strip()
        return result

    def calculate_all(self):
        """왼쪽 2×2 계산 카드와 오른쪽 세로 검토·시뮬레이션 카드를 표시합니다."""
        common = self._collect_live_common_values(self.notebook.index(self.notebook.select()))
        for panel in (*self.panels, self.criteria_panel, self.scurve_panel):
            self._apply_live_common_values(panel, common)
            panel.calculate()
        self.scurve_panel.calculate_energy()

        window = tk.Toplevel(self.root)
        english = self.language == "en"
        window.title("Integrated Calculation Results" if english else "통합 계산 결과")
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        width = min(1440, max(720, screen_w - 96))
        height = min(900, max(520, screen_h - 110))
        window.minsize(min(720, width), min(520, height))
        window.transient(self.root)
        WindowManager.center(window, self.root, width, height)
        window._ui_theme = self.ui_theme
        window._language = self.language

        results = (("Motor Capacity" if english else "전동기 용량", self.motor_panel),
                   ("Traction Ratio" if english else "트랙션비", self.traction_panel),
                   ("Brake" if english else "브레이크", self.brake_panel),
                   ("Traffic Analysis" if english else "교통량", self.traffic_panel),
                   ("KC Clause Review" if english else "기준 검토", self.criteria_panel),
                   ("S-Curve Simulation" if english else "S-Curve 시뮬레이션", self.scurve_panel))

        toolbar = tk.Frame(window)
        toolbar.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(
            toolbar,
            text="Integrated Results" if english else "통합 계산 결과",
            font=("맑은 고딕", 15, "bold"), anchor="w"
        ).pack(side="left", fill="x", expand=True)

        def combined_text():
            blocks = []
            for name, panel in results:
                blocks.extend((name, self._panel_report_text(panel), ""))
            return "\n".join(blocks).rstrip()

        def copy_results():
            window.clipboard_clear()
            window.clipboard_append(combined_text())
            copy_button.config(text="Copied" if english else "복사 완료")
            window.after(1200, lambda: copy_button.config(
                text="Copy Results" if english else "결과 복사"))

        copy_button = SkyButton(
            toolbar, text="Copy Results" if english else "결과 복사",
            command=copy_results, width=12, font=("맑은 고딕", 10, "bold")
        )
        copy_button.pack(side="right")

        # 네 계산을 2×2로 유지하고, 긴 두 결과는 오른쪽 한 열에 세로로 둡니다.
        cards = tk.Frame(window)
        cards.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        cards.grid_rowconfigure(0, weight=1)
        cards.grid_columnconfigure(0, weight=9)
        cards.grid_columnconfigure(1, weight=11)
        left_cards = tk.Frame(cards)
        right_cards = tk.Frame(cards)
        left_cards.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        right_cards.grid(row=0, column=1, sticky="nsew")
        compact_height = min(255, max(190, (height - 155) // 3))
        for grid_index in range(2):
            left_cards.grid_rowconfigure(grid_index, minsize=compact_height)
            left_cards.grid_columnconfigure(grid_index, weight=1, uniform="compact_result")
            right_cards.grid_rowconfigure(grid_index, weight=1, uniform="detailed_result")
        right_cards.grid_columnconfigure(0, weight=1)

        for index, (name, panel) in enumerate(results, start=1):
            parent = left_cards if index <= 4 else right_cards
            card_border = tk.Frame(parent, bd=0)
            card_border._theme_role = "history_card_border"
            row, column = INTEGRATED_RESULT_CELLS[index - 1]
            if index > 4:
                column = 0
            card_border.grid(
                row=row, column=column, sticky="nsew",
                padx=(0 if column == 0 else 7, 0),
                pady=(0, 7 if row == 0 else 0),
            )
            card = tk.Frame(card_border, bd=0)
            card._theme_role = "surface"
            card.pack(fill="both", expand=True, padx=2, pady=2)
            header = tk.Label(
                card, text=f"{index}. {name}", font=("맑은 고딕", 11, "bold"),
                anchor="w", padx=12, pady=8
            )
            header._theme_role = "header_1" if index % 2 else "header_2"
            header.pack(fill="x")
            result_host = tk.Frame(card)
            result_host.pack(fill="both", expand=True, padx=8, pady=8)
            text_widget = tk.Text(
                result_host, wrap="word", font=("맑은 고딕", 10),
                padx=10, pady=10, height=7, relief="flat"
            )
            bar = ttk.Scrollbar(result_host, orient="vertical", command=text_widget.yview)
            text_widget.configure(yscrollcommand=bar.set)
            bar.pack(side="right", fill="y")
            text_widget.pack(side="left", fill="both", expand=True)
            text_widget.insert("1.0", self._panel_report_text(panel))
            text_widget.config(state="disabled")

        SkyButton(
            window, text="Close" if english else "닫기",
            command=window.destroy, width=10
        ).pack(pady=(2, 12))
        apply_theme(window, self.ui_theme)
        apply_font_scale(window, self.font_size)

    def _show_basic_concepts_legacy(self, parent=None):
        parent = parent or self.root
        if hasattr(self, "_concept_window") and self._concept_window.winfo_exists():
            self._concept_window.lift()
            self._concept_window.focus_force()
            return
        english = self.language == "en"
        window = tk.Toplevel(parent)
        self._concept_window = window
        window.title("Formula Visual Guide" if english else "계산 수식 이미지 가이드")
        WindowManager.center(window, parent, 900, 650)
        window.minsize(720, 520)
        window.transient(parent)
        window._ui_theme = self.ui_theme
        window._language = self.language

        heading = tk.Label(
            window,
            text=("Elevator Calculation Flow" if english else "승강기 계산 흐름을 그림으로 보기"),
            font=("맑은 고딕", 15, "bold"), anchor="w",
        )
        heading.pack(fill="x", padx=18, pady=(16, 8))
        notebook = ttk.Notebook(window)
        notebook.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        diagrams = [
            (("Motor", "전동기 용량"),
             [("Inputs\nQ, V, OB, η", "입력값\nQ, V, OB, η"),
              ("Power Formula\nP = Q×V×(1−OB) / (6120×η)", "출력 공식\nP = Q×V×(1−OB) / (6120×η)"),
              ("Motor Capacity\nP (kW)", "전동기 용량\nP (kW)")],
             ("Confirm the speed unit and enter OB and η as percentages.",
              "속도 단위를 확인하고 OB와 η는 백분율로 입력합니다.")),
            (("Traction", "트랙션비"),
             [("Car / Load / Rope", "카·적재하중·로프"),
              ("Front Tf  |  Rear Tr", "전반부 Tf  |  후반부 Tr"),
              ("Final Ratio\nmax(Tf, Tr)", "최종 트랙션비\nmax(Tf, Tr)")],
             ("The larger ratio is the governing traction condition.",
              "두 비율 중 큰 값이 불리한 최종 조건입니다.")),
            (("Brake", "브레이크"),
             [("Enter 2+ known values\nv, t, d, a", "알고 있는 값 2개 이상\nv, t, d, a"),
              ("d = v×t / 2\na = v / t", "d = v×t / 2\na = v / t"),
              ("Speed · Time\nDistance · Deceleration", "속도·시간\n거리·감속도")],
             ("The guide assumes constant deceleration to a stop.",
              "일정한 감속도로 정지한다고 가정합니다.")),
            (("Traffic", "교통량"),
             [("Population × Peak Rate\n= 5-min Demand", "건물인구 × 집중률\n= 5분 수요"),
              ("Capacity per Car\n= Riders × 300 / RTT", "대당 수송능력\n= 승객수 × 300 / RTT"),
              ("Cars → Interval → Wait", "필요대수 → 운전간격 → 대기")],
             ("This is an initial design estimate based on the selected assumptions.",
              "선택한 가정에 따른 초기 설계용 추정입니다.")),
        ]

        palette = THEMES[self.ui_theme]

        def draw_diagram(canvas, nodes, note):
            canvas.delete("all")
            width = max(canvas.winfo_width(), 680)
            height = max(canvas.winfo_height(), 390)
            canvas.configure(bg=palette["surface"])
            box_width = min(560, width - 100)
            left = (width - box_width) / 2
            right = left + box_width
            top = 45
            box_height = 78
            gap = 42
            for index, pair in enumerate(nodes):
                label = pair[0] if english else pair[1]
                y1 = top + index * (box_height + gap)
                y2 = y1 + box_height
                fill = "#dff1ff" if index != 1 else "#e8f7e8"
                if self.ui_theme == "dark":
                    fill = "#123c59" if index != 1 else "#174d38"
                canvas.create_rectangle(
                    left, y1, right, y2, fill=fill,
                    outline=palette["accent"], width=2,
                )
                canvas.create_text(
                    width / 2, (y1 + y2) / 2, text=label,
                    fill=palette["text"], font=("맑은 고딕", 13, "bold"),
                    justify="center",
                )
                if index < len(nodes) - 1:
                    canvas.create_line(
                        width / 2, y2 + 5, width / 2, y2 + gap - 5,
                        fill=palette["accent"], width=3, arrow=tk.LAST,
                    )
            canvas.create_text(
                width / 2, height - 34, text=note[0] if english else note[1],
                fill=palette["muted"], font=("맑은 고딕", 10),
                width=width - 70, justify="center",
            )

        for titles, nodes, note in diagrams:
            page = tk.Frame(notebook)
            canvas = tk.Canvas(page, highlightthickness=0)
            canvas.pack(fill="both", expand=True)
            canvas.bind("<Configure>", lambda _e, c=canvas, n=nodes, tip=note: draw_diagram(c, n, tip))
            notebook.add(page, text=titles[0] if english else titles[1])

        SkyButton(
            window, text="Close" if english else "닫기", command=window.destroy, width=10
        ).pack(pady=(0, 12))
        apply_theme(window, self.ui_theme)
        apply_font_scale(window, self.font_size)

    def show_basic_concepts(self, parent=None):
        """설정에서 네 계산식 이미지를 잘림 없이 확인하는 전용 가이드입니다."""
        parent = parent or self.root
        if hasattr(self, "_concept_window") and self._concept_window.winfo_exists():
            self._concept_window.lift()
            self._concept_window.focus_force()
            return
        english = self.language == "en"
        window = tk.Toplevel(parent)
        self._concept_window = window
        window.title("Formula Visual Guide" if english else "계산 수식 이미지 가이드")
        window.minsize(760, 560)
        window.transient(parent)
        window._ui_theme = self.ui_theme
        window._language = self.language
        center_child_window(window, parent, 940, 680)

        tk.Label(
            window,
            text=("Formula Visual Guide" if english else "수식 이미지 가이드"),
            font=("맑은 고딕", 15, "bold"), anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 4))
        tk.Label(
            window,
            text=("Select a tab to view the complete formula without cropping."
                  if english else "계산 항목 탭을 선택하면 잘리지 않은 전체 수식을 확인할 수 있습니다."),
            font=("맑은 고딕", 10), anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 10))

        notebook = ttk.Notebook(window)
        notebook.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        guide_items = (
            ("motor", "Motor Capacity", "전동기 용량"),
            ("traction", "Traction Ratio", "트랙션비"),
            ("brake", "Brake", "브레이크"),
            ("traffic", "Traffic Analysis", "교통량"),
        )
        window._formula_photos = []

        for key, title_en, title_ko in guide_items:
            page = tk.Frame(notebook)
            notebook.add(page, text=title_en if english else title_ko)
            canvas = tk.Canvas(page, highlightthickness=0)
            scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            content = tk.Frame(canvas)
            content_id = canvas.create_window((0, 0), window=content, anchor="n")

            tk.Label(content, text=title_en if english else title_ko,
                     font=("맑은 고딕", 14, "bold"), anchor="center").pack(
                         fill="x", padx=20, pady=(22, 12))
            if english:
                formula = tk.Label(
                    content, text=FORMULA_TEXT_EN[key], justify="left", anchor="w",
                    font=("맑은 고딕", 12, "bold"), padx=24, pady=22,
                    highlightthickness=1,
                )
                formula._theme_role = "formula"
                formula.pack(fill="x", padx=34, pady=12)
                formula_target = formula
            else:
                # 고해상도 원본을 그대로 표시합니다. 강제 확대는 픽셀 깨짐의 원인이 됩니다.
                photo = tk.PhotoImage(data=FORMULA_IMAGE_DATA[key])
                window._formula_photos.append(photo)
                image_label = tk.Label(content, image=photo, bd=1, relief="solid",
                                       padx=0, pady=0)
                image_label._theme_role = "formula"
                image_label.pack(padx=4, pady=12)
                formula_target = image_label

            def resize_content(event, c=canvas, item_id=content_id):
                c.itemconfigure(item_id, width=max(event.width, 720))

            def update_scroll(_event, c=canvas, holder=content):
                c.configure(scrollregion=c.bbox("all"))

            canvas.bind("<Configure>", resize_content)
            content.bind("<Configure>", update_scroll)
            def scroll_formula(event, c=canvas):
                c.yview_scroll(int(-event.delta / 120), "units")
                return "break"

            for target in (page, canvas, content, formula_target):
                target.bind("<MouseWheel>", scroll_formula, add="+")

        SkyButton(window, text="Close" if english else "닫기",
                  command=window.destroy, width=10).pack(pady=(0, 14))
        apply_theme(window, self.ui_theme)
        apply_font_scale(window, self.font_size)

    def open_settings(self):
        if hasattr(self, "_settings_window") and self._settings_window.winfo_exists():
            self._settings_window.lift()
            self._settings_window.focus_force()
            return
        english = self.language == "en"
        window = tk.Toplevel(self.root)
        self._settings_window = window
        window.title("Settings" if english else "설정")
        window.resizable(False, False)
        window.transient(self.root)
        center_child_window(window, self.root, 560, 610)
        window._ui_theme = self.ui_theme
        window._language = self.language

        tk.Label(window, text="Program Settings" if english else "프로그램 설정", font=("맑은 고딕", 14, "bold"),
                 anchor="w").pack(fill="x", padx=18, pady=(18, 10))
        form = tk.Frame(window)
        form.pack(fill="x", padx=18)
        font_var = tk.IntVar(value=self.font_size)
        preset_var = tk.StringVar(value=WINDOW_PRESET_EN.get(self.window_preset, self.window_preset) if english else self.window_preset)
        language_var = tk.StringVar(value="English" if self.language == "en" else "한국어")
        theme_var = tk.StringVar(value=("Dark" if self.ui_theme == "dark" else "Light") if english else
                                 ("다크" if self.ui_theme == "dark" else "라이트"))

        preset_values = (("Auto Fit", "PC 1000×680", "Desktop 1200×800") if english else
                         ("자동", "PC 1000×680", "데스크톱 1200×800"))
        rows = ((("Font Size" if english else "폰트 사이즈"), font_var, (9, 10, 11, 12, 13, 14)),
                (("Window Size" if english else "화면 규격"), preset_var, preset_values),
                (("Language" if english else "언어"), language_var,
                 (("Korean", "English") if english else ("한국어", "English"))))
        for label, variable, values in rows:
            row = tk.Frame(form)
            row.pack(fill="x", pady=7)
            tk.Label(row, text=label, width=15, anchor="w",
                     font=("맑은 고딕", 10, "bold")).pack(side="left")
            combo = ttk.Combobox(row, textvariable=variable, values=values,
                                 state="readonly", width=25, font=("맑은 고딕", 10))
            combo.pack(side="left", fill="x", expand=True)
            bind_combobox_popdown_theme(combo)

        spec = tk.Label(
            form,
            text=("Window sizes: Auto Fit / PC 1000×680 / Desktop 1200×800\n"
                  "Header buttons automatically move to two rows when space is limited."
                  if english else
                  "화면 규격: 자동 맞춤 / PC 1000×680 / 데스크톱 1200×800\n"
                  "글꼴을 키우거나 창을 줄이면 상단 버튼이 자동으로 두 줄 배치됩니다."),
            justify="left", anchor="w", font=("맑은 고딕", 9)
        )
        spec._theme_role = "muted"
        spec.pack(fill="x", pady=(2, 12))

        links = tk.LabelFrame(
            window, text=" Shortcuts & Help " if english else " 바로가기와 도움말 ",
            padx=10, pady=10,
        )
        links.pack(fill="x", padx=18, pady=4)
        SkyButton(
            links, text="Project Manager  Ctrl+P" if english else "프로젝트 관리 Ctrl+P",
            command=self.open_project_manager,
        ).pack(fill="x", pady=3)
        SkyButton(
            links, text="Keyboard Shortcuts" if english else "키보드 단축키",
            command=self.show_shortcut_help,
        ).pack(fill="x", pady=3)
        SkyButton(
            links, text="Formula Visual Guide" if english else "수식 이미지 가이드",
            command=lambda: self.show_basic_concepts(window),
        ).pack(fill="x", pady=3)
        def apply_settings():
            self.apply_font_size(font_var.get())
            selected_preset = WINDOW_PRESET_KO.get(preset_var.get(), preset_var.get())
            self.set_window_preset(selected_preset)
            previous_language = self.language
            self.language = "en" if language_var.get() == "English" else "ko"
            selected_theme = "dark" if theme_var.get() in ("Dark", "다크") else "light"
            self.ui_theme = selected_theme
            self.store.set_theme(self.ui_theme)
            self.store.set_ui_preferences(self.font_size, self.window_preset, self.language)
            self.apply_current_theme()
            if self.language != previous_language:
                # 이미 열린 보조창의 표 머리글처럼 즉시 번역하기 어려운 항목은
                # 닫은 뒤 새 언어로 다시 열게 하여 혼합 언어가 남지 않게 합니다.
                for child in self.root.winfo_children():
                    if isinstance(child, tk.Toplevel) and child is not window:
                        child.destroy()
            self.apply_current_language()
            chosen_english = self.language == "en"
            window._language = self.language
            window.destroy()
            messagebox.showinfo(
                "Settings" if chosen_english else "설정",
                "Settings have been applied." if chosen_english else "화면 설정을 적용했습니다.",
                parent=self.root,
            )

        buttons = tk.Frame(window)
        buttons.pack(side="bottom", fill="x", padx=18, pady=18)
        SkyButton(buttons, text="Apply" if english else "적용", command=apply_settings, width=10).pack(side="right")
        SkyButton(buttons, text="Close" if english else "닫기", command=window.destroy, width=10).pack(side="right", padx=6)
        apply_theme(window, self.ui_theme)
        apply_font_scale(window, self.font_size)

    def confirm_exit(self):
        """제목 표시줄 X를 눌렀을 때 YES/NO로 종료 여부를 확인합니다."""
        if hasattr(self, "_exit_window") and self._exit_window.winfo_exists():
            self._exit_window.lift()
            return
        english = self.language == "en"
        window = tk.Toplevel(self.root)
        self._exit_window = window
        window.title("Exit Program" if english else "프로그램 종료")
        window.resizable(False, False)
        window.transient(self.root)
        window._ui_theme = self.ui_theme
        window._language = self.language
        tk.Label(window, text="Exit the program?" if english else "프로그램을 종료하시겠습니까?",
                 font=("맑은 고딕", 12, "bold")).pack(expand=True, pady=(28, 12))
        buttons = tk.Frame(window)
        buttons.pack(pady=(0, 22))
        def exit_program():
            self.live_calculation.close()
            self.root.destroy()
        SkyButton(buttons, text="YES", command=exit_program, width=10).pack(side="left", padx=8)
        SkyButton(buttons, text="NO", command=window.destroy, width=10).pack(side="left", padx=8)
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        apply_theme(window, self.ui_theme)
        apply_font_scale(window, self.font_size)
        center_child_window(window, self.root, 380, 170)
        window.grab_set()

    def active_panel(self):
        try:
            return (self.panels + [self.criteria_panel, self.scurve_panel])[self.notebook.index(self.notebook.select())]
        except (tk.TclError, IndexError):
            return self.motor_panel

    def _shortcut_text(self):
        if getattr(self, "language", "ko") == "en":
            return ("Ctrl+Enter Calculate  |  Ctrl+L Clear  |  Ctrl+Z Undo  |  "
                    "Space / Ctrl+Right Next Tab  |  Ctrl+P Projects")
        return ("Ctrl+Enter 계산  |  Ctrl+L 입력값 삭제  |  Ctrl+Z 실행 취소  |  "
                "Space / Ctrl+Right 다음 계산창  |  Ctrl+P 프로젝트 관리  |  Ctrl+I 통합계산")

    def _show_transfer_status(self, message):
        """자동으로 옮긴 항목을 하단에 잠시 표시한 뒤 단축키 문구로 복원합니다."""
        self.shortcut_label.config(text=message)
        if hasattr(self, "_transfer_status_job"):
            self.root.after_cancel(self._transfer_status_job)
        self._transfer_status_job = self.root.after(
            2800, lambda: self.shortcut_label.config(text=self._shortcut_text())
        )

    @staticmethod
    def _panel_number(panel, key):
        """패널 입력값을 읽되 비어 있거나 계산식이 잘못됐으면 전달하지 않습니다."""
        entry = panel.entries.get(key)
        if entry is None or not entry.get().strip():
            return None
        try:
            return parse_number(entry.get(), key)
        except ValueError:
            return None

    def _collect_live_common_values(self, preferred_index):
        """방금 편집한 탭을 우선해 단위와 의미가 일치하는 입력만 수집한다."""
        all_panels = (*self.panels, self.criteria_panel, self.scurve_panel)
        order = ([preferred_index] if 0 <= preferred_index < len(all_panels) else []) + [
            i for i in range(len(all_panels)) if i != preferred_index]
        common = {}
        sources = {}
        def remember(key, value, index):
            if value is not None and key not in common:
                common[key] = value
                sources[key] = index
        for index in order:
            panel = all_panels[index]
            if panel is self.motor_panel:
                q_value = self._panel_number(panel, "Q")
                ob_value = self._panel_number(panel, "OB")
                speed_value = self._panel_number(panel, "V")
                remember("Q",q_value,index)
                remember("OB",ob_value,index)
                if speed_value is not None:
                    unit = panel.unit_vars.get("V")
                    remember("speed_m_s",speed_value/60 if unit and unit.get()=="m/min" else speed_value,index)
            elif panel is self.traction_panel:
                q_value = self._panel_number(panel, "Q")
                ob_value = self._panel_number(panel, "OB")
                rope_count = self._panel_number(panel, "n")
                remember("Q",q_value,index)
                remember("OB",ob_value,index)
                remember("rope_count",rope_count,index)
            elif panel is self.criteria_panel:
                rated = self._panel_number(panel, "rated")
                remember("speed_m_s",rated,index)
                if panel.drive.get() == "권상식":
                    count = self._panel_number(panel, "count")
                    remember("rope_count",count,index)
            # 제동의 시작속도와 시뮬레이션의 속도 상한은 정격속도와 다를 수 있다.
            # 이 두 탭에서 정격속도를 역으로 덮어쓰지 않는다.
        common["__sources__"] = sources
        common["__preferred__"] = preferred_index
        return common

    def _can_auto_fill(self, panel, key, force=False):
        """빈칸이거나 이전 자동입력 그대로인 항목만 갱신합니다."""
        entry = panel.entries.get(key)
        if entry is None or str(entry.cget("state")) == "disabled":
            return False
        if force:
            return True
        current = entry.get().strip()
        previous_auto = self._auto_filled_values.get((panel.storage_key, key))
        if panel is self.scurve_panel and key == "vmax" and previous_auto is None:
            return not current or current == panel.default_state.get("vmax", "2")
        return not current or current == previous_auto

    def _mark_project_common_values_as_linked(self):
        """프로젝트에서 불러온 공통값을 탭 사이에 계속 연동할 값으로 표시합니다.

        프로젝트를 불러온 직후 각 탭에 들어 있는 값은 같은 설계값의 복사본입니다.
        따라서 어느 한 탭에서 값을 수정한 뒤 이동하면, 아직 사용자가 따로 수정하지
        않은 다른 탭의 복사본만 최신값으로 바꿀 수 있도록 최초값을 기억합니다.
        """
        linked_fields = (
            (self.motor_panel, ("Q", "OB", "V")),
            (self.traction_panel, ("Q", "OB", "n")),
            (self.brake_panel, ("v",)),
            (self.criteria_panel, ("count", "rated")),
            (self.scurve_panel, ("vmax",)),
        )
        for panel, keys in linked_fields:
            for key in keys:
                entry = panel.entries.get(key)
                if entry is not None and entry.get().strip():
                    self._auto_filled_values[(panel.storage_key, key)] = entry.get().strip()

    def _apply_live_common_values(self, panel, common):
        planned = []
        def current_source(field):
            return (common.get("__sources__", {}).get(field) == common.get("__preferred__")
                    and common.get("__preferred__") is not None)
        if panel is self.motor_panel:
            for key in ("Q", "OB"):
                if key in common and self._can_auto_fill(panel, key, current_source(key)):
                    desired = clean_number_text(common[key])
                    if panel.entries[key].get().strip() != desired:
                        planned.append((key, desired))
            if "speed_m_s" in common and self._can_auto_fill(panel, "V", current_source("speed_m_s")):
                factor = 60 if panel.unit_vars["V"].get() == "m/min" else 1
                desired = clean_number_text(common["speed_m_s"] * factor)
                if panel.entries["V"].get().strip() != desired:
                    planned.append(("V", desired))
        elif panel is self.traction_panel:
            for key in ("Q", "OB"):
                if key in common and self._can_auto_fill(panel, key, current_source(key)):
                    desired = clean_number_text(common[key])
                    if panel.entries[key].get().strip() != desired:
                        planned.append((key, desired))
            if "rope_count" in common and self._can_auto_fill(panel, "n", current_source("rope_count")):
                desired = clean_number_text(common["rope_count"])
                if panel.entries["n"].get().strip() != desired:
                    planned.append(("n", desired))
        elif panel is self.brake_panel:
            if "speed_m_s" in common and self._can_auto_fill(panel, "v"):
                factor = 60 if panel.speed_unit.get() == "m/min" else 1
                desired = clean_number_text(common["speed_m_s"] * factor)
                if panel.entries["v"].get().strip() != desired:
                    planned.append(("v", desired))
        elif panel is self.criteria_panel:
            for field, key in (("rope_count", "count"), ("speed_m_s", "rated")):
                if field in common and self._can_auto_fill(panel, key, current_source(field)):
                    if key == "count" and panel.drive.get() != "권상식":
                        continue
                    desired = clean_number_text(common[field])
                    if panel.entries[key].get().strip() != desired:
                        planned.append((key, desired))
        elif panel is self.scurve_panel:
            if "speed_m_s" in common and self._can_auto_fill(panel, "vmax"):
                desired = clean_number_text(common["speed_m_s"])
                if panel.entries["vmax"].get().strip() != desired:
                    planned.append(("vmax", desired))

        if not planned:
            return []
        push_undo_state(panel)
        for key, text_value in planned:
            entry = panel.entries[key]
            entry.delete(0, tk.END)
            entry.insert(0, text_value)
            self._auto_filled_values[(panel.storage_key, key)] = text_value
        if isinstance(panel, tk.Widget):
            if panel is self.traction_panel:
                refresh_live_graphs(panel, 'traction')
            elif panel is self.traffic_panel:
                refresh_live_graphs(panel, 'traffic')
            elif panel is self.scurve_panel:
                refresh_live_graphs(panel, 'mechanical')
                refresh_live_graphs(panel, 'electrical')
        return [key for key, _value in planned]

    def on_tab_changed(self, _event=None):
        """탭 이동 시 의미와 단위가 같은 공통값만 다음 계산창으로 전달합니다."""
        self._tab_after_enter = None
        try:
            new_index = self.notebook.index(self.notebook.select())
            common = self._collect_live_common_values(self._last_tab_index)
            destinations = (*self.panels, self.criteria_panel, self.scurve_panel)
            filled = self._apply_live_common_values(destinations[new_index], common)
            self._last_tab_index = new_index
            if filled:
                labels = {"Q": "적재하중", "OB": "오버밸런스율", "V": "정격속도", "v": "속도",
                          "n": "로프 가닥 수", "count": "로프 가닥 수", "rated": "정격속도",
                          "vmax": "설정 최고속도"}
                if self.language == "en":
                    self._show_transfer_status(
                        "Auto-filled: " + ", ".join(ENGLISH_UI.get(labels[key], labels[key]) for key in filled)
                        + "  (existing user-edited values were preserved)"
                    )
                else:
                    self._show_transfer_status(
                        "자동 전달: " + ", ".join(labels[key] for key in filled)
                        + "  (직접 수정한 기존 값은 덮어쓰지 않음)"
                    )
        except (tk.TclError, IndexError, AttributeError) as error:
            # 탭 전환 보조 기능의 오류가 계산 자체를 막지 않도록 로그만 남깁니다.
            log_unexpected_error("탭 공통값 자동 전달", error)

    def _shortcut_theme(self, _event=None):
        self.toggle_theme()
        return "break"

    def toggle_always_on_top(self):
        self.always_on_top = not self.always_on_top
        self.root.attributes("-topmost", self.always_on_top)
        self.topmost_button.config(text="고정 해제" if self.always_on_top else "창 고정")
        self.store.set_always_on_top(self.always_on_top)
        self.apply_current_language()

    def show_shortcut_help(self, _event=None):
        if hasattr(self, "_shortcut_window") and self._shortcut_window.winfo_exists():
            self._shortcut_window.lift()
            self._shortcut_window.focus_force()
            return "break"
        english = self.language == "en"
        title = "Keyboard Shortcuts" if english else "키보드 단축키"
        shortcuts = [
            ("Ctrl+Enter", "Calculate current tab", "현재 탭 계산"),
            ("Space / Ctrl+Right", "Go to the next calculation tab", "다음 계산창으로 이동"),
            ("Ctrl+L", "Clear current-tab inputs", "현재 탭 입력값 삭제"),
            ("Ctrl+Z", "Undo last input change", "마지막 입력 변경 실행 취소"),
            ("Ctrl+H", "Open current-tab history", "현재 탭 입력 기록"),
            ("Ctrl+P", "Open project manager", "프로젝트 관리"),
            ("Ctrl+I", "Run integrated calculation", "통합계산 실행"),
            ("Alt+T", "Toggle light/dark mode", "라이트/다크 모드 전환"),
            ("F1", "Show this help", "이 도움말 열기"),
        ]
        window = tk.Toplevel(self.root)
        self._shortcut_window = window
        window.title(title)
        window.resizable(False, False)
        window.transient(self.root)
        center_child_window(window, self.root, 560, 545)
        window._ui_theme = self.ui_theme
        window._language = self.language
        tk.Label(
            window, text=title, font=("맑은 고딕", 15, "bold"), anchor="w"
        ).pack(fill="x", padx=20, pady=(18, 10))
        table = tk.Frame(window)
        table.pack(fill="both", expand=True, padx=20)
        for row, (key, description_en, description_ko) in enumerate(shortcuts):
            key_label = tk.Label(
                table, text=key, font=("맑은 고딕", 11, "bold"),
                width=13, anchor="w", padx=10, pady=8,
                highlightthickness=1,
            )
            key_label._theme_role = "header_1"
            key_label.grid(row=row, column=0, sticky="nsew")
            description = tk.Label(
                table, text=description_en if english else description_ko,
                font=("맑은 고딕", 11), anchor="w", padx=12, pady=8,
                highlightthickness=1,
            )
            description.grid(row=row, column=1, sticky="nsew")
        table.grid_columnconfigure(1, weight=1)
        SkyButton(
            window, text="Close" if english else "닫기", command=window.destroy, width=10
        ).pack(pady=(8, 16))
        apply_theme(window, self.ui_theme)
        apply_font_scale(window, self.font_size)
        return "break"

    @staticmethod
    def _state_number(state, key):
        return project_state_number(state, key)

    def _project_snapshot(self):
        """여섯 탭의 입력과 선택 상태를 저장 자료로 만든다."""
        states = {
            "motor": self.motor_panel.capture_state(),
            "traction": self.traction_panel.capture_state(),
            "brake": self.brake_panel.capture_state(),
            "traffic": self.traffic_panel.capture_state(),
            "criteria": self.criteria_panel.capture_state(),
            "scurve": self.scurve_panel.capture_state(),
        }
        active_key = ("motor", "traction", "brake", "traffic", "criteria", "scurve")[
            self.notebook.index(self.notebook.select())]
        return merge_project_states(states, active_key)

    def _synchronize_common_inputs(self):
        """현재 탭의 설계값을 변경 가능한 다른 탭에 전달한다."""
        active = self.notebook.index(self.notebook.select())
        common = self._collect_live_common_values(active)
        for index, panel in enumerate((*self.panels, self.criteria_panel, self.scurve_panel)):
            if index != active:
                self._apply_live_common_values(panel, common)

    def save_current_project(self, parent=None):
        parent = parent or self.root
        english = self.language == "en"
        info = app_ask_project_info(
            parent=parent,
            initial_manager=self.store.data.get("last_project_manager", ""),
        )
        if info is None:
            return False
        name, manager = info
        self._synchronize_common_inputs()
        states, common = self._project_snapshot()
        project = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "name": name, "manager": manager, "states": states, "common": common,
        }
        self.store.save_project(project)
        if self.store.save_warning:
            return False
        self.current_project_id = project["id"]
        messagebox.showinfo(
            "Project Saved" if english else "프로젝트 저장",
            (f"The project ‘{name}’ was saved with {manager} as the manager."
             if english else f"프로젝트 ‘{name}’을(를) 담당자 ‘{manager}’로 저장했습니다."),
            parent=parent
        )
        return True

    def apply_project(self, project, parent=None):
        # 이전 프로젝트의 자동입력 기준이 새 프로젝트에 섞이지 않도록 먼저 지웁니다.
        self._auto_filled_values.clear()
        states = project.get("states", {})
        loaded_panels = []
        project_name = project.get("name", "")
        for key, panel in (("motor", self.motor_panel), ("traction", self.traction_panel),
                           ("brake", self.brake_panel), ("traffic", self.traffic_panel),
                           ("criteria", self.criteria_panel), ("scurve", self.scurve_panel)):
            if isinstance(states.get(key), dict):
                panel.apply_state(states[key])
                loaded_panels.append(panel)
                if key in ("motor", "traction", "brake", "traffic"):
                    show_input_status(
                        panel,
                        f"Loaded inputs from project ‘{project_name}’."
                        if self.language == "en" else
                        f"프로젝트 ‘{project_name}’의 입력값을 불러왔습니다."
                    )
            elif key == "criteria":
                # 구버전 프로젝트에는 이 탭이 없으므로 현재 다른 프로젝트의 입력을 지웁니다.
                panel.apply_state({})
            elif key == "scurve":
                panel.apply_state(panel.default_state)
        if self.scurve_panel in loaded_panels and hasattr(self.scurve_panel,"calculate_energy"):
            self.scurve_panel.calculate_energy()
        # 불러온 공통 설계값은 서로 같은 값의 복사본이므로 이후 탭 이동 때 연동합니다.
        # 사용자가 특정 탭에서 직접 고친 값은 최초값과 달라져 자동으로 덮어쓰지 않습니다.
        self._mark_project_common_values_as_linked()
        self.current_project_id = project.get("id")

        # 프로젝트를 불러오면 사용자가 계산 버튼을 다시 누르지 않아도 즉시 결과를 표시합니다.
        # 불러오기 자체는 새 입력 작업이 아니므로 입력 기록에는 추가하지 않습니다.
        self.store._suppress_history = True
        try:
            for panel in loaded_panels:
                try:
                    panel.calculate()
                except Exception as error:
                    log_unexpected_error("프로젝트 불러오기 계산", error)
        finally:
            self.store._suppress_history = False

        if isinstance(self.traction_panel, tk.Widget):
            for panel, kind in ((self.traction_panel, 'traction'),
                                (self.traffic_panel, 'traffic'),
                                (self.scurve_panel, 'mechanical'),
                                (self.scurve_panel, 'electrical')):
                refresh_live_graphs(panel, kind)

        if parent:
            parent.destroy()

    def save_integrated_report(self, parent=None):
        """현재 여섯 탭의 입력과 화면 결과를 한 개의 UTF-8 텍스트 보고서로 저장합니다."""
        parent = parent or self.root
        english = self.language == "en"
        path = filedialog.asksaveasfilename(
            parent=parent,
            title="Save Integrated Calculation Report" if english else "통합 계산 보고서 저장",
            defaultextension=".txt",
            filetypes=[("Text Report" if english else "텍스트 보고서", "*.txt")]
        )
        if not path:
            return
        states, common = self._project_snapshot()
        names = ({"motor": "Motor Capacity", "traction": "Traction Ratio",
                  "brake": "Brake Deceleration", "traffic": "Traffic Analysis",
                  "criteria": "KC Clause Review", "scurve": "S-Curve Simulation"}
                 if english else
                 {"motor": "전동기 용량", "traction": "트랙션비",
                  "brake": "브레이크 제동", "traffic": "교통량 분석",
                  "criteria": "기준 검토", "scurve": "S-Curve 시뮬레이션"})
        panels = {"motor": self.motor_panel, "traction": self.traction_panel,
                  "brake": self.brake_panel, "traffic": self.traffic_panel,
                  "criteria": self.criteria_panel, "scurve": self.scurve_panel}

        def report_state(value):
            if isinstance(value, dict):
                return {key: report_state(item) for key, item in value.items()}
            if isinstance(value, list):
                return [report_state(item) for item in value]
            if english and isinstance(value, str):
                return CHOICE_EN.get(value, ENGLISH_UI.get(value, value))
            return value
        lines = (["Elevator Design Values and Performance Analysis Report",
                  f"Saved at: {datetime.now():%Y-%m-%d %H:%M:%S}",
                  f"Program build: {APP_BUILD}", f"Formula version: {FORMULA_VERSION}",
                  f"Shared values: {common}", ""] if english else
                 ["승강기 주요 설계값 계산 및 운행성능 분석 보고서",
                  f"저장 시각: {datetime.now():%Y-%m-%d %H:%M:%S}",
                  f"프로그램 빌드: {APP_BUILD}", f"계산식 버전: {FORMULA_VERSION}",
                  f"공통값: {common}", ""])
        for key in ("motor", "traction", "brake", "traffic", "criteria", "scurve"):
            lines.extend((f"[{names[key]}]",
                          (f"Input state: {report_state(states[key])}" if english else f"입력 상태: {states[key]}"),
                          self._panel_report_text(panels[key]), ""))
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8-sig")
            messagebox.showinfo(
                "Integrated Report" if english else "통합 보고서",
                "The current inputs and results were saved." if english else "현재 입력과 결과를 저장했습니다.",
                parent=parent)
        except OSError as error:
            messagebox.showerror("Report Save Error" if english else "통합 보고서 저장 오류", str(error), parent=parent)

    def open_project_manager(self):
        """프로젝트 관리 컨트롤러를 통해 관리창을 엽니다."""
        return self.project_manager.open()

    def _open_project_manager_impl(self):
        english = self.language == "en"
        window = tk.Toplevel(self.root)
        window.title("Elevator Projects" if english else "승강기 프로젝트")
        window.minsize(760, 500)
        window.resizable(True, True)
        window.transient(self.root)
        window._ui_theme = self.ui_theme
        window._language = self.language
        center_child_window(window, self.root, 960, 580)

        toolbar = tk.Frame(window)
        toolbar.pack(fill="x", padx=16, pady=(14, 8))
        heading_group = tk.Frame(toolbar)
        heading_group.pack(side="left", fill="x", expand=True)
        tk.Label(heading_group, text="Project Manager" if english else "프로젝트 관리",
                 font=("맑은 고딕", 15, "bold"), anchor="w").pack(fill="x")
        subtitle = tk.Label(
            heading_group,
            text=("Select one or more projects to load, rename, change manager, or delete."
                  if english else
                  "프로젝트를 하나 이상 선택해 불러오기·프로젝트명 변경·담당자 변경·삭제를 실행할 수 있습니다."),
            font=("맑은 고딕", 10), anchor="w",
        )
        subtitle._theme_role = "muted"
        subtitle.pack(fill="x", pady=(3, 0))

        def save_and_refresh():
            if self.save_current_project(window):
                refresh(self.current_project_id)

        SkyButton(toolbar, text="Save Current Inputs" if english else "현재 입력 새로 저장",
                  command=save_and_refresh, width=16,
                  font=("맑은 고딕", 10, "bold")).pack(side="right", padx=(10, 0))

        card_border = tk.Frame(window, bd=0)
        card_border._theme_role = "history_card_border"
        card_border.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        card = tk.Frame(card_border, bd=0)
        card._theme_role = "surface"
        card.pack(fill="both", expand=True, padx=2, pady=2)
        card_header = tk.Label(
            card, text="Saved Projects" if english else "저장된 프로젝트",
            font=("맑은 고딕", 11, "bold"), anchor="w", padx=12, pady=8,
        )
        card_header._theme_role = "header_1"
        card_header.pack(fill="x")
        project_table = tk.Frame(card)
        project_table.pack(fill="both", expand=True, padx=8, pady=8)
        project_list = ttk.Treeview(
            project_table,
            columns=("checked", "name", "manager", "saved_at", "formula"),
            show="headings", selectmode="extended", style="Project.Treeview"
        )
        project_list.heading("checked", text="Check" if english else "체크")
        project_list.heading("name", text="Project Name" if english else "프로젝트명")
        project_list.heading("manager", text="Manager" if english else "담당자")
        project_list.heading("saved_at", text="Saved At" if english else "저장 시각")
        project_list.heading("formula", text="Formula Version" if english else "계산식 버전")
        project_list.column("checked", width=62, minwidth=62, stretch=False, anchor="center")
        project_list.column("name", width=245, minwidth=150, anchor="w")
        project_list.column("manager", width=130, minwidth=100, stretch=False, anchor="center")
        project_list.column("saved_at", width=155, minwidth=130, stretch=False, anchor="center")
        project_list.column("formula", width=130, minwidth=110, stretch=False, anchor="center")
        project_scrollbar = ttk.Scrollbar(
            project_table, orient="vertical", command=project_list.yview
        )
        project_list.configure(yscrollcommand=project_scrollbar.set)
        project_scrollbar.pack(side="right", fill="y")
        project_list.pack(side="left", fill="both", expand=True)
        projects = []
        projects_by_row = {}
        checked_rows = set()

        def refresh(select_project_id=None):
            nonlocal projects, projects_by_row
            projects = list(reversed(self.store.projects()))
            projects_by_row = {}
            project_list.delete(*project_list.get_children())
            selected_row = None
            for index, item in enumerate(projects):
                row_id = f"project_{index}"
                projects_by_row[row_id] = item
                project_list.insert(
                    "", "end", iid=row_id,
                    values=("□", item.get("name", "Unnamed" if english else "이름 없음"),
                            item.get("manager") or ("Unassigned" if english else "미지정"),
                            item.get("saved_at", ""),
                            item.get("__formula_version__", "Earlier Version" if english else "이전 버전")),
                    tags=("even" if index % 2 == 0 else "odd",),
                )
                if item.get("id") == select_project_id:
                    selected_row = row_id
            # 새로고침 뒤에도 체크 상태는 프로젝트 ID 기준으로 복원합니다.
            valid_ids = {item.get("id") for item in projects}
            checked_rows.intersection_update(valid_ids)
            for row_id, item in projects_by_row.items():
                values = list(project_list.item(row_id, "values"))
                values[0] = "☑" if item.get("id") in checked_rows else "□"
                project_list.item(row_id, values=values)
            if selected_row:
                project_list.focus(selected_row)
                project_list.see(selected_row)

        def update_checkmark(_event=None):
            """체크 상태를 실제 체크박스 모양으로 표시합니다."""
            for row_id, item in projects_by_row.items():
                values = list(project_list.item(row_id, "values"))
                if values:
                    values[0] = "☑" if item.get("id") in checked_rows else "□"
                    project_list.item(row_id, values=values)

        drag_state = {"active": False, "target": True, "visited": set(), "moved": False}

        def _set_row_checked(row_id, checked):
            if not row_id or row_id not in projects_by_row:
                return
            project_id = projects_by_row[row_id].get("id")
            if checked:
                checked_rows.add(project_id)
            else:
                checked_rows.discard(project_id)

        def project_press(event):
            """체크칸뿐 아니라 프로젝트 행의 어느 위치를 눌러도 선택을 시작합니다."""
            row_id = project_list.identify_row(event.y)
            if not row_id:
                return "break"
            project_id = projects_by_row[row_id].get("id")
            drag_state["active"] = True
            drag_state["target"] = project_id not in checked_rows
            drag_state["visited"] = {row_id}
            drag_state["moved"] = False
            _set_row_checked(row_id, drag_state["target"])
            project_list.focus(row_id)
            project_list.see(row_id)
            update_checkmark()
            return "break"

        def project_drag(event):
            """마우스를 누른 채 위/아래로 훑으면 지나간 프로젝트를 연속 선택/해제합니다."""
            if not drag_state["active"]:
                return "break"
            row_id = project_list.identify_row(event.y)
            if row_id and row_id in projects_by_row and row_id not in drag_state["visited"]:
                drag_state["visited"].add(row_id)
                drag_state["moved"] = True
                _set_row_checked(row_id, drag_state["target"])
                project_list.see(row_id)
                update_checkmark()
            return "break"

        def project_release(event):
            drag_state["active"] = False
            drag_state["visited"].clear()
            return "break"

        def selected_projects():
            """체크박스가 켜진 프로젝트를 화면 순서대로 반환합니다."""
            return [item for row_id, item in projects_by_row.items()
                    if item.get("id") in checked_rows]

        def selected_one(action_name):
            """불러오기·이름 변경·담당자 변경처럼 대상 하나가 필요한 작업을 검사합니다."""
            items = selected_projects()
            if not items:
                messagebox.showinfo(
                    "Projects" if english else "프로젝트",
                    "Click anywhere on a project row to select it." if english else "프로젝트 줄의 아무 곳이나 눌러 선택해주세요.",
                    parent=window
                )
                return None
            if len(items) > 1:
                messagebox.showinfo(
                    "Projects" if english else "프로젝트",
                    (f"Select exactly one project to {action_name}." if english else
                     f"{action_name}할 프로젝트 하나만 선택해주세요."),
                    parent=window
                )
                return None
            return items[0]

        def load_selected():
            item = selected_one("load" if english else "불러오기")
            if item:
                self.apply_project(item, window)

        def delete_selected():
            items = selected_projects()
            if not items:
                messagebox.showinfo(
                    "Projects" if english else "프로젝트",
                    "Select at least one project to delete." if english else "삭제할 프로젝트를 하나 이상 선택해주세요.", parent=window
                )
                return
            if len(items) == 1:
                question = (f"Delete ‘{items[0].get('name')}’?" if english else
                            f"‘{items[0].get('name')}’을 삭제할까요?")
            else:
                question = (f"Delete all {len(items)} selected projects?" if english else
                            f"선택한 프로젝트 {len(items)}개를 모두 삭제할까요?")
            if messagebox.askyesno("Delete Projects" if english else "프로젝트 삭제", question, parent=window):
                self.store.delete_projects(item.get("id") for item in items)
                refresh()

        def rename_selected():
            item = selected_one("rename" if english else "프로젝트명 변경")
            if not item:
                return
            name = app_ask_string("Project Name" if english else "프로젝트 이름",
                                  "Enter a new name." if english else "새 이름을 입력하세요.",
                                  initialvalue=item.get("name", ""), parent=window)
            if name is not None and name.strip():
                self.store.rename_project(item.get("id"), name)
                refresh(item.get("id"))

        def change_manager_selected():
            items = selected_projects()
            if not items:
                messagebox.showinfo(
                    "Projects" if english else "프로젝트",
                    "Select one or more project rows." if english else
                    "담당자를 변경할 프로젝트를 하나 이상 선택해주세요.", parent=window)
                return
            initial_manager = items[0].get("manager", "") if len(items) == 1 else ""
            manager = app_ask_string(
                "Project Manager" if english else "프로젝트 담당자",
                (f"Enter the manager to apply to all {len(items)} selected projects." if english else
                 f"선택한 프로젝트 {len(items)}개에 적용할 새 담당자 이름을 입력하세요."),
                initialvalue=initial_manager, parent=window,
            )
            if manager is None:
                return
            manager = manager.strip()
            if not manager:
                messagebox.showwarning(
                    "Project Manager" if english else "프로젝트 담당자",
                    "Enter a manager name." if english else "담당자 이름을 입력해주세요.", parent=window)
                return
            for item in items:
                self.store.change_project_manager(item.get("id"), manager)
            refresh()
            messagebox.showinfo(
                "Manager Changed" if english else "담당자 변경 완료",
                (f"Updated {len(items)} project(s)." if english else
                 f"선택한 프로젝트 {len(items)}개의 담당자를 ‘{manager}’(으)로 변경했습니다."), parent=window)

        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=16, pady=(0, 14))
        SkyButton(buttons, text="Load Selected Project" if english else "선택 프로젝트 불러오기", command=load_selected, width=17).pack(side="left")
        SkyButton(buttons, text="Rename Project" if english else "프로젝트명 변경", command=rename_selected, width=14).pack(side="right", padx=(6, 0))
        SkyButton(buttons, text="Change Manager" if english else "담당자 변경", command=change_manager_selected, width=13).pack(side="right", padx=(6, 0))
        SkyButton(buttons, text="Delete" if english else "삭제", command=delete_selected, width=8).pack(side="right")
        project_list.bind("<ButtonPress-1>", project_press)
        project_list.bind("<B1-Motion>", project_drag)
        project_list.bind("<ButtonRelease-1>", project_release)
        row_colors = (("#ffffff", "#eef5fa") if self.ui_theme == "light" else
                      ("#07131d", "#0b2233"))
        project_list.tag_configure("even", background=row_colors[0])
        project_list.tag_configure("odd", background=row_colors[1])
        refresh()
        apply_theme(window, self.ui_theme)
        apply_font_scale(window, self.font_size)
        apply_language(window, self.language)

    def _install_motor_secondary_speed(self):
        panel = self.motor_panel
        speed_entry = panel.entries.get("V")
        if speed_entry is None:
            return
        row = getattr(panel, "entry_rows", {}).get("V")
        if row is None:
            return
        label = tk.Label(row, text="", font=("맑은 고딕", 9), bg="white")
        label._theme_role = "muted"
        label.pack(side="left", padx=(8, 0))
        panel._secondary_speed_label = label
        def refresh(_event=None):
            raw = speed_entry.get().strip()
            if not raw:
                label.config(text="")
                return
            try:
                value = parse_number(raw, "정격속도")
                unit = panel.unit_vars["V"].get()
                if unit == "m/s":
                    label.config(text=f"= {value * 60:.2f} m/min")
                else:
                    label.config(text=f"= {value / 60:.3f} m/s")
            except Exception:
                label.config(text="")
        speed_entry.bind("<KeyRelease>", refresh, add="+")
        panel.target_combo.bind("<<ComboboxSelected>>", lambda _e: self.root.after_idle(refresh), add="+")
        refresh()

    def apply_current_theme(self):
        """선택한 테마를 메인 창과 열려 있는 설정 창에 적용합니다."""
        self.root._ui_theme = self.ui_theme
        configure_ttk_theme(self.root, self.ui_theme)
        apply_theme(self.root, self.ui_theme)
        self.scurve_panel.redraw_plot()
        self.scurve_panel.redraw_energy_plot()
        self.apply_font_size(self.font_size)
        self.apply_current_language()
        self.header_controls.lift()

    def toggle_theme(self):
        """라이트 모드와 다크 모드를 즉시 전환합니다."""
        previous_mode = self.ui_theme
        self.ui_theme = "dark" if self.ui_theme == "light" else "light"
        try:
            self.apply_current_theme()
            self.store.set_theme(self.ui_theme)
        except Exception as error:
            # 예상하지 못한 환경 차이가 있어도 계산 프로그램 자체는 종료하지 않습니다.
            log_unexpected_error("화면 모드 변경", error)
            self.ui_theme = previous_mode
            self.root._ui_theme = previous_mode
            self.apply_current_language()
            messagebox.showerror(
                "Theme Change Error" if self.language == "en" else "화면 모드 변경 오류",
                (f"Could not change the theme.\n{error}" if self.language == "en" else
                 f"화면 모드를 변경하지 못했습니다.\n{error}"))


def enable_windows_dpi_awareness():
    """Tk를 생성하기 전에 DPI 인식을 활성화한다. 다른 OS는 변경하지 않는다."""
    if sys.platform != "win32":
        return False
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return True
    except (AttributeError, OSError):
        return False


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_calculation_self_tests()
        assert evaluate_rope_clause('traction','rope',3,7,160000,10000)['limit'] == 16
        assert evaluate_traction_case('stationary',150,100,.2,3.14)['comparison'] == '≥'
        assert evaluate_traction_case('load',150,100,.2,3.14)['comparison'] == '≤'
        assert evaluate_rope_clause('traction','rope',3,8,120000,10000)['status'] == 'COMPLIANT'
        assert evaluate_rope_clause('traction','rope',2,8,120000,10000)['status'] == 'NONCOMPLIANT'
        assert evaluate_rope_clause('traction','rope',3,None,120000,10000)['status'] == 'INDETERMINATE'
        assert evaluate_actual_speed(2,2.1,True,True,True)['margin_percentage_points'] == 0
        assert evaluate_actual_speed(2,2.1,False,True,True)['status'] == 'INDETERMINATE'
        assert evaluate_brake_evidence(True,True,None,True)['status'] == 'INDETERMINATE'
        assert abs(scurve_profile(30,2,1,.8,1500)['samples'][-1][1]-30) < 1e-7
        print(f"자동검사 통과: 빌드 {APP_BUILD}, 계산식 {FORMULA_VERSION}")
        raise SystemExit(0)

    enable_windows_dpi_awareness()
    root = tk.Tk()
    set_dialog_root(root)
    try:
        app = ElevatorApp(root)
    except Exception as error:
        # 더블클릭 실행 시 콘솔이 바로 닫혀도 원인을 확인할 수 있게 표시합니다.
        log_unexpected_error("프로그램 시작", error)
        startup_english = getattr(root, "_language", "ko") == "en"
        messagebox.showerror(
            "Program Startup Error" if startup_english else "프로그램 실행 오류",
            (f"An error occurred while creating the program window.\n{type(error).__name__}: {error}"
             if startup_english else
             f"프로그램 화면을 만드는 중 오류가 발생했습니다.\n{type(error).__name__}: {error}"),
            parent=root,
        )
        root.destroy()
    else:
        root.mainloop()
