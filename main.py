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

import copy
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
from assets import FORMULA_IMAGE_DATA, FORMULA_TEXT_EN
from app_config import APP_BUILD, FORMULA_VERSION, BUTTON_BG, BUTTON_ACTIVE_BG, BUTTON_TEXT
from theme_manager import (THEMES, get_theme, apply_theme, style_combobox_popdown,
                           bind_combobox_popdown_theme, configure_ttk_theme, apply_font_scale)
from ui_components import (SkyButton, WindowManager, center_child_window,
                           app_ask_string, app_ask_project_info, messagebox, set_dialog_root,
                           attach_numeric_validation)
from storage import (PersistentStore, get_data_file_path, normalize_record,
                     CALCULATOR_KEYS, MAX_HISTORY_PER_CALCULATOR)
from utils import (clean_number_text, parse_number, ensure_positive,
                   calculate_safely, require_calculation)
from calculators import (
    calculate_motor_value, calculate_traction_values, calculate_brake_values,
    calculate_traffic_values, traffic_pdf_reference, traffic_visible_input_fields,
    run_calculation_self_tests,
)
from simulation_plot import draw_scurve_plot, draw_energy_comparison
from energy_model import compare_trips, read_measurement
from background_jobs import calculate_snapshot


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


def focus_input_for_replacement(entry):
    """Tab으로 이동한 숫자칸의 기존 값을 바로 덮어쓸 수 있게 선택한다."""
    entry.focus_set()
    entry.selection_range(0, tk.END)
    entry.icursor(tk.END)


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


def create_result_display(parent):
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
        font=("맑은 고딕", 9), width=10
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
class SolverPanel(tk.Frame):
    def __init__(self, parent, vars_spec, formulas, note, store, storage_key,
                 input_validator=None, result_validator=None, formula_key=None):
        """
        vars_spec : 화면에 표시할 변수의 이름, 단위, % 여부를 저장한 목록
        formulas  : 사용자가 선택한 '구하고자 하는 값'별 계산식

        예를 들어 전동기 용량 P를 선택하면 P 입력칸은 잠기고,
        나머지 Q, V, OB, 효율을 입력하여 P를 계산하는 방식입니다.
        % 값은 계산 직전에 100으로 나누어 45%를 0.45로 바꿉니다.
        """
        super().__init__(parent, bg="white")
        self.vars_spec = vars_spec
        self.formulas = formulas
        self.store = store
        self.storage_key = storage_key
        self.input_validator = input_validator
        self.result_validator = result_validator
        self.entries = {}
        self.entry_rows = {}
        self.unit_vars = {}
        self._last_units = {}
        self.undo_stack = []
        self.input_history = self.store.history(self.storage_key)
        self.previous_values = self.store.previous(self.storage_key)

        # 공식·단위 안내는 입력 박스 위, 입력과 결과는 공통 규격의 좌우 박스에 둡니다.
        self.input_area, result_area = create_calculation_layout(
            self, note, formula_key=formula_key
        )

        top = tk.Frame(self.input_area, bg="white")
        top.pack(anchor="w", pady=(12, 6), padx=10)
        tk.Label(top, text="구하고자 하는 값 :", font=("맑은 고딕", 11, "bold"),
                 bg="white").pack(side="left")

        self.target_combo = ttk.Combobox(
            top, values=[v["label"] for v in vars_spec],
            state="readonly", width=22, font=("맑은 고딕", 11)
        )
        self.target_combo.current(0)
        self.target_combo.pack(side="left", padx=10)
        self.target_combo.bind("<<ComboboxSelected>>", self.on_target_change)

        self.form = tk.Frame(self.input_area, bg="white")
        self.form.pack(anchor="w", padx=10, pady=4)
        for v in vars_spec:
            row = tk.Frame(self.form, bg="white")
            row.pack(anchor="w", pady=3)
            tk.Label(row, text=v["label"], font=("맑은 고딕", 10), bg="white",
                     width=18, anchor="w").pack(side="left")
            entry = tk.Entry(row, font=("맑은 고딕", 10), width=16, justify="right")
            attach_numeric_validation(entry)
            entry.pack(side="left", padx=5)
            entry.bind("<Return>", lambda _event: self.calculate())
            if v.get("unit_factors"):
                default_unit = v.get("default_unit") or next(iter(v["unit_factors"]))
                unit_var = tk.StringVar(value=default_unit)
                unit_combo = ttk.Combobox(
                    row, textvariable=unit_var, values=list(v["unit_factors"]),
                    state="readonly", width=7, font=("맑은 고딕", 9)
                )
                unit_combo.pack(side="left")
                unit_combo.bind(
                    "<<ComboboxSelected>>",
                    lambda _event, key=v["key"]: self.on_unit_change(key)
                )
                self.unit_vars[v["key"]] = unit_var
                self._last_units[v["key"]] = default_unit
            else:
                unit_text = "%" if v.get("percent") else v.get("unit", "")
                tk.Label(row, text=unit_text, font=("맑은 고딕", 10), bg="white").pack(side="left")
            self.entries[v["key"]] = entry
            self.entry_rows[v["key"]] = row

        action_buttons = create_action_buttons(
            self.input_area, self.calculate,
            [
                ("clear", "입력값 삭제", self.clear, "normal"),
                ("previous", "이전 입력값", self.restore_previous, "disabled"),
                ("history", "입력 기록", self.show_history, "disabled"),
            ]
        )
        self.action_buttons = action_buttons
        self.previous_button = action_buttons["previous"]
        self.history_button = action_buttons["history"]
        if self.previous_values:
            self.previous_button.config(state="normal")
        if self.input_history:
            self.history_button.config(state="normal")

        self.initial_result_message = INITIAL_RESULT_MESSAGE
        self.result_text = create_result_display(result_area)
        self._show(initial_result_text(self))

        self.on_target_change()

    def _target_key(self):
        idx = self.target_combo.current()
        return self.vars_spec[idx]["key"]

    def _show(self, text, error=False):
        """전동기 결과와 오류를 공통 결과창 형식으로 표시합니다."""
        set_result_display(self.result_text, text, error)

    def on_unit_change(self, key):
        """한 입력칸에서 단위를 바꾸면 현재 숫자도 같은 물리량으로 변환합니다."""
        push_undo_state(self)
        spec = next(item for item in self.vars_spec if item["key"] == key)
        old_unit = self._last_units.get(key, self.unit_vars[key].get())
        new_unit = self.unit_vars[key].get()
        entry = self.entries[key]
        raw = entry.get().strip()
        if raw:
            try:
                value = parse_number(raw, spec["label"])
                base_value = value * spec["unit_factors"][old_unit]
                converted = base_value / spec["unit_factors"][new_unit]
                state = str(entry.cget("state"))
                entry.config(state="normal")
                entry.delete(0, tk.END)
                entry.insert(0, f"{converted:.10g}")
                if state == "disabled":
                    entry.config(state="disabled")
            except ValueError as error:
                self._show("Input error: Check the value and selected unit."
                           if widget_language(self) == "en" else f"입력 오류: {error}", error=True)
        self._last_units[key] = new_unit

    def on_target_change(self, event=None):
        # 목표 항목을 바꾸기 전에 현재 값을 모두 보관합니다.
        # 예: P를 계산한 뒤 목표를 Q로 바꾸면, 방금 구한 P는 다음 역산에
        # 그대로 사용할 수 있어야 하므로 새 목표인 Q만 비웁니다.
        if event is not None:
            push_undo_state(self)
        current_values = {key: entry.get() for key, entry in self.entries.items()}

        # 새로 구할 값의 입력칸만 비우고 회색으로 잠급니다.
        # 나머지 입력칸은 기존 값을 다시 넣어 확실하게 유지합니다.
        target_key = self._target_key()
        # 스마트 입력 UI: 현재 구하려는 값은 입력 대상이 아니므로 해당 행을 숨기고
        # 실제로 필요한 입력값만 표시합니다. 계산값은 결과 영역에 표시됩니다.
        for key, row in getattr(self, "entry_rows", {}).items():
            if key == target_key:
                row.pack_forget()
            elif not row.winfo_manager():
                row.pack(anchor="w", pady=3)
        for key, entry in self.entries.items():
            entry.config(state="normal")
            if key == target_key:
                entry.delete(0, tk.END)
                _mode, colors = get_theme(entry)
                entry.config(state="disabled", disabledbackground=colors["disabled_entry"])
            else:
                entry.delete(0, tk.END)
                entry.insert(0, current_values[key])
        # 전동기 속도처럼 서로 연결된 보조 입력칸이 있으면 함께 갱신합니다.
        sync = getattr(self, "sync_speed_display", None)
        if sync:
            sync()
        # 아래 결과 표시는 '입력값 삭제'를 누르기 전까지 유지합니다.
        # 어떤 값을 방금 계산했는지 확인하면서 다음 역산을 할 수 있습니다.

    def calculate(self):
        # 잠긴 목표값을 제외한 나머지 입력값을 읽어 선택된 공식을 실행합니다.
        target_key = self._target_key()
        target_spec = next(v for v in self.vars_spec if v["key"] == target_key)
        try:
            prepare = getattr(self, "prepare_calculation", None)
            if prepare:
                prepare()
            sync = getattr(self, "sync_speed_display", None)
            if sync:
                sync()
            vals = {}
            for v in self.vars_spec:
                key = v["key"]
                if key == target_key:
                    continue
                raw = self.entries[key].get().strip()
                if raw == "":
                    raise ValueError(f"'{v['label']}' 값을 입력해주세요.")
                num = parse_number(raw, v["label"])
                if v.get("unit_factors"):
                    num *= v["unit_factors"][self.unit_vars[key].get()]
                if v.get("percent"):
                    num = num / 100.0
                vals[key] = num

            if self.input_validator:
                self.input_validator(vals, target_key)

            result = require_calculation(calculate_safely(self.formulas[target_key], vals))
            if not math.isfinite(result):
                raise ValueError("계산 결과가 유한한 숫자가 아닙니다. 입력값을 확인하세요.")
            if self.result_validator:
                self.result_validator(result, target_key)
            display_val = result * 100 if target_spec.get("percent") else result
            if target_spec.get("unit_factors"):
                display_val = result / target_spec["unit_factors"][self.unit_vars[target_key].get()]

            # 계산 결과를 목표 입력칸에 쓰기 직전 상태를 보관해 Ctrl+Z로 되돌립니다.
            push_undo_state(self)
            entry = self.entries[target_key]
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, f"{display_val:.4f}")
            entry.config(state="disabled")
            if sync:
                sync()

            unit = (self.unit_vars[target_key].get() if target_spec.get("unit_factors") else
                    ("%" if target_spec.get("percent") else target_spec.get("unit", "")))
            english = widget_language(self) == "en"
            target_label = ENGLISH_UI.get(target_spec["label"], target_spec["label"]) \
                if english else target_spec["label"]
            result_summary = f"{target_label} = {display_val:.4f} {unit}".strip()
            # 계산이 끝난 뒤에만 전체 기록에 추가합니다.
            self._remember_input(target_key, target_spec["label"], result_summary)
            used_values = []
            for spec in self.vars_spec:
                if spec["key"] == target_key:
                    continue
                used_unit = (self.unit_vars[spec["key"]].get() if spec.get("unit_factors") else
                             ("%" if spec.get("percent") else spec.get("unit", "")))
                used_label = ENGLISH_UI.get(spec["label"], spec["label"]) \
                    if english else spec["label"]
                used_values.append(
                    f"- {used_label} = {self.entries[spec['key']].get()} {used_unit}".rstrip()
                )
            process_lines = []
            if self.storage_key == "motor":
                formula_map_ko = {
                    "P": "P = [Q × V × (1-OB)] / (6120 × η)",
                    "Q": "Q = P × 6120 × η / [V × (1-OB)]",
                    "V": "V = P × 6120 × η / [Q × (1-OB)]",
                    "eff": "η = Q × V × (1-OB) / (6120 × P)",
                    "OB": "OB = 1 - (P × 6120 × η) / (Q × V)",
                }
                process_lines = [
                    "", "[Calculation Process]" if english else "[계산 과정]",
                    ("1. Check the entered values and units." if english else "1. 입력값과 단위를 확인합니다."),
                    ("2. Convert speed to the formula base unit (m/min)." if english else "2. 속도를 계산식 기준 단위(m/min)로 통일합니다."),
                    ("3. Apply formula: " if english else "3. 공식 적용: ") + formula_map_ko.get(target_key, ""),
                    ("4. Calculate and round the display value to four decimals." if english else "4. 계산 후 표시값을 소수 넷째 자리까지 정리합니다."),
                ]
            displayed = (f"▶ {result_summary}\n\n[Inputs Used]\n" if english else
                         f"▶ {result_summary}\n\n[계산에 사용한 입력값]\n")
            displayed += "\n".join(used_values + process_lines)
            self._show(displayed)
        except ZeroDivisionError:
            self._show("Error: Division by zero. Check the inputs." if widget_language(self) == "en"
                       else "오류: 0으로 나누는 값이 있습니다. 입력값을 확인하세요.", error=True)
        except ValueError as e:
            self._show("Input error: Check all required values, units, and percentage ranges."
                       if widget_language(self) == "en" else f"오류: {e}", error=True)
        except Exception as e:
            if widget_language(self) == "en":
                log_unexpected_error("Motor capacity calculation", e)
                self._show("Unexpected calculation error. Check the error log.", error=True)
            else:
                show_unexpected_error(self, "전동기 용량 계산", e)

    def _remember_input(self, target_key, target_label, result_summary):
        record = {"__target_key__": target_key, "__target_label__": target_label,
                  "__units__": {key: var.get() for key, var in self.unit_vars.items()}}
        for key, entry in self.entries.items():
            record[key] = "" if key == target_key else entry.get()
        self.input_history = self.store.add_history(
            self.storage_key, record, result_summary
        )
        self.previous_values = self.store.previous(self.storage_key)
        self.previous_button.config(state="normal")
        self.history_button.config(state="normal")

    def restore_previous(self):
        """가장 최근에 계산하거나 삭제하기 전에 입력했던 값을 복원합니다."""
        if self.previous_values is None:
            return
        push_undo_state(self)
        self._apply_record(self.previous_values)
        self._show("Previous inputs loaded. Check the values, then calculate."
                   if widget_language(self) == "en" else
                   "이전 입력값을 불러왔습니다. 값을 확인한 뒤 계산하세요.")

    def show_history(self):
        specs = [("__target_label__", "구한 값", 140)]
        specs.extend((v["key"], v["label"], 110) for v in self.vars_spec)
        open_history_window(self, "전동기 용량 입력 기록", self.input_history,
                            specs, self._load_history_record,
                            self._delete_history_record, self._clear_history,
                            self._rename_history_record)

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
        push_undo_state(self)
        self._apply_record(record)
        clean_record = {
            key: value for key, value in record.items()
            if key not in ("__saved_at__", "__result_summary__")
        }
        self.store.set_previous(self.storage_key, clean_record)
        self.previous_values = self.store.previous(self.storage_key)
        self.previous_button.config(state="normal")
        self._show((f"Input record {record_number} loaded. Check the values, then calculate."
                    if widget_language(self) == "en" else
                    f"입력 기록 {record_number}번을 불러왔습니다. 값을 확인한 뒤 계산하세요."))

    def _apply_record(self, record):
        """이전 값과 입력 기록이 같은 방식으로 입력칸에 적용되게 합니다."""
        for key, unit in record.get("__units__", {}).items():
            if key in self.unit_vars and unit in next(
                item["unit_factors"] for item in self.vars_spec if item["key"] == key
            ):
                self.unit_vars[key].set(unit)
                self._last_units[key] = unit
        target_key = record["__target_key__"]
        target_index = next(i for i, spec in enumerate(self.vars_spec)
                            if spec["key"] == target_key)
        self.target_combo.current(target_index)
        self.on_target_change()
        for key, entry in self.entries.items():
            if key != target_key:
                entry.delete(0, tk.END)
                entry.insert(0, record.get(key, ""))
        sync = getattr(self, "sync_speed_display", None)
        if sync:
            sync()

    def clear(self):
        push_undo_state(self)
        target_key = self._target_key()
        current = {
            "__target_key__": target_key,
            "__target_label__": next(v["label"] for v in self.vars_spec
                                      if v["key"] == target_key),
        }
        for key, entry in self.entries.items():
            current[key] = "" if key == target_key else entry.get()
        if any(current[key].strip() for key in self.entries if key != target_key):
            self.store.set_previous(self.storage_key, current)
            self.previous_values = self.store.previous(self.storage_key)
            self.previous_button.config(state="normal")

        for key, entry in self.entries.items():
            entry.config(state="normal")
            entry.delete(0, tk.END)
            if key == target_key:
                _mode, colors = get_theme(entry)
                entry.config(state="disabled", disabledbackground=colors["disabled_entry"])
        self._show(initial_result_text(self))
        for key, entry in self.entries.items():
            if key != target_key:
                entry.focus_set()
                break
        sync = getattr(self, "sync_speed_display", None)
        if sync:
            sync()

    def capture_state(self):
        return {
            "target": self._target_key(),
            "values": {key: entry.get() for key, entry in self.entries.items()},
            "units": {key: var.get() for key, var in self.unit_vars.items()},
        }

    def apply_state(self, state, remember_undo=True):
        if remember_undo:
            push_undo_state(self)
        for key, unit in state.get("units", {}).items():
            if key in self.unit_vars:
                self.unit_vars[key].set(unit)
                self._last_units[key] = unit
        target = state.get("target", self._target_key())
        target_index = next((i for i, spec in enumerate(self.vars_spec)
                             if spec["key"] == target), 0)
        self.target_combo.current(target_index)
        for key, entry in self.entries.items():
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, state.get("values", {}).get(key, ""))
            if key == target:
                _mode, colors = get_theme(entry)
                entry.config(state="disabled", disabledbackground=colors["disabled_entry"])

    def undo_last(self):
        undo_panel(self)


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
        validate_motor_values, validate_motor_result, formula_key="motor"
    )
    notebook.add(panel, text="전동기 용량")
    return panel


# ===================================================================
# 탭 2. 트랙션비 통합 계산
# ===================================================================
def build_traction_tab(notebook, store):
    """중간 단계 탭 없이 트랙션비 통합 계산 화면을 바로 표시합니다."""
    panel = IntegratedTractionPanel(notebook, store)
    notebook.add(panel, text="트랙션비 계산")
    return panel


class IntegratedTractionPanel(tk.Frame):
    """문제에서 주어진 값만 한 번 입력하는 트랙션비 통합 계산 화면.

    계산 순서:
    입력값 → 균형추 중량 → 로프 총중량 → 전반부/후반부 트랙션비
    → 둘 중 큰 값을 최종 트랙션비로 선택
    """
    def __init__(self, parent, store):
        super().__init__(parent, bg="white")
        self.store = store
        self.storage_key = "traction"

        note = ("문제에서 주어진 값만 입력하면 균형추·로프·전반부·후반부·최종 트랙션비를 한 번에 계산합니다.\n"
                "※ 문제에 값이 없으면 보상체인 중량과 이동케이블 중량은 0으로 입력합니다.")
        left, right = create_calculation_layout(self, note, formula_key="traction")
        self.input_area = left

        fields = [
            ("Q", "적재하중 Q", "kg", ""),
            ("Wc", "카 자중 Wc", "kg", ""),
            ("H", "승강행정 H", "m", ""),
            ("wr", "로프 단위중량 wr", "kg/m", ""),
            ("n", "로프 가닥 수 n", "가닥", ""),
            ("OB", "오버밸런스율 OB", "%", ""),
            ("Wcomp", "보상체인 중량", "kg", "0"),
            ("Wm", "이동케이블 중량", "kg", "0"),
        ]
        self.entries = {}
        self.defaults = {}
        self.undo_stack = []
        # 가장 최근에 입력하거나 계산한 값은 프로그램을 종료해도 보관합니다.
        self.previous_values = self.store.previous(self.storage_key)
        # 이번 실행 중 사용한 입력값을 계산 순서대로 계속 쌓아두는 목록입니다.
        self.input_history = self.store.history(self.storage_key)
        for key, label, unit, default in fields:
            row = tk.Frame(left, bg="white")
            row.pack(anchor="w", pady=4)
            tk.Label(row, text=label, width=18, anchor="w", bg="white", font=("맑은 고딕", 10)).pack(side="left")
            entry = tk.Entry(row, width=13, font=("맑은 고딕", 10), justify="right")
            attach_numeric_validation(entry)
            entry.insert(0, default)
            entry.pack(side="left", padx=5)
            tk.Label(row, text=unit, width=6, anchor="w", bg="white", font=("맑은 고딕", 10)).pack(side="left")
            entry.bind("<Return>", lambda _event: self.calculate())
            self.entries[key] = entry
            self.defaults[key] = default

        action_buttons = create_action_buttons(
            left, self.calculate,
            [
                ("clear", "입력값 삭제", self.reset, "normal"),
                ("previous", "이전 입력값", self.restore_previous, "disabled"),
                ("history", "입력 기록", self.show_history, "disabled"),
            ]
        )
        self.action_buttons = action_buttons
        self.previous_button = action_buttons["previous"]
        self.history_button = action_buttons["history"]
        if self.previous_values:
            self.previous_button.config(state="normal")
        if self.input_history:
            self.history_button.config(state="normal")

        self.result_text = create_result_display(right)
        self._show(initial_result_text(self))

    def _show(self, text, error=False):
        set_result_display(self.result_text, text, error)

    def _remember(self, values, result_summary):
        """성공적으로 계산한 입력값만 영구 기록에 저장합니다."""
        self.input_history = self.store.add_history(
            self.storage_key, values, result_summary
        )
        self.previous_values = self.store.previous(self.storage_key)
        self.previous_button.config(state="normal")
        self.history_button.config(state="normal")

    def reset(self):
        push_undo_state(self)
        # 삭제 직전의 입력값을 저장합니다. 필수 입력칸이 전부 비어 있다면
        # 이미 기억 중인 값을 빈칸으로 덮어쓰지 않습니다.
        current = {key: entry.get() for key, entry in self.entries.items()}
        required_keys = ("Q", "Wc", "H", "wr", "n", "OB")
        if any(current[key].strip() for key in required_keys):
            # 삭제 직전 값은 '이전 입력값'으로만 보관하고 계산 기록에는 넣지 않습니다.
            self.store.set_previous(self.storage_key, current)
            self.previous_values = self.store.previous(self.storage_key)
            self.previous_button.config(state="normal")

        # 필수값은 빈칸으로, 문제에 없을 수 있는 선택항은 0으로 되돌립니다.
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, self.defaults[key])
        self._show(("Inputs cleared. Compensation-chain and traveling-cable weights default to 0.\n"
                    "Use Previous Inputs to restore the values from before clearing.")
                   if widget_language(self) == "en" else
                   "입력값을 삭제했습니다. 보상체인·이동케이블은 기본값 0입니다.\n"
                   "삭제 직전 값은 ‘이전 입력값’ 버튼으로 복원할 수 있습니다.")
        self.entries["Q"].focus_set()
        self.entries["Q"].selection_range(0, tk.END)

    def restore_previous(self):
        """가장 최근에 계산했거나 삭제하기 전에 입력했던 값을 복원합니다."""
        if self.previous_values is None:
            return
        push_undo_state(self)
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, self.previous_values.get(key, ""))
        self._show("Previous inputs loaded. Check the values, then calculate."
                   if widget_language(self) == "en" else
                   "이전 입력값을 불러왔습니다. 값을 확인한 뒤 계산하세요.")
        self.entries["Q"].focus_set()
        self.entries["Q"].selection_range(0, tk.END)

    def show_history(self):
        specs = [
            ("Q", "적재하중", 85), ("Wc", "카 자중", 85),
            ("H", "승강행정", 75), ("wr", "로프 단위중량", 105),
            ("n", "로프 수", 65), ("OB", "OB(%)", 70),
            ("Wcomp", "보상체인", 90), ("Wm", "이동케이블", 100),
        ]
        open_history_window(self, "트랙션비 입력 기록", self.input_history,
                            specs, self._load_history_record,
                            self._delete_history_record, self._clear_history,
                            self._rename_history_record)

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
        push_undo_state(self)
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, record.get(key, ""))
        clean_record = {key: record.get(key, "") for key in self.entries}
        self.store.set_previous(self.storage_key, clean_record)
        self.previous_values = self.store.previous(self.storage_key)
        self._show((f"Input record {record_number} loaded. Check the values, then calculate."
                    if widget_language(self) == "en" else
                    f"입력 기록 {record_number}번을 불러왔습니다. 값을 확인한 뒤 계산하세요."))
        self.entries["Q"].focus_set()
        self.entries["Q"].selection_range(0, tk.END)

    def capture_state(self):
        return {"values": {key: entry.get() for key, entry in self.entries.items()}}

    def apply_state(self, state, remember_undo=True):
        if remember_undo:
            push_undo_state(self)
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, state.get("values", {}).get(key, self.defaults.get(key, "")))

    def undo_last(self):
        undo_panel(self)

    def calculate(self):
        english = widget_language(self) == "en"
        try:
            labels = {"Q":"적재하중", "Wc":"카 자중", "H":"승강행정", "wr":"로프 단위중량",
                      "n":"로프 가닥 수", "OB":"오버밸런스율", "Wcomp":"보상체인 중량", "Wm":"이동케이블 중량"}
            v = {key: parse_number(entry.get(), labels[key]) for key, entry in self.entries.items()}
            for key in ("Q", "Wc", "H", "wr", "n"):
                ensure_positive(v[key], labels[key])
            ensure_positive(v["Wcomp"], labels["Wcomp"], allow_zero=True)
            ensure_positive(v["Wm"], labels["Wm"], allow_zero=True)
            if not 0 < v["OB"] < 100:
                raise ValueError("'오버밸런스율'은 0보다 크고 100보다 작은 % 값이어야 합니다.")
            if not v["n"].is_integer():
                raise ValueError("'로프 가닥 수'는 정수로 입력해주세요.")

            calculated = require_calculation(calculate_safely(calculate_traction_values, v))
            ob = calculated["ob"]
            wcw = calculated["wcw"]
            wr_total = calculated["rope_total"]
            tf = calculated["front"]
            tr = calculated["rear"]
            if not all(math.isfinite(value) for value in (wcw, wr_total, tf, tr)):
                raise ValueError("계산 결과의 숫자 범위가 너무 큽니다. 입력값을 확인하세요.")

            # 설계 검토에는 더 불리한 조건을 써야 하므로 큰 값을 최종값으로 선택합니다.
            final = calculated["final"]
            basis = calculated["basis"]
            english = widget_language(self) == "en"
            if english:
                basis_text = "Front ratio" if "전반" in basis else "Rear ratio"
                result = (
                    f"1. Counterweight Wcw = {wcw:,.4f} kg\n"
                    f"   = {v['Wc']:g} + {v['Q']:g} × {ob:g}\n\n"
                    f"2. Total rope weight Wr = {wr_total:,.4f} kg\n"
                    f"   = {v['H']:g} × {v['wr']:g} × {v['n']:g}\n\n"
                    f"3. Front traction ratio Tf = {tf:.4f}\n"
                    f"4. Rear traction ratio Tr = {tr:.4f}\n\n"
                    f"▶ Final traction ratio = {final:.4f}\n"
                    f"▶ Rounded to 2 decimals = {final:.2f}\n"
                    f"   ({basis_text} is larger)"
                )
            else:
                result = (
                    f"1. 균형추 중량 Wcw = {wcw:,.4f} kg\n"
                    f"   = {v['Wc']:g} + {v['Q']:g} × {ob:g}\n\n"
                    f"2. 로프 총중량 Wr = {wr_total:,.4f} kg\n"
                    f"   = {v['H']:g} × {v['wr']:g} × {v['n']:g}\n\n"
                    f"3. 전반부 트랙션비 Tf = {tf:.4f}\n"
                    f"4. 후반부 트랙션비 Tr = {tr:.4f}\n\n"
                    f"▶ 최종 트랙션비 = {final:.4f}\n"
                    f"▶ 소수점 둘째 자리까지 표시 = {final:.2f}\n"
                    f"   ({basis}가 더 큼)"
                )
            self._remember(
                {key: entry.get() for key, entry in self.entries.items()},
                (f"Final traction ratio = {final:.4f} ({final:.2f})" if english else
                 f"최종 트랙션비 = {final:.4f} ({final:.2f})")
            )
            self._show(result)
        except ZeroDivisionError:
            self._show("Error: A formula denominator is zero. Check the inputs."
                       if widget_language(self) == "en" else
                       "오류: 계산식의 분모가 0입니다. 입력값을 확인하세요.", error=True)
        except ValueError as e:
            self._show("Input error: Check required values, units, and valid ranges."
                       if widget_language(self) == "en" else f"입력 오류: {e}", error=True)
        except Exception as e:
            if widget_language(self) == "en":
                log_unexpected_error("Traction ratio calculation", e)
                self._show("Unexpected calculation error. Check the error log.", error=True)
            else:
                show_unexpected_error(self, "트랙션비 계산", e)


# ===================================================================
# 탭 3. 브레이크 제동 계산
#   d = v x t / 2 ,  t = 2d / v ,  v = 2d / t ,  a = v / t
#   (d,t 주어짐) -> v = 2d/t , a = 2d/t^2
#   (v,a 주어짐) -> t = v/a , d = v^2/(2a)
# ===================================================================
class BrakePanel(tk.Frame):
    """네 물리량 중 사용자가 입력한 두 값을 찾아 나머지 두 값을 계산합니다.

    계산 결과를 입력칸에 다시 쓰지 않고 결과 영역에만 표시하여,
    이전 계산 결과가 다음 계산의 입력값으로 잘못 사용되는 것을 방지합니다.
    """
    def __init__(self, parent, store):
        super().__init__(parent, bg="white")
        self.store = store
        self.storage_key = "brake"

        note = ("속도(v), 제동시간(t), 제동거리(d), 감속도(a) 중 알고 있는 값 2개 이상을 입력하세요.\n"
                "※ 일정한 감속도로 정지한다고 가정합니다. 3개 이상 입력하면 공식 일치 여부도 검사합니다.\n"
                "※ 속도 단위는 입력칸 옆에서 m/s 또는 m/min을 선택할 수 있습니다.")
        left, right = create_calculation_layout(self, note, formula_key="brake")
        self.input_area = left

        fields = [("v", "속도 v", "m/s"), ("t", "제동시간 t", "s"),
                  ("d", "제동거리 d", "m"), ("a", "감속도 a", "m/s²")]
        self.entries = {}
        self.undo_stack = []
        self.speed_unit = tk.StringVar(value="m/s")
        self._last_speed_unit = "m/s"
        self.input_history = self.store.history(self.storage_key)
        self.previous_values = self.store.previous(self.storage_key)

        form = tk.Frame(left, bg="white")
        form.pack(anchor="w", padx=10)
        for key, label, unit in fields:
            row = tk.Frame(form, bg="white")
            row.pack(anchor="w", pady=4)
            tk.Label(row, text=label, font=("맑은 고딕", 10), bg="white",
                     width=12, anchor="w").pack(side="left")
            e = tk.Entry(row, font=("맑은 고딕", 10), width=16, justify="right")
            attach_numeric_validation(e)
            e.pack(side="left", padx=5)
            if key == "v":
                self.speed_unit_combo = ttk.Combobox(
                    row, textvariable=self.speed_unit, values=("m/s", "m/min"),
                    state="readonly", width=7, font=("맑은 고딕", 9)
                )
                self.speed_unit_combo.pack(side="left")
                self.speed_unit_combo.bind("<<ComboboxSelected>>", self.on_speed_unit_change)
                bind_combobox_popdown_theme(self.speed_unit_combo)
            else:
                tk.Label(row, text=unit, font=("맑은 고딕", 10), bg="white").pack(side="left")
            self.entries[key] = e
            e.bind("<Return>", lambda _event: self.calculate())

        action_buttons = create_action_buttons(
            left, self.calculate,
            [
                ("clear", "입력값 삭제", self.clear, "normal"),
                ("previous", "이전 입력값", self.restore_previous, "disabled"),
                ("history", "입력 기록", self.show_history, "disabled"),
            ]
        )
        self.action_buttons = action_buttons
        self.previous_button = action_buttons["previous"]
        self.history_button = action_buttons["history"]
        if self.previous_values:
            self.previous_button.config(state="normal")
        if self.input_history:
            self.history_button.config(state="normal")

        self.initial_result_message = INITIAL_RESULT_MESSAGE
        self.result_text = create_result_display(right)
        self._show(initial_result_text(self))

    def _show(self, text, error=False):
        """브레이크 결과와 오류를 공통 결과창 형식으로 표시합니다."""
        set_result_display(self.result_text, text, error)

    def on_speed_unit_change(self, _event=None):
        """브레이크 속도 단위를 바꿀 때 같은 입력칸의 숫자도 즉시 변환합니다."""
        push_undo_state(self)
        new_unit = self.speed_unit.get()
        raw = self.entries["v"].get().strip()
        if raw:
            try:
                value = parse_number(raw, "속도")
                speed_ms = value / 60 if self._last_speed_unit == "m/min" else value
                display = speed_ms * 60 if new_unit == "m/min" else speed_ms
                self.entries["v"].delete(0, tk.END)
                self.entries["v"].insert(0, f"{display:.10g}")
            except ValueError as error:
                self._show("Input error: Check the speed value and unit."
                           if widget_language(self) == "en" else f"입력 오류: {error}", error=True)
        self._last_speed_unit = new_unit

    def _get(self, key):
        raw = self.entries[key].get().strip()
        if raw == "":
            return None
        value = parse_number(raw, "브레이크 입력값")
        if key == "v" and self.speed_unit.get() == "m/min":
            value /= 60
        return value

    def calculate(self):
        english = widget_language(self) == "en"
        try:
            v = self._get("v")
            t = self._get("t")
            d = self._get("d")
            a = self._get("a")
            solved = require_calculation(calculate_safely(
                calculate_brake_values, v=v, t=t, d=d, a=a))
            v, t, d, a = solved["v"], solved["t"], solved["d"], solved["a"]
            input_basis = solved["basis"]
            if not all(math.isfinite(value) for value in (v, t, d, a)):
                raise ValueError("계산 결과의 숫자 범위가 너무 큽니다. 입력값을 확인하세요.")

            # 감속도를 중력가속도 기준(g값)으로도 함께 보여줍니다.
            g_ratio = a / 9.81

            # 사용자가 직접 넣은 두 값과 계산 결과 요약을 저장합니다.
            self._remember_input(
                f"v={v:.4f} m/s({v * 60:.4f} m/min), t={t:.4f} s, "
                f"d={d:.4f} m, a={a:.4f} m/s²"
            )

            consistency = ""
            if len(solved["differences"]) >= 3:
                maximum_error = max(solved["differences"].values()) * 100
                if english:
                    consistency = (
                        f"[Input Consistency] "
                        f"{'Consistent' if solved['consistent'] else 'Inconsistent'} "
                        f"(maximum error {maximum_error:.2f}%)\n"
                    )
                else:
                    consistency = (
                        f"[입력값 관계 검사] {'일치' if solved['consistent'] else '불일치'} "
                        f"(최대 오차 {maximum_error:.2f}%)\n"
                    )
            if english:
                self._show(
                    "[Calculation Assumption] Constant deceleration to a stop\n"
                    "[Input Combination] Validated from the entered known values\n\n"
                    f"{consistency}"
                    f"▶ Speed v = {v:.4f} m/s  ( {v * 60:.4f} m/min )\n"
                    f"▶ Braking time t = {t:.4f} s\n"
                    f"▶ Braking distance d = {d:.4f} m\n"
                    f"▶ Deceleration a = {a:.4f} m/s²  ( {g_ratio:.4f} g )"
                )
            else:
                self._show(
                    f"[계산 가정] 일정한 감속도로 정지\n"
                    f"[입력 조합] {input_basis}\n\n"
                    f"{consistency}"
                    f"▶ 속도 v = {v:.4f} m/s  ( {v * 60:.4f} m/min )\n"
                    f"▶ 제동시간 t = {t:.4f} s\n"
                    f"▶ 제동거리 d = {d:.4f} m\n"
                    f"▶ 감속도 a = {a:.4f} m/s²  ( {g_ratio:.4f} g )"
                )
        except ZeroDivisionError:
            self._show(
                "Error: A value causes division by zero. Check the inputs."
                if english else "오류: 0으로 나누는 값이 있습니다. 입력값을 확인하세요.",
                error=True,
            )
        except ValueError as e:
            self._show(
                "Input error: Check the entered values and units." if english else f"오류: {e}",
                error=True,
            )
        except Exception as e:
            if english:
                LOGGER.exception("Unexpected brake calculation error")
                self._show("An unexpected error occurred during brake calculation.", error=True)
            else:
                show_unexpected_error(self, "브레이크 제동 계산", e)

    def _remember_input(self, result_summary):
        record = {key: entry.get() for key, entry in self.entries.items()}
        record["__speed_unit__"] = self.speed_unit.get()
        self.input_history = self.store.add_history(
            self.storage_key, record, result_summary
        )
        self.previous_values = self.store.previous(self.storage_key)
        self.previous_button.config(state="normal")
        self.history_button.config(state="normal")

    def restore_previous(self):
        """가장 최근에 계산하거나 삭제하기 전에 입력했던 두 값을 복원합니다."""
        if self.previous_values is None:
            return
        push_undo_state(self)
        self.speed_unit.set(self.previous_values.get("__speed_unit__", "m/s"))
        self._last_speed_unit = self.speed_unit.get()
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, self.previous_values.get(key, ""))
        self._show("Previous inputs loaded. Check the values, then calculate."
                   if widget_language(self) == "en" else
                   "이전 입력값을 불러왔습니다. 값을 확인한 뒤 계산하세요.")
        self.entries["v"].focus_set()

    def show_history(self):
        specs = [("__speed_unit__", "속도 단위", 90), ("v", "속도", 120), ("t", "제동시간(s)", 120),
                 ("d", "제동거리(m)", 120), ("a", "감속도(m/s²)", 140)]
        open_history_window(self, "브레이크 제동 입력 기록", self.input_history,
                            specs, self._load_history_record,
                            self._delete_history_record, self._clear_history,
                            self._rename_history_record)

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
        push_undo_state(self)
        self.speed_unit.set(record.get("__speed_unit__", "m/s"))
        self._last_speed_unit = self.speed_unit.get()
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, record.get(key, ""))
        clean_record = {key: record.get(key, "") for key in self.entries}
        clean_record["__speed_unit__"] = self.speed_unit.get()
        self.store.set_previous(self.storage_key, clean_record)
        self.previous_values = self.store.previous(self.storage_key)
        self.previous_button.config(state="normal")
        self._show((f"Input record {record_number} loaded. Check the values, then calculate."
                    if widget_language(self) == "en" else
                    f"입력 기록 {record_number}번을 불러왔습니다. 값을 확인한 뒤 계산하세요."))

    def clear(self):
        push_undo_state(self)
        current = {key: entry.get() for key, entry in self.entries.items()}
        if any(value.strip() for value in current.values()):
            self.store.set_previous(self.storage_key, current)
            self.previous_values = self.store.previous(self.storage_key)
            self.previous_button.config(state="normal")
        for entry in self.entries.values():
            entry.delete(0, tk.END)
        self._show(initial_result_text(self))
        self.entries["v"].focus_set()

    def capture_state(self):
        return {
            "values": {key: entry.get() for key, entry in self.entries.items()},
            "speed_unit": self.speed_unit.get(),
        }

    def apply_state(self, state, remember_undo=True):
        if remember_undo:
            push_undo_state(self)
        self.speed_unit.set(state.get("speed_unit", "m/s"))
        self._last_speed_unit = self.speed_unit.get()
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, state.get("values", {}).get(key, ""))

    def undo_last(self):
        undo_panel(self)


def build_brake_tab(notebook, store):
    panel = BrakePanel(notebook, store)
    notebook.add(panel, text="브레이크 제동")
    return panel


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
class TrafficPanel(tk.Frame):
    """입력 가정과 적용 기준을 분리하여 교통량을 추정하는 패널입니다."""
    def __init__(self, parent, store):
        super().__init__(parent, bg="white")
        self.store = store
        self.storage_key = "traffic"
        self.undo_stack = []

        note = ("PDF 교재의 용도별 인구·RTT·5분 수송능력 공식에 따른 초기 설계용 추정입니다.\n"
                "※ 선택한 건물용도에 해당하는 인구 입력항목만 사용하며, 다른 용도의 입력값은 무시합니다.\n"
                "※ 예상 정지수는 로컬 정지수(fL)+운행형식별 급행 정지수(fE)이며 손실시간률은 10%입니다.\n"
                "※ 교재는 대기시간을 운전간격의 1/2와 약 60%로 각각 설명하므로 환산율을 직접 확인하세요.")
        left, right = create_calculation_layout(self, note, formula_key="traffic")
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
        tk.Label(settings, text="건물용도", width=18, anchor="w",
                 font=("맑은 고딕", 10)).pack(side="left")
        self.building_use = tk.StringVar(value="사용자 설정")
        self.building_use_combo = ttk.Combobox(
            settings, textvariable=self.building_use, state="readonly", width=15,
            values=("오피스-전용사옥", "오피스-복합사옥", "오피스-공공건물",
                    "오피스-임대사무실", "공동주택", "호텔-고급", "호텔-중급",
                    "호텔-비즈니스", "병원", "판매시설", "사용자 설정")
        )
        self.building_use_combo.pack(side="left", padx=5)
        bind_combobox_popdown_theme(self.building_use_combo)
        self.building_use_combo.bind(
            "<<ComboboxSelected>>", self._on_building_use_changed
        )
        SkyButton(settings, text="용도값 저장", command=self.save_use_preset,
                  font=("맑은 고딕", 8), width=9, padx=2, pady=1).pack(side="left", padx=(3, 2))
        SkyButton(settings, text="용도값 적용", command=self.load_use_preset,
                  font=("맑은 고딕", 8), width=9, padx=2, pady=1).pack(side="left")

        # 스크롤 입력영역보다 먼저 하단 공간을 예약해야 버튼이 입력박스
        # 경계에 눌려 잘리지 않습니다. 크기는 다른 세 계산창과 동일합니다.
        action_buttons = create_action_buttons(
            left, self.calculate,
            [
                ("clear", "입력값 삭제", self.clear, "normal"),
                ("previous", "이전 입력값", self.restore_previous, "disabled"),
                ("history", "입력 기록", self.show_history, "disabled"),
            ],
            side="bottom"
        )
        self.action_buttons = action_buttons
        self.previous_button = action_buttons["previous"]
        self.history_button = action_buttons["history"]
        if self.previous_values:
            self.previous_button.config(state="normal")
        if self.input_history:
            self.history_button.config(state="normal")

        scroll_host = tk.Frame(left, bg="white")
        scroll_host.pack(fill="both", expand=True, padx=5)
        canvas = tk.Canvas(scroll_host, highlightthickness=0, height=400)
        vertical = ttk.Scrollbar(scroll_host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vertical.set)
        canvas.pack(side="left", fill="both", expand=True)
        vertical.pack(side="right", fill="y")
        form = tk.Frame(canvas, bg="white")
        form_window = canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(form_window, width=e.width))
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
            ("정지층수 산정", self.stop_count_mode,
             ("실제 정지층수 직접 입력", "교재 기준: 총 층수-2")),
            ("운행 서비스형식", self.service_type,
             ("로컬 운전 (fE=0)", "편도구간 급행 (fE=1)", "전층 자유 운전 (fE=2)")),
        ):
            row = tk.Frame(form, bg="white")
            row.pack(anchor="w", fill="x", pady=2)
            tk.Label(row, text=label, font=("맑은 고딕", 10), width=18,
                     anchor="w").pack(side="left")
            combo = ttk.Combobox(row, textvariable=variable, values=choices,
                                 state="readonly", width=24, font=("맑은 고딕", 9))
            combo.pack(side="left", padx=5)
            bind_combobox_popdown_theme(combo)
            self.traffic_choice_combos.append((variable, combo, tuple(choices)))
        for key, label, unit in fields:
            row = tk.Frame(form, bg="white")
            row.pack(anchor="w", fill="x", pady=2)
            tk.Label(row, text=label, font=("맑은 고딕", 10), bg="white",
                     width=18, anchor="w").pack(side="left")
            entry_width = 23 if key == "floor_areas" else 12
            e = tk.Entry(row, font=("맑은 고딕", 10), width=entry_width, justify="right")
            attach_numeric_validation(e, list_mode=key == "floor_areas")
            e.pack(side="left", padx=5)
            tk.Label(row, text=unit, font=("맑은 고딕", 10), bg="white").pack(side="left")
            self.field_rows[key] = row
            self.entries[key] = e
            e.bind("<Return>", lambda _event: self.calculate())

        self.entries["excluded_floors"].insert(0, "2")
        self.entries["guests_per_room"].insert(0, "2")
        self.entries["wait_factor"].insert(0, "50")

        self.criterion_row = tk.Frame(form, bg="white")
        self.criterion_row.pack(anchor="w", fill="x", pady=2)
        tk.Label(self.criterion_row, text="서비스 판정", width=18, anchor="w",
                 font=("맑은 고딕", 10)).pack(side="left")
        self.criterion_mode = tk.StringVar(value="PDF 교재 기준")
        criterion_combo = ttk.Combobox(
            self.criterion_row, textvariable=self.criterion_mode, state="readonly", width=15,
            values=("PDF 교재 기준", "판정 안 함", "사용자 정의 기준")
        )
        criterion_combo.pack(side="left", padx=5)
        bind_combobox_popdown_theme(criterion_combo)
        self.traffic_choice_combos.append(
            (self.criterion_mode, criterion_combo,
             ("PDF 교재 기준", "판정 안 함", "사용자 정의 기준"))
        )

        for key, label, unit in (
            ("good_threshold", "양호 기준 이하", "초"),
            ("bad_threshold", "불량 기준 초과", "초"),
            ("criterion_source", "판정 기준 메모(선택)", "문서명·사내기준 등"),
        ):
            row = tk.Frame(form, bg="white")
            row.pack(anchor="w", fill="x", pady=2)
            tk.Label(row, text=label, width=18, anchor="w",
                     font=("맑은 고딕", 10)).pack(side="left")
            entry = tk.Entry(row, font=("맑은 고딕", 10),
                             width=23 if key == "criterion_source" else 12,
                             justify="right" if key != "criterion_source" else "left")
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

        self.result_text = create_result_display(right)
        self.initial_result_message = INITIAL_RESULT_MESSAGE
        self._show(initial_result_text(self))

    def _show(self, text, error=False):
        """교통량 결과와 오류를 공통 결과창 형식으로 표시합니다."""
        set_result_display(self.result_text, text, error)

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
        return traffic_visible_input_fields(choice_ko(self.building_use.get()))

    def apply_choice_language(self, language):
        """교통량 선택항목은 표시만 번역하고 계산용 내부 의미는 유지합니다."""
        variables = [(self.building_use, self.building_use_combo,
                      tuple(CHOICE_EN.keys())[:11]), *self.traffic_choice_combos]
        seen = set()
        for variable, combo, korean_values in variables:
            if str(combo) in seen:
                continue
            seen.add(str(combo))
            current_ko = choice_ko(variable.get())
            display_values = tuple(CHOICE_EN.get(value, value) for value in korean_values) \
                if language == "en" else tuple(korean_values)
            combo.configure(values=display_values)
            variable.set(CHOICE_EN.get(current_ko, current_ko) if language == "en" else current_ko)

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
        building_use = choice_ko(self.building_use.get())
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
        english = widget_language(self) == "en"
        use_name = choice_ko(self.building_use.get())
        display_name = CHOICE_EN.get(use_name, use_name) if english else use_name
        if use_name == "사용자 설정":
            messagebox.showinfo(
                "Building-use Preset" if english else "건물용도 기본값",
                "Select a specific building use first." if english else "먼저 구체적인 건물용도를 선택해주세요.", parent=self)
            return
        if not messagebox.askyesno(
                "Building-use Preset" if english else "건물용도 기본값",
                (f"Save the current inputs as the preset for ‘{display_name}’?" if english else
                 f"현재 입력값을 ‘{use_name}’의 사용자 기본값으로 저장할까요?"),
                parent=self):
            return
        self.store.save_traffic_preset(use_name, self.capture_state())
        if self.store.save_warning:
            return
        messagebox.showinfo(
            "Building-use Preset" if english else "건물용도 기본값",
            ("Preset saved. You can maintain source-verified values directly."
             if english else "저장했습니다. 출처가 확인된 값을 직접 관리할 수 있습니다."), parent=self)

    def load_use_preset(self):
        """선택한 건물용도에 사용자가 저장한 값을 입력칸에 적용합니다."""
        english = widget_language(self) == "en"
        use_name = choice_ko(self.building_use.get())
        display_name = CHOICE_EN.get(use_name, use_name) if english else use_name
        preset = self.store.traffic_preset(use_name)
        if not preset:
            messagebox.showinfo(
                "Building-use Preset" if english else "건물용도 기본값",
                (f"No preset is saved for ‘{display_name}’." if english else
                 f"‘{use_name}’에 저장된 사용자 기본값이 없습니다."), parent=self)
            return
        self.apply_state(preset)
        self._show(
            f"Loaded the preset for ‘{display_name}’. Check the criteria and inputs."
            if english else f"‘{use_name}’ 사용자 기본값을 불러왔습니다. 기준과 입력값을 확인하세요."
        )

    def capture_state(self):
        state = {key: entry.get() for key, entry in self.entries.items()}
        state["__building_use__"] = choice_ko(self.building_use.get())
        state["__criterion_mode__"] = choice_ko(self.criterion_mode.get())
        state["__stop_count_mode__"] = choice_ko(self.stop_count_mode.get())
        state["__service_type__"] = choice_ko(self.service_type.get())
        return state

    def apply_state(self, state, remember_undo=True):
        if remember_undo:
            push_undo_state(self)
        self.building_use.set(state.get("__building_use__", "사용자 설정"))
        self.criterion_mode.set(state.get("__criterion_mode__", "PDF 교재 기준"))
        self.stop_count_mode.set(
            state.get("__stop_count_mode__", "실제 정지층수 직접 입력")
        )
        self.service_type.set(state.get("__service_type__", "로컬 운전 (fE=0)"))
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            defaults = {"excluded_floors": "2", "guests_per_room": "2", "wait_factor": "50"}
            default = defaults.get(key, "")
            entry.insert(0, state.get(key, default) or default)
        self._update_use_fields()
        self.apply_choice_language(getattr(self.winfo_toplevel(), "_language", "ko"))

    def undo_last(self):
        undo_panel(self)

    def clear(self):
        push_undo_state(self)
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
        self._show(initial_result_text(self))
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
        self._show("Previous inputs loaded. Check the values, then calculate."
                   if widget_language(self) == "en" else
                   "이전 입력값을 불러왔습니다. 값을 확인한 뒤 계산하세요.")
        self._focus_first_use_field()

    def show_history(self):
        specs = [
            ("__building_use__", "건물용도", 90),
            ("__criterion_mode__", "판정방식", 100),
            ("__stop_count_mode__", "정지층수 방식", 110),
            ("__service_type__", "서비스형식", 110),
            ("A", "오피스 층면적", 90), ("F", "총 층수", 70),
            ("excluded_floors", "제외층수", 70),
            ("floor_areas", "층별면적", 120),
            ("S", "점유면적", 90), ("phi", "집중률(%)", 85),
            ("households", "세대수", 70),
            ("persons_per_household", "세대당인원", 80),
            ("rooms", "객실수", 70), ("guests_per_room", "객실당인원", 80),
            ("beds", "병상수", 70), ("direct_population", "직접인구", 80),
            ("C", "카 정원", 70), ("board_rate", "탑승률(%)", 85),
            ("n", "정지층수", 80), ("td", "도어시간", 80),
            ("tp", "출입시간", 80), ("Tr_travel", "주행시간", 80),
            ("wait_factor", "대기환산율", 80), ("N_current", "현재대수", 70),
            ("good_threshold", "양호기준", 75),
            ("bad_threshold", "불량기준", 75),
            ("criterion_source", "판정기준 메모", 110),
        ]
        open_history_window(self, "교통량 분석 입력 기록", self.input_history,
                            specs, self._load_history_record,
                            self._delete_history_record, self._clear_history,
                            self._rename_history_record)

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
        self._show((f"Input record {record_number} loaded. Check the values, then calculate."
                    if widget_language(self) == "en" else
                    f"입력 기록 {record_number}번을 불러왔습니다. 값을 확인한 뒤 계산하세요."))
        self._focus_first_use_field()

    def calculate(self):
        english = widget_language(self) == "en"
        try:
            building_use = choice_ko(self.building_use.get())
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

            if choice_ko(self.stop_count_mode.get()) == "교재 기준: 총 층수-2":
                n = F - 2
                if n <= 0:
                    raise ValueError("교재식 정지층수는 총 층수가 2층보다 커야 합니다.")
            else:
                n = self._get("n", "실제 정지층수")
            express_stops = {
                "로컬 운전 (fE=0)": 0,
                "편도구간 급행 (fE=1)": 1,
                "전층 자유 운전 (fE=2)": 2,
            }[choice_ko(self.service_type.get())]

            floor_areas = []
            floor_areas_text = self.entries["floor_areas"].get().strip()
            if floor_areas_text:
                floor_areas = [parse_number(item, "층별 유효면적")
                               for item in floor_areas_text.split(";") if item.strip()]

            included = int(F - excluded)
            population_basis = ""
            households = rooms = persons = guests = beds = None
            if building_use.startswith("오피스-"):
                if A is None and not floor_areas:
                    raise ValueError("오피스는 '층별 이용면적' 또는 '층별 면적목록'이 필요합니다.")
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
                population_basis = "PDF 호텔식: 객실수×객실당 수용인원(또는 숙박 가능 인원)"
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
                (F, "건물층수"), (population, "건물인구"),
                (phi, "집중률"), (C, "카 정원"), (board_rate, "탑승률"),
                (n, "정지층수"), (td, "도어 개폐시간"),
                (tp, "승객 출입시간"), (Tr_travel, "주행시간"),
            ]
            if building_use.startswith("오피스-"):
                positive_values.append((S, "오피스 1인당 면적"))
                if A is not None:
                    positive_values.append((A, "오피스 층별 이용면적"))
            for value, label in positive_values:
                ensure_positive(value, label)
            for area in floor_areas:
                ensure_positive(area, "층별 유효면적")
            for value, label in ((households, "공동주택 세대수"),
                                 (persons, "세대당 거주인구"),
                                 (rooms, "호텔 객실수"),
                                 (guests, "객실당 수용인원"),
                                 (beds, "병원 병상수")):
                if value is not None:
                    ensure_positive(value, label)
            if not 0 <= excluded < F:
                raise ValueError("'인구산정 제외층수'는 0 이상이며 총 층수보다 작아야 합니다.")
            if not 0 < phi <= 1 or not 0 < board_rate <= 1 or not 0 < wait_factor <= 1:
                raise ValueError("집중률·탑승률·대기시간 환산율은 0 초과 100 이하의 %여야 합니다.")
            for value, label in ((F, "건물층수"), (excluded, "이용인구 제외층수"),
                                 (C, "카 정원"), (n, "정지층수")):
                if not value.is_integer():
                    raise ValueError(f"'{label}'은(는) 정수로 입력해주세요.")
            for value, label in ((households, "공동주택 세대수"),
                                 (rooms, "호텔 객실수"), (beds, "병원 병상수")):
                if value is not None and not value.is_integer():
                    raise ValueError(f"'{label}'은(는) 정수로 입력해주세요.")
            if n > F:
                raise ValueError(f"'정지층수'는 총 {int(F)}층보다 클 수 없습니다.")
            if n + express_stops > F:
                raise ValueError(
                    "로컬 정지층수와 급행 정지수의 합은 총 층수보다 클 수 없습니다."
                )
            if building_use.startswith("오피스-") and floor_areas and len(floor_areas) != included:
                raise ValueError(
                    f"층별 유효면적은 제외 후 유효층수 {included}개와 같은 개수로 입력해주세요."
                )
            if current_cars is not None:
                ensure_positive(current_cars, "현재 설치대수")
                if not current_cars.is_integer():
                    raise ValueError("'현재 설치대수'는 정수로 입력해주세요.")

            calculated = require_calculation(calculate_safely(calculate_traffic_values, {
                "A": A or 0, "F": F, "excluded_floors": excluded,
                "floor_areas": floor_areas, "S": S or 1, "population": population,
                "phi": phi, "C": C,
                "board_rate": board_rate, "n": n, "td": td, "tp": tp,
                "Tr_travel": Tr_travel, "wait_factor": wait_factor,
                "express_stops": express_stops,
            }))
            if not all(math.isfinite(value) for key, value in calculated.items()
                       if isinstance(value, (int, float))):
                raise ValueError("계산 결과의 숫자 범위가 너무 큽니다. 입력값을 확인하세요.")

            N = calculated["recommended"]
            AIT = calculated["interval"]
            AWT = calculated["wait"]
            reference = traffic_pdf_reference(
                building_use, F, population=population, total_area=total_area,
                households=households, rooms=rooms
            )

            criterion_line = "서비스 판정: 적용하지 않음 (확인된 기준을 선택하지 않음)"
            if choice_ko(self.criterion_mode.get()) == "PDF 교재 기준":
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
                        f"PDF 운전간격 판정: {grade} "
                        "(표 1-11 호텔 40초 이하 예시)"
                    )
            elif choice_ko(self.criterion_mode.get()) == "사용자 정의 기준":
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
                (f"Recommended cars {N}, interval {AIT:.2f} s, average wait {AWT:.2f} s"
                 if english else
                 f"수송능력 산정 {N}대, 운전간격 {AIT:.2f}초, 평균대기 {AWT:.2f}초")
            )

            result = "[교통량 분석 결과 — 입력 가정에 따른 추정]\n\n"
            result += f"건물용도 분류             = {choice_ko(self.building_use.get())}\n"
            result += f"이용인구 산정근거         = {population_basis}\n"
            if building_use.startswith("오피스-"):
                area_mode = "층별 개별 면적" if floor_areas else "모든 유효층 동일 면적"
                result += f"면적 적용                 = {area_mode}\n"
                result += (f"인구산정 유효층 / 총 면적 = {included}층 / "
                           f"{calculated['total_area']:.1f} m²\n")
            elif building_use == "공동주택":
                result += f"세대수 × 세대당 인원      = {int(households)} × {persons:g}\n"
            elif building_use.startswith("호텔-"):
                result += f"객실수 × 객실당 인원      = {int(rooms)} × {guests:g}\n"
            elif building_use == "병원":
                result += f"병상수                     = {int(beds)} 병상\n"
            result += f"예상 이용인구 M           = {calculated['population']:.1f} 인\n"
            result += f"승객수 r                  = {calculated['riders']:.2f} 인\n"
            result += (f"예상 정지수 fL+fE         = {calculated['local_stops']:.2f} + "
                       f"{calculated['express_stops']:g} = {calculated['expected_stops']:.2f}\n")
            result += f"도어 / 출입 / 손실시간    = {calculated['door_time']:.2f} / {calculated['passenger_time']:.2f} / {calculated['loss_time']:.2f} 초\n"
            result += f"일주시간 RTT              = {calculated['round_trip']:.2f} 초\n\n"
            result += f"대당 5분 수송능력 P'      = {calculated['capacity']:.2f} 인/5분\n"
            result += f"혼잡 5분 이용자수 Q       = {calculated['peak_users']:.1f} 인\n"
            result += f"수송능력 기준 산정대수 N  = {N} 대\n"
            result += f"산정대수 운전간격 / 대기  = {AIT:.2f} / {AWT:.2f} 초\n\n"

            result += "[PDF 설계 참고값]\n"
            demand_range = reference["demand_range"]
            if demand_range:
                low, high = demand_range
                demand_status = ("범위 내" if low <= phi * 100 <= high
                                 else "범위 밖 — 입력 근거 확인")
                result += (f"피크 5분 집중률 예시      = {low:g}~{high:g}% "
                           f"(현재 {phi*100:.1f}%, {demand_status})\n")
            else:
                result += "피크 5분 집중률 예시      = 해당 용도 표 제시 없음\n"
            speed_range = reference["speed_range_m_min"]
            result += (f"층수별 권장속도 예시       = "
                       f"{speed_range + ' m/min' if speed_range else '해당 용도 표 제시 없음'}\n")
            if reference["rough_count"] is not None:
                rough = reference["rough_count"]
                result += (f"규모별 개략 설치대수      = {rough}대 "
                           f"({reference['rough_basis']})\n")
                result += (f"두 산정값 비교             = 수송능력식 {N}대 / "
                           f"규모 참고표 {rough}대\n")
            result += criterion_line + "\n\n"

            result += "[설치대수별 비교]\n"
            for row in calculated["comparison"]:
                result += f"{row['count']}대: 운전간격 {row['interval']:.2f}초 / 예상대기 {row['wait']:.2f}초\n"
            if current_cars is not None:
                current_interval = calculated["round_trip"] / current_cars
                capacity_status = (f"수송능력 산정값보다 {N-int(current_cars)}대 부족"
                                   if current_cars < N else
                                   f"수송능력 산정값 충족, {int(current_cars)-N}대 여유")
                result += (f"현재 {int(current_cars)}대: 운전간격 {current_interval:.2f}초 / "
                           f"예상대기 {current_interval * wait_factor:.2f}초 ({capacity_status})\n")

            result += "\n[계산 가정]\n"
            result += (f"정지층수 방식: {choice_ko(self.stop_count_mode.get())}, "
                       f"서비스형식: {choice_ko(self.service_type.get())}\n")
            result += f"손실시간률 10%, 대기시간 환산율 {wait_factor*100:.1f}%\n"
            if building_use.startswith("오피스-"):
                result += f"오피스 인구산정 제외층수: {int(excluded)}층\n"
            result += ("※ PDF 안에서도 평균대기시간을 운전간격의 1/2와 약 60%로 각각 "
                       "설명하므로 선택한 환산율을 함께 표시합니다.\n")
            result += ("※ 규모별 대수·권장속도·서비스 판정은 법정 최소기준이 아니라 "
                       "교재의 초기 설계 예시입니다.\n")
            result += "출처: LM1505010802_23v1 설비계획 수립, 표 1-11~1-13 및 교통량 산식\n"
            result += f"계산식 버전: {FORMULA_VERSION}"

            if english:
                use_name = CHOICE_EN.get(building_use, building_use)
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

                criterion_mode = choice_ko(self.criterion_mode.get())
                if criterion_mode == "판정 안 함":
                    criterion_line_en = "Service rating: Not applied"
                elif criterion_mode == "사용자 정의 기준":
                    grade_en = "Good" if AIT <= good else ("Poor" if AIT > bad else "Fair")
                    criterion_line_en = f"Custom service rating: {grade_en}"
                    source = self.entries["criterion_source"].get().strip()
                    if source:
                        criterion_line_en += f" (note: {source})"
                else:
                    if reference["interval_target"] is None:
                        criterion_line_en = "PDF interval rating: No target is listed for this use"
                    elif building_use == "공동주택":
                        grade_en = ("Shorter than the example range" if AIT < 60 else
                                    "Within the example range" if AIT <= 90 else
                                    "Above the example range")
                        criterion_line_en = f"PDF interval rating: {grade_en} (residential: 60–90 s)"
                    elif building_use.startswith("오피스-"):
                        grade_en = ("Target met" if AIT <= 30 else
                                    "Verify handling capacity" if AIT <= 40 else
                                    "Above the reference target")
                        criterion_line_en = f"PDF interval rating: {grade_en} (office: 30 s; up to 40 s when capacity is sufficient)"
                    else:
                        grade_en = "Target met" if AIT <= 40 else "Above the reference target"
                        criterion_line_en = f"PDF interval rating: {grade_en} (hotel: 40 s)"

                lines = [
                    "[Traffic Analysis Result — Initial Design Estimate]", "",
                    f"Building use                = {use_name}",
                    f"Population basis            = {population_basis_en}",
                ]
                if building_use.startswith("오피스-"):
                    area_mode_en = "Individual floor areas" if floor_areas else "Same area for all included floors"
                    lines.extend([
                        f"Area method                 = {area_mode_en}",
                        f"Included floors / total area = {included} / {calculated['total_area']:.1f} m²",
                    ])
                elif building_use == "공동주택":
                    lines.append(f"Households × people        = {int(households)} × {persons:g}")
                elif building_use.startswith("호텔-"):
                    lines.append(f"Rooms × guests             = {int(rooms)} × {guests:g}")
                elif building_use == "병원":
                    lines.append(f"Hospital beds              = {int(beds)}")
                lines.extend([
                    f"Estimated population M      = {calculated['population']:.1f} people",
                    f"Passengers per trip r       = {calculated['riders']:.2f} people",
                    (f"Expected stops fL+fE        = {calculated['local_stops']:.2f} + "
                     f"{calculated['express_stops']:g} = {calculated['expected_stops']:.2f}"),
                    (f"Door / transfer / loss time = {calculated['door_time']:.2f} / "
                     f"{calculated['passenger_time']:.2f} / {calculated['loss_time']:.2f} s"),
                    f"Round-trip time RTT         = {calculated['round_trip']:.2f} s", "",
                    f"5-minute capacity per car P'= {calculated['capacity']:.2f} people",
                    f"Peak 5-minute demand Q      = {calculated['peak_users']:.1f} people",
                    f"Recommended number of cars N = {N}",
                    f"Interval / expected wait    = {AIT:.2f} / {AWT:.2f} s", "",
                    "[PDF Design Reference]",
                ])
                demand_range = reference["demand_range"]
                if demand_range:
                    low, high = demand_range
                    demand_status_en = "within range" if low <= phi * 100 <= high else "outside range — verify the assumption"
                    lines.append(f"Peak-rate example          = {low:g}–{high:g}% (current {phi*100:.1f}%, {demand_status_en})")
                else:
                    lines.append("Peak-rate example          = Not listed for this use")
                speed_range = reference["speed_range_m_min"]
                lines.append(f"Speed example by floor count = {speed_range + ' m/min' if speed_range else 'Not listed for this use'}")
                if reference["rough_count"] is not None:
                    rough = reference["rough_count"]
                    lines.extend([
                        f"Scale-table rough count     = {rough} cars",
                        f"Calculated / rough count    = {N} / {rough} cars",
                    ])
                lines.extend([criterion_line_en, "", "[Car-count Comparison]"])
                for row in calculated["comparison"]:
                    lines.append(f"{row['count']} cars: interval {row['interval']:.2f} s / expected wait {row['wait']:.2f} s")
                if current_cars is not None:
                    current_interval = calculated["round_trip"] / current_cars
                    capacity_status_en = (f"short by {N-int(current_cars)} cars" if current_cars < N else
                                          f"requirement met, {int(current_cars)-N} spare")
                    lines.append(
                        f"Existing {int(current_cars)} cars: interval {current_interval:.2f} s / "
                        f"expected wait {current_interval * wait_factor:.2f} s ({capacity_status_en})"
                    )
                lines.extend([
                    "", "[Assumptions]",
                    (f"Stop method: {CHOICE_EN.get(choice_ko(self.stop_count_mode.get()), self.stop_count_mode.get())}; "
                     f"service type: {CHOICE_EN.get(choice_ko(self.service_type.get()), self.service_type.get())}"),
                    f"Lost-time rate 10%; waiting-time factor {wait_factor*100:.1f}%",
                ])
                if building_use.startswith("오피스-"):
                    lines.append(f"Office population excludes {int(excluded)} floors")
                lines.extend([
                    "The reference describes average waiting time as both one-half and about 60% of the interval; the selected factor is shown above.",
                    "Counts, speeds, and service ratings are initial design references, not statutory minimums.",
                    "Source: LM1505010802_23v1 Equipment Planning, Tables 1-11–1-13 and traffic formulas",
                    f"Formula version: {FORMULA_VERSION}",
                ])
                result = "\n".join(lines)

            result += "\n[설계평가] 운전간격·수송능력은 선택한 교재/사용자 기준에 따른 초기 검토입니다.\n"
            result += "[법령검토] 건축물 용도·규모·층수 등 별도 입력과 건축법령 대조가 필요하여 현재 판정 불가. 비상용·장애인용 요구도 별도 확인하세요.\n"
            result += "KS B ISO 8100-32는 계획·선정용 표준이며 법정 검사 판정값이 아닙니다."
            self._show(result)

        except ZeroDivisionError:
            self._show(
                "Error: A value causes division by zero. Check the inputs."
                if english else "오류: 0으로 나누는 값이 있습니다. 입력값을 확인하세요.",
                error=True,
            )
        except ValueError as e:
            self._show(
                "Input error: Check the required values, ranges, and selected units."
                if english else f"입력 오류: {e}",
                error=True,
            )
        except Exception as e:
            if english:
                LOGGER.exception("Unexpected traffic analysis error")
                self._show("An unexpected error occurred during traffic analysis.", error=True)
            else:
                show_unexpected_error(self, "교통량 분석", e)


def build_traffic_tab(notebook, store):
    panel = TrafficPanel(notebook, store)
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
from elevator_review_engine import (KC_SOURCE, KC_URL, INTERNAL_NOTICE, compare_criterion,
    evaluate_rope_clause, evaluate_actual_speed, evaluate_brake_evidence,
    evaluate_traction_case, evaluate_motor_capacity, scurve_profile, review_guidance)

class CriteriaPanel(tk.Frame):
    """법령 단일 조항과 설계용 계산을 별도 표시한다."""
    def __init__(self,parent,store):
        super().__init__(parent,bg='white')
        self.store=store
        self.entries={}
        self.undo_stack=[]
        self.storage_key='criteria'
        self.previous_values=store.previous(self.storage_key)
        self.input_history=store.history(self.storage_key)
        self.grid_rowconfigure(0,weight=1)
        self.grid_columnconfigure(0,weight=1,uniform='criteria_split')
        self.grid_columnconfigure(1,weight=1,uniform='criteria_split')
        holder=tk.Frame(self,bg='white');holder.grid(row=0,column=0,sticky='nsew')
        canvas=tk.Canvas(holder,bg='white',highlightthickness=0)
        bar=ttk.Scrollbar(holder,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        frame=tk.Frame(canvas,bg='white')
        canvas.create_window((8,8),window=frame,anchor='nw')
        frame.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-1 if e.delta>0 else 1,'units'))

        tk.Label(frame,text='KC 2050-51:2022 개별 조항 검토',font=('맑은 고딕',11,'bold'),bg='white').pack(anchor='w')
        self.drive=tk.StringVar(value='권상식')
        drive_combo=ttk.Combobox(frame,textvariable=self.drive,values=('권상식','기타'),state='readonly',width=18)
        drive_combo.pack(anchor='w')
        drive_combo.bind('<Return>',self._calculate_on_return)
        for key,label in (('count','로프 가닥 수'),('diameter','로프 공칭직경 mm'),('breaking','1가닥 최소 파단하중 N'),('force','최하층 정격하중 최대 장력 N'),('rated','정격속도 m/s'),('measured_up','중간구간 실측 상승 m/s'),('measured_down','중간구간 실측 하강 m/s'),('selected_motor','선정 전동기 kW')):
            row=tk.Frame(frame,bg='white');row.pack(anchor='w',pady=2)
            tk.Label(row,text=label,width=25,anchor='w',bg='white').pack(side='left')
            entry=tk.Entry(row,width=12);attach_numeric_validation(entry);entry.pack(side='left');self.entries[key]=entry
            entry.bind('<Return>',self._calculate_on_return)
        self.speed_conditions=tk.BooleanVar(value=False)
        tk.Checkbutton(frame,text='50% 하중, 중간 주행, 정격 전압·주파수 모두 확인',variable=self.speed_conditions,bg='white').pack(anchor='w')
        self.brake_checks={}
        for key,label in (('load','125% 하강에서 브레이크 단독 정지 시험'),('sets','제동 기계부품 최소 2세트 확인'),('failure','한 세트 고장 시 양방향 조건 정지·유지'),('decel','안전장치·완충기 감속도와 비교')):
            var=tk.StringVar(value='자료 없음');self.brake_checks[key]=var
            row=tk.Frame(frame,bg='white');row.pack(anchor='w')
            tk.Label(row,text=label,width=39,anchor='w',bg='white').pack(side='left')
            combo=ttk.Combobox(row,textvariable=var,values=('자료 없음','충족 증빙','미충족 증빙'),state='readonly',width=12)
            combo.pack(side='left');combo.bind('<Return>',self._calculate_on_return)
        tk.Label(frame,text='부속서 IX: 최악 조건에서 산정한 장력과 마찰값 직접 입력',bg='white').pack(anchor='w',pady=(6,1))
        self.traction_entries={}
        for case,title in (('load','125% 적재'),('emergency','비상제동'),('stationary','카·균형추 정지')):
            row=tk.Frame(frame,bg='white');row.pack(anchor='w')
            tk.Label(row,text=title,width=16,anchor='w',bg='white').pack(side='left')
            for key,label in (('t1','T1 N'),('t2','T2 N'),('f','f'),('alpha','α rad')):
                tk.Label(row,text=label,bg='white').pack(side='left')
                e=tk.Entry(row,width=7);attach_numeric_validation(e);e.pack(side='left',padx=2)
                e.bind('<Return>',self._calculate_on_return)
                self.traction_entries[(case,key)]=e
        actions=tk.Frame(frame,bg='white');actions.pack(anchor='w',fill='x',pady=8)
        SkyButton(actions,text='기준 검토',command=self.calculate,width=11).pack(side='left')
        SkyButton(actions,text='입력값 삭제',command=self.clear,width=11).pack(side='left',padx=5)
        self.previous_button=SkyButton(actions,text='이전 입력값',command=self.restore_previous,
                                       width=11,state='normal' if self.previous_values else 'disabled')
        self.previous_button.pack(side='left',padx=5)
        self.history_button=SkyButton(actions,text='입력 기록',command=self.show_history,
                                      width=11,state='normal' if self.input_history else 'disabled')
        self.history_button.pack(side='left',padx=5)

        result_holder=tk.LabelFrame(self,text=' 검토 결과 ',font=('맑은 고딕',11,'bold'),bg='white',padx=6,pady=6)
        result_holder.grid(row=0,column=1,sticky='nsew',padx=(7,0),pady=(3,6))
        self.result_text=create_result_display(result_holder)
        self._show('입력 자료별 개별 조항만 검토합니다. 검사기관의 최종 판정 대상입니다.')
    def _calculate_on_return(self,_event=None):
        self.calculate()
        return 'break'
    def _show(self,s,error=False):set_result_display(self.result_text,s,error)
    def capture_state(self):
        state={key:entry.get() for key,entry in self.entries.items()}
        state.update({f'{case}_{key}':entry.get() for (case,key),entry in self.traction_entries.items()})
        state['__drive__']=self.drive.get()
        state['__speed_conditions__']=self.speed_conditions.get()
        state.update({f'__brake_{key}__':var.get() for key,var in self.brake_checks.items()})
        return state
    def apply_state(self,state,remember_undo=True):
        if not isinstance(state,dict):return
        if remember_undo:push_undo_state(self)
        for key,entry in self.entries.items():
            entry.delete(0,tk.END);entry.insert(0,str(state.get(key,'')))
        for (case,key),entry in self.traction_entries.items():
            entry.delete(0,tk.END);entry.insert(0,str(state.get(f'{case}_{key}','')))
        self.drive.set(state.get('__drive__','권상식'))
        self.speed_conditions.set(state.get('__speed_conditions__',False))
        for key,var in self.brake_checks.items():var.set(state.get(f'__brake_{key}__','자료 없음'))
    def _remember(self,summary):
        if getattr(self.store,'_suppress_history',False):return
        self.input_history=self.store.add_history(self.storage_key,self.capture_state(),summary)
        self.previous_values=self.store.previous(self.storage_key)
        self.previous_button.config(state='normal')
        self.history_button.config(state='normal')
    def clear(self):
        current=self.capture_state()
        push_undo_state(self)
        if any(current[key].strip() for key in self.entries) or any(
            current[f'{case}_{key}'].strip() for case,key in self.traction_entries) or (
            current['__drive__']!='권상식' or current['__speed_conditions__'] or
            any(var.get()!='자료 없음' for var in self.brake_checks.values())):
            self.store.set_previous(self.storage_key,current)
            self.previous_values=self.store.previous(self.storage_key)
            self.previous_button.config(state='normal')
        for e in list(self.entries.values())+list(self.traction_entries.values()):e.delete(0,tk.END)
        for v in self.brake_checks.values():v.set('자료 없음')
        self.drive.set('권상식')
        self.speed_conditions.set(False);self._show('입력값을 삭제했습니다.')
    def restore_previous(self):
        if self.previous_values is None:return
        self.apply_state(self.previous_values)
        self._show('이전 입력값을 불러왔습니다. 값을 확인한 뒤 기준 검토를 누르세요.')
    def show_history(self):
        specs=[('__drive__','구동 방식',95),('count','로프 가닥 수',85),('diameter','로프 직경',85),
               ('breaking','파단하중',100),('force','최대 장력',90),('rated','정격속도',85),
               ('measured_up','실측 상승',85),('measured_down','실측 하강',85),
               ('selected_motor','선정 전동기',90),('__speed_conditions__','속도 측정조건',95)]
        specs.extend((f'__brake_{key}__',f'브레이크 {key}',115) for key in self.brake_checks)
        specs.extend((f'{case}_{key}',f'{case} {key}',85)
                     for case,key in self.traction_entries)
        open_history_window(self,'기준 검토 입력 기록',self.input_history,specs,
                            self._load_history_record,self._delete_history_record,
                            self._clear_history,self._rename_history_record)
    def _load_history_record(self,record,number):
        self.apply_state(record)
        self.store.set_previous(self.storage_key,self.capture_state())
        self.previous_values=self.store.previous(self.storage_key)
        self.previous_button.config(state='normal')
        self._show(f'입력 기록 {number}번을 불러왔습니다. 값을 확인한 뒤 기준 검토를 누르세요.')
    def _delete_history_record(self,index):
        self.input_history=self.store.delete_history(self.storage_key,index)
        if not self.input_history:self.history_button.config(state='disabled')
        return self.input_history
    def _clear_history(self):
        self.store.clear_history(self.storage_key)
        self.input_history=[];self.history_button.config(state='disabled')
    def _rename_history_record(self,index,name):
        self.input_history=self.store.rename_history(self.storage_key,index,name)
        return self.input_history
    def undo_last(self):undo_panel(self)
    def calculate(self):
        try:
            def number(k):
                s=self.entries[k].get().strip()
                return parse_number(s,k) if s else None
            def add_review(lines,topic,**details):
                lines.append('  [권장 검토 — 자동 설계변경 지시가 아닙니다]')
                lines.extend('  '+item for item in review_guidance(topic,**details))
            rope=evaluate_rope_clause('traction' if self.drive.get()=='권상식' else 'other','rope',*(number(k) for k in ('count','diameter','breaking','force')))
            lines=['[9.2.2 매다는 장치 안전율 — 수치항목]',f"상태: {rope['status']} / {rope['reason']}"]
            if 'value' in rope:lines.append(f"안전율 {rope['value']:.3f} / 하한 {rope['limit']:g} / 여유율 {rope['margin_pct']:.2f}% / {rope['engineering']} ({rope['clause']})")
            if rope['status']=='NONCOMPLIANT':add_review(lines,'rope')
            lines.extend(['','[9.3 / 부속서 IX 권상 3조건 — 조건식 계산]'])
            legal_notes=[]
            for case,title in (('load','적재'),('emergency','비상제동'),('stationary','카·균형추 정지')):
                vals=[]
                for key in ('t1','t2','f','alpha'):
                    raw=self.traction_entries[(case,key)].get().strip()
                    vals.append(parse_number(raw,key) if raw else None)
                traction=evaluate_traction_case(case,*vals)
                if 'ratio' in traction:
                    lines.append(f"{title}: {traction['ratio']:.4f} {traction['comparison']} {traction['limit']:.4f}  /  여유율 {traction['margin_pct']:.2f}%  /  {traction['status']}")
                else:
                    lines.append(f"{title}: 조건식 자료 부족")
                legal_notes.append((title,traction.get('legal_status',traction['status']),traction['reason']))
                if traction['status']=='조건식 미충족':add_review(lines,'traction',case=case)
            lines.append('')
            for title,status,_reason in legal_notes:
                lines.append(f'※ {title} 법정 상태: {status}')
            reasons=list(dict.fromkeys(reason for _title,_status,reason in legal_notes))
            if len(reasons)==1:
                lines.append('   공통 사유: '+reasons[0])
            else:
                for title,_status,reason in legal_notes:
                    lines.append(f'   {title} 사유: {reason}')
            lines.extend(['','[13.2.4 실측 운행속도 — 상승·하강 별도]'])
            for name,key in (('상승','measured_up'),('하강','measured_down')):
                speed=evaluate_actual_speed(number('rated'),number(key),self.speed_conditions.get(),self.speed_conditions.get(),self.speed_conditions.get())
                line=f"{name}: {speed['status']} / {speed.get('ratio_pct','—')}%"
                if 'margin_percentage_points' in speed:line+=f" / 경계까지 {speed['margin_percentage_points']:.2f}%p"
                lines.append(line+' / '+speed['reason'])
                if speed['status']=='NONCOMPLIANT':add_review(lines,'speed',measured_ratio=speed['ratio_pct'])
            mapping={'자료 없음':None,'충족 증빙':True,'미충족 증빙':False}
            failed_checks=tuple(key for key,var in self.brake_checks.items() if var.get()=='미충족 증빙')
            brake=evaluate_brake_evidence(*(mapping[v.get()] for v in self.brake_checks.values()))
            lines.extend(['','[13.2.2.2.1 브레이크 증빙]',f"상태: {brake['status']} / {brake['reason']}"])
            if brake['status']=='NONCOMPLIANT':add_review(lines,'brake',failed_checks=failed_checks)
            selected=number('selected_motor')
            motor_panel=self.winfo_toplevel()._elevator_app.motor_panel
            # 역산 모드에서 P 입력값은 필요동력 계산 결과가 아니므로 비교하지 않는다.
            raw=motor_panel.entries['P'].get().strip() if motor_panel._target_key()=='P' else ''
            needed=parse_number(raw,'필요동력') if raw else None
            lines.extend(['','[전동기 선정 — 설계용량, 법정 판정 아님]'])
            if needed is None or selected is None:lines.append('선정값과 필요동력이 모두 있어야 용량을 비교할 수 있습니다.')
            else:
                capacity=evaluate_motor_capacity(needed,selected)
                label='설계용량 충족' if capacity['adequate'] else '설계용량 부족'
                lines.append(f'선정 {selected:g} kW ≥ 필요 {needed:g} kW: {label}' if capacity['adequate'] else f'선정 {selected:g} kW < 필요 {needed:g} kW: {label} ({capacity["shortfall_kw"]:.4f} kW 부족)')
                if not capacity['adequate']:add_review(lines,'motor')
            lines.extend(['',INTERNAL_NOTICE,'적용기준·제조사 설계도서 및 시험기록과 대조 필요. 검사기관의 최종 판정 대상.',f'출처: {KC_SOURCE} / {KC_URL}'])
            self._show('\n'.join(lines))
            if (any(str(value).strip() for key,value in self.capture_state().items() if not key.startswith('__')) or
                self.drive.get()!='권상식' or self.speed_conditions.get() or
                any(var.get()!='자료 없음' for var in self.brake_checks.values())):
                self._remember(f"로프: {rope['status']} / 브레이크: {brake['status']}")
        except (ValueError,OverflowError) as e:self._show(f'입력 오류: {e}',True)


class SCurvePanel(tk.Frame):
    """기존 기계동력 곡선과 같은 운행 조건의 전기에너지 비교."""
    ENERGY_FIELDS=(('car_mass','카 질량 kg','1000'),('load_mass','적재 질량 kg','500'),
                   ('counterweight_mass','균형추 질량 kg','1500'),('equivalent_extra_mass','로프·회전부 등가질량 kg','300'),
                   ('resistance','이동 저항력 N','100'),('drive_efficiency','구동 효율 (0~1)','0.85'),
                   ('regen_efficiency','회생 효율 (0~1; 미설치 0)','0'),('auxiliary_kw','운행 중 보조전력 kW','0.15'),
                   ('ref_vmax','기준 최고속도 m/s','2'),('ref_amax','기준 최대 가속도 m/s²','1'),
                   ('ref_jerk','기준 저크 m/s³','0.8'),('candidate_vmax','후보 최고속도 m/s','2'),
                   ('candidate_amax','후보 최대 가속도 m/s²','0.8'),('candidate_jerk','후보 저크 m/s³','0.6'))
    def __init__(self,parent,store):
        super().__init__(parent,bg='white');self.entries={};self.storage_key='scurve';self.store=store;self.undo_stack=[]
        self._profile=None;self._energy_profile=None;self._reference_energy_profile=None
        self.mode_tabs=ttk.Notebook(self);self.mode_tabs.pack(fill='both',expand=True)
        basic=tk.Frame(self.mode_tabs,bg='white');energy=tk.Frame(self.mode_tabs,bg='white')
        self.mode_tabs.add(basic,text='기계동력 곡선');self.mode_tabs.add(energy,text='전기에너지 비교')
        tk.Label(basic,text='대칭 S-Curve: 일정 저크로 가감속하는 단순화 운행 모델',bg='white',font=('맑은 고딕',11,'bold')).pack(anchor='w',padx=10,pady=8)
        for key,label,default in (('distance','운행거리 m','30'),('vmax','설정 최고속도 m/s','2'),('amax','최대 가속도 m/s²','1'),('jerk','저크 한계 m/s³','0.8'),('mass','등가 이동질량 kg','1500'),('force','불평형·저항 합력 N','0')):
            row=tk.Frame(basic,bg='white');row.pack(anchor='w',padx=10,pady=2)
            tk.Label(row,text=label,width=27,anchor='w',bg='white').pack(side='left')
            entry=tk.Entry(row,width=14);attach_numeric_validation(entry);entry.insert(0,default);entry.pack(side='left');self.entries[key]=entry
            entry.bind('<Return>',lambda _event:self.calculate(record=True))
        tk.Button(basic,text='시뮬레이션 실행',command=lambda:self.calculate(record=True)).pack(anchor='w',padx=10,pady=5)
        self.plot=tk.Canvas(basic,height=255,highlightthickness=0);self.plot.pack(fill='x',padx=10,pady=(0,5))
        self._simulation_actions(basic,'mechanical')
        self.plot.bind('<Configure>',lambda _event:self._queue_plot_redraw('mechanical'))
        self.result_text=create_result_display(basic)
        self._show('예상 기계동력만 계산합니다. 전기에너지는 오른쪽 비교 탭에서 계산합니다.')
        self._build_energy(energy)
        self.default_state=self.capture_state()
    def _build_energy(self,host):
        self.energy_entries={};self.measurement_paths={};self.direction=tk.StringVar(value='상승')
        outer=tk.Frame(host,bg='white');outer.pack(fill='x')
        canvas=tk.Canvas(outer,height=290,highlightthickness=0,bg='white')
        scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='x',expand=True)
        form=tk.Frame(canvas,bg='white');canvas.create_window((0,0),window=form,anchor='nw')
        form.bind('<Configure>',lambda _event:canvas.configure(scrollregion=canvas.bbox('all')))
        tk.Label(form,text='운행거리: 기계동력 탭의 입력값 사용. 나머지 하중·방향·효율은 두 곡선에 동일 적용.',bg='white').pack(anchor='w',padx=10,pady=4)
        row=tk.Frame(form,bg='white');row.pack(anchor='w',padx=10)
        tk.Label(row,text='운행 방향',width=27,anchor='w',bg='white').pack(side='left')
        ttk.Combobox(row,textvariable=self.direction,values=('상승','하강'),state='readonly',width=13).pack(side='left')
        for key,label,default in self.ENERGY_FIELDS:
            row=tk.Frame(form,bg='white');row.pack(anchor='w',padx=10,pady=2)
            tk.Label(row,text=label,width=27,anchor='w',bg='white').pack(side='left')
            entry=tk.Entry(row,width=15);attach_numeric_validation(entry);entry.insert(0,default);entry.pack(side='left')
            entry.bind('<Return>',lambda _event:self.calculate_energy(record=True));self.energy_entries[key]=entry
        for key,label in (('reference','기준 실측 CSV'),('candidate','후보 실측 CSV')):
            row=tk.Frame(form,bg='white');row.pack(anchor='w',padx=10,pady=2)
            tk.Label(row,text=label,width=27,anchor='w',bg='white').pack(side='left')
            entry=tk.Entry(row,width=40);entry.pack(side='left');self.measurement_paths[key]=entry
            tk.Button(row,text='찾기',command=lambda e=entry:self._choose_measurement(e)).pack(side='left')
        fields=list(self.energy_entries.values())+list(self.measurement_paths.values())
        for entry in fields:
            entry.bind('<Tab>',lambda event:self._energy_focus(event,fields,1))
            entry.bind('<Shift-Tab>',lambda event:self._energy_focus(event,fields,-1))
        tk.Button(host,text='시뮬레이션 실행',command=lambda:self.calculate_energy(record=True)).pack(anchor='w',padx=10,pady=4)
        self.energy_plot=tk.Canvas(host,height=235,highlightthickness=0);self.energy_plot.pack(fill='x',padx=10)
        self.energy_plot.bind('<Configure>',lambda _event:self._queue_plot_redraw('electrical'))
        self._simulation_actions(host,'electrical')
        self.energy_result=create_result_display(host)
        self._show_energy('예측 비교입니다. 실측 두 운행 CSV가 없으면 절감 성능 검증으로 표시하지 않습니다.')
    def _simulation_actions(self,host,mode):
        bar=tk.Frame(host,bg='white');bar.pack(fill='x',padx=10,pady=(0,5))
        for label,action in (
            ('이전 시뮬레이션',lambda:self._load_previous_simulation(mode)),
            ('시뮬레이션 기록',self._show_simulation_history),
            ('시뮬레이션 삭제',lambda:self._delete_displayed_simulation(mode)),
            ('시뮬레이션 복사 (PNG)',lambda:self._save_simulation_png(mode))):
            tk.Button(bar,text=label,command=action).pack(side='left',padx=(0,6))

    def _record_simulation(self,mode,summary):
        self.store.add_simulation(mode,self.capture_state(),summary)

    def _load_simulation_record(self,record):
        state=record.get('__state__')
        if not isinstance(state,dict):return
        self.apply_state(state)
        mode=record.get('__simulation_mode__','mechanical')
        self.mode_tabs.select(1 if mode=='electrical' else 0)
        if mode=='electrical':self.calculate_energy()
        else:self.calculate()

    def _load_previous_simulation(self,mode):
        records=self.store.simulation_history(mode)
        if not records:
            messagebox.showinfo('이전 시뮬레이션','저장된 시뮬레이션이 없습니다.',parent=self)
            return
        self._load_simulation_record(records[-1][1])

    def _delete_displayed_simulation(self,mode):
        if mode=='electrical':
            self._energy_profile=None;self._reference_energy_profile=None
            self.redraw_energy_plot();self._show_energy('화면의 시뮬레이션을 삭제했습니다. 저장된 기록은 기록창에서 삭제할 수 있습니다.')
        else:
            self._profile=None;self.redraw_plot()
            self._show('화면의 시뮬레이션을 삭제했습니다. 저장된 기록은 기록창에서 삭제할 수 있습니다.')

    def _show_simulation_history(self):
        window=tk.Toplevel(self);window.title('시뮬레이션 기록')
        window.transient(self.winfo_toplevel())
        WindowManager.center(window,self.winfo_toplevel(),780,480)
        frame=tk.Frame(window);frame.pack(fill='both',expand=True,padx=12,pady=12)
        tree=ttk.Treeview(frame,columns=('time','mode','summary'),show='headings',selectmode='browse')
        for key,label,width in (('time','저장 시각',150),('mode','종류',100),('summary','결과',480)):
            tree.heading(key,text=label);tree.column(key,width=width,anchor='w')
        scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        def refresh():
            for item in tree.get_children():tree.delete(item)
            for index,record in reversed(self.store.simulation_history()):
                mode='전기에너지 비교' if record['__simulation_mode__']=='electrical' else '기계동력'
                tree.insert('', 'end',iid=str(index),values=(record.get('__timestamp__',''),mode,record.get('__result_summary__','')))
        def selected():
            ids=tree.selection()
            if not ids:
                messagebox.showinfo('시뮬레이션 기록','기록을 하나 선택하세요.',parent=window)
                return None
            return int(ids[0])
        def load():
            index=selected()
            if index is None:return
            history=self.store.data['calculators']['scurve']['history']
            if index<len(history):self._load_simulation_record(history[index]);window.destroy()
        def delete():
            index=selected()
            if index is None:return
            if not messagebox.askyesno('기록 삭제','선택한 시뮬레이션 기록을 삭제할까요?',parent=window):return
            self.store.delete_simulation(index);refresh()
        row=tk.Frame(window);row.pack(fill='x',padx=12,pady=(0,10))
        tk.Button(row,text='불러오기',command=load).pack(side='left',padx=4)
        tk.Button(row,text='선택 기록 삭제',command=delete).pack(side='left',padx=4)
        tk.Button(row,text='닫기',command=window.destroy).pack(side='right',padx=4)
        tree.bind('<Double-1>',lambda _event:load())
        refresh()

    def _save_simulation_png(self,mode):
        profile=self._energy_profile if mode=='electrical' else self._profile
        reference=self._reference_energy_profile if mode=='electrical' else None
        if profile is None or (mode=='electrical' and reference is None):
            messagebox.showinfo('PNG 저장','먼저 시뮬레이션을 실행하세요.',parent=self)
            return
        path=filedialog.asksaveasfilename(parent=self,title='그래프 PNG 저장',defaultextension='.png',
            initialfile='승강기_전기에너지비교.png' if mode=='electrical' else '승강기_S-Curve.png',
            filetypes=[('PNG 이미지','*.png')])
        if not path:return
        try:
            palette=get_theme(self)[1]
            try:
                from plot_render import render_plot
            except ImportError:
                from native_plot import render_png
                Path(path).write_bytes(render_png(profile,palette,reference,size=(1100,440)))
            else:
                render_plot(profile,palette,reference,size=(1100,440),scale=2).save(path,format='PNG')
        except (OSError,ValueError) as error:
            messagebox.showerror('PNG 저장 실패',str(error),parent=self)
        else:
            messagebox.showinfo('PNG 저장',f'그래프를 저장했습니다.\n{path}',parent=self)

    def _energy_focus(self,event,fields,direction):
        focus_input_for_replacement(fields[(fields.index(event.widget)+direction)%len(fields)])
        return 'break'
    def _choose_measurement(self,entry):
        path=filedialog.askopenfilename(parent=self,title='실측 운행 CSV 선택',filetypes=[('CSV','*.csv')])
        if path:entry.delete(0,tk.END);entry.insert(0,path)
    def _show(self,s,error=False):set_result_display(self.result_text,s,error)
    def _show_energy(self,s,error=False):set_result_display(self.energy_result,s,error)
    def _queue_plot_redraw(self,mode):
        key='_pending_'+mode+'_redraw'
        pending=getattr(self,key,None)
        if pending is not None:self.after_cancel(pending)
        action=self.redraw_energy_plot if mode=='electrical' else self.redraw_plot
        def render():
            setattr(self,key,None)
            action()
        setattr(self,key,self.after(80,render))
    def redraw_plot(self):
        if hasattr(self,'plot'):draw_scurve_plot(self.plot,self._profile,get_theme(self.plot)[1])
    def redraw_energy_plot(self):
        if hasattr(self,'energy_plot'):
            draw_energy_comparison(self.energy_plot,self._reference_energy_profile,self._energy_profile,get_theme(self.energy_plot)[1])
    def capture_state(self):
        state={key:entry.get() for key,entry in self.entries.items()}
        if hasattr(self,'energy_entries'):
            state['_energy']={key:entry.get() for key,entry in self.energy_entries.items()}
            state['_direction']=self.direction.get()
            state['_measurement_paths']={key:entry.get() for key,entry in self.measurement_paths.items()}
        return state
    def apply_state(self,state,remember_undo=True):
        if not isinstance(state,dict):return
        if remember_undo:push_undo_state(self)
        for key,entry in self.entries.items():
            entry.delete(0,tk.END);entry.insert(0,str(state.get(key,'')))
        if hasattr(self,'energy_entries'):
            energy=state.get('_energy',{})
            defaults={key:default for key,_,default in self.ENERGY_FIELDS}
            for key,entry in self.energy_entries.items():
                entry.delete(0,tk.END);entry.insert(0,str(energy.get(key,defaults[key])))
            self.direction.set(state.get('_direction','상승'))
            paths=state.get('_measurement_paths',{})
            for key,entry in self.measurement_paths.items():
                entry.delete(0,tk.END);entry.insert(0,str(paths.get(key,'')))
    def undo_last(self):undo_panel(self)
    def clear(self):
        push_undo_state(self)
        for entry in (*self.entries.values(),*getattr(self,'energy_entries',{}).values(),*getattr(self,'measurement_paths',{}).values()):entry.delete(0,tk.END)
        self._show('입력값을 삭제했습니다.')
        if hasattr(self,'energy_result'):self._show_energy('입력값을 삭제했습니다.')
    def calculate_energy(self,record=False,precomputed=None,premeasurements=None):
        try:
            values={key:parse_number(entry.get(),key) for key,entry in self.energy_entries.items()}
            shared=dict(distance=parse_number(self.entries['distance'].get(),'운행거리'),
                        car_mass=values['car_mass'],load_mass=values['load_mass'],
                        counterweight_mass=values['counterweight_mass'],equivalent_extra_mass=values['equivalent_extra_mass'],
                        resistance=values['resistance'],direction=self.direction.get(),
                        drive_efficiency=values['drive_efficiency'],regen_efficiency=values['regen_efficiency'],
                        auxiliary_kw=values['auxiliary_kw'])
            result=(precomputed if precomputed is not None else
                compare_trips(shared,dict(vmax=values['ref_vmax'],amax=values['ref_amax'],jerk=values['ref_jerk']),
                              dict(vmax=values['candidate_vmax'],amax=values['candidate_amax'],jerk=values['candidate_jerk'])))
            self._reference_energy_profile=result['reference'];self._energy_profile=result['candidate'];self.redraw_energy_plot()
            lines=['[동일 조건 두 곡선의 전기에너지 추정]',
                   '일정 효율·일정 저항의 단순 모델. 실측 없이 제조사 절감 성능으로 해석할 수 없습니다.',
                   f"운행거리 {shared['distance']:g} m · {shared['direction']} · 적재 {shared['load_mass']:g} kg"]
            for label,key in (('기준','reference'),('후보','candidate')):
                p=result[key]
                lines.append(f"{label}: 운행 {p['duration_s']:.2f} s / 실제 최고속도 {p['peak_speed_m_s']:.3f} m/s / "
                             f"구동 {p['draw_kwh']:.6f}, 회수 {p['returned_kwh']:.6f}, 보조 {p['auxiliary_kwh']:.6f} kWh → 순 {p['net_kwh']:.6f} kWh")
            percent=(f"{result['difference_pct']:+.2f}% (모델 추정)" if result['difference_pct'] is not None else '기준 순사용량 ≤ 0: 비율 미표시')
            lines.append(f"순 사용량 차이(기준−후보): {result['difference_kwh']:+.6f} kWh / {percent}")
            lines.append(f"운행시간 차이(후보−기준): {result['candidate']['duration_s']-result['reference']['duration_s']:+.2f} s")
            measurements={}
            for key,label in (('reference','기준'),('candidate','후보')):
                path=self.measurement_paths[key].get().strip()
                if path:
                    m=(premeasurements[key] if premeasurements is not None else
                       read_measurement(path,result[key]));measurements[key]=m
                    error=(f"{m['energy_error_pct']:+.2f}%" if m['energy_error_pct'] is not None else '실측 0: 비율 미표시')
                    lines.append(f"{label} 실측: {m['measured_kwh']:.6f} kWh / 예측 오차 {m['energy_error_kwh']:+.6f} kWh ({error}) / 속도 RMSE {m['speed_rmse_m_s']:.3f} m/s")
            if len(measurements)==2:
                measured=measurements['reference']['measured_kwh']-measurements['candidate']['measured_kwh']
                lines.append(f'두 실측 운행 사용량 차이(기준−후보): {measured:+.6f} kWh (해당 한 쌍만)')
            else:lines.append('실측 두 운행이 없으므로 절감률은 모델 추정치입니다.')
            lines.append('※ 운행시간·승차감·정지 오차를 별도로 확인해야 합니다.')
            self._show_energy('\n'.join(lines))
            if record:self._record_simulation('electrical',f"순 사용량 {result['candidate']['net_kwh']:.6f} kWh")
            return result
        except (ValueError,OverflowError,OSError) as error:
            self._energy_profile=None;self._reference_energy_profile=None;self.redraw_energy_plot();self._show_energy(f'입력/실측 오류: {error}',True)
            return None
        except Exception as error:
            log_unexpected_error('전기에너지 시뮬레이션',error)
            self._show_energy('계산 오류가 발생했습니다. 오류 로그를 확인하세요.',True)
            return None
    def calculate(self,record=False,precomputed=None):
        try:
            p=(precomputed if precomputed is not None else
               scurve_profile(*(parse_number(self.entries[k].get(),k) for k in ('distance','vmax','amax','jerk','mass','force'))))
            self._profile=p;self.redraw_plot()
            rows=p['samples'];stride=max(1,len(rows)//18)
            lines=['[단순화 S-Curve 운행 결과]',f"운행시간 {p['duration_s']:.2f} s / 최고속도 {p['peak_speed_m_s']:.3f} m/s / 정속 구간 {p['cruise_s']:.2f} s",f"최고 예상 기계동력(절댓값) {p['peak_mechanical_kw']:.2f} kW",f"구동 구간 기계적 일 {p['motoring_mechanical_wh']:.2f} Wh / 제동 구간 기계적 일 {p['braking_mechanical_wh']:.2f} Wh",'', '시간 s | 위치 m | 속도 m/s | 가속도 m/s² | 예상 기계동력 kW']
            lines.extend(f'{t:7.2f} | {x:7.2f} | {v:7.3f} | {a:8.3f} | {power:7.2f}' for t,x,v,a,power in rows[::stride])
            lines.extend(['','※ F=(등가 이동질량×가속도)+입력한 불평형 합력, P=F×v로 계산한 기계적 일입니다. 제동 구간 수치는 회생 가능한 전기에너지가 아닙니다.','※ 구동 효율·회생 경로·손실·대기전력을 반영하지 않습니다. S-Curve만으로 에너지 절감을 판정할 수 없습니다.'])
            self._show('\n'.join(lines))
            if record:self._record_simulation('mechanical',f"운행 {p['duration_s']:.2f} s / 최고속도 {p['peak_speed_m_s']:.3f} m/s")
        except (ValueError,OverflowError) as error:
            self._profile=None;self.redraw_plot();self._show(f'입력 오류: {error}',True)
        except Exception as error:
            log_unexpected_error('기계동력 시뮬레이션',error)
            self._show('계산 오류가 발생했습니다. 오류 로그를 확인하세요.',True)


class ElevatorApp:
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
        self.criteria_panel = CriteriaPanel(self.notebook, self.store)
        self.notebook.add(self.criteria_panel, text="KC 기준 검토")
        self.scurve_panel = SCurvePanel(self.notebook, self.store)
        self.notebook.add(self.scurve_panel, text="S-Curve 시뮬레이션")
        self.root._elevator_app = self
        self.panels = [self.motor_panel, self.traction_panel,
                       self.brake_panel, self.traffic_panel]
        # 자동 전달값은 사용자가 직접 수정한 값을 덮어쓰지 않도록
        # '프로그램이 마지막으로 자동 입력한 값'을 항목별로 따로 기억합니다.
        self._auto_filled_values = {}
        self._last_tab_index = 0
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
            for key, entry in entries:
                # 메모칸에는 공백을 입력할 수 있게 유지하고, 모든 입력칸에 Tab 이동을 연결합니다.
                if not (panel is self.traffic_panel and key == "criterion_source"):
                    entry.bind("<space>", self._shortcut_next_tab, add="+")
                entry.bind("<Tab>", lambda e, p=panel: self._focus_adjacent_input(p, e.widget, 1), add="+")
                entry.bind("<Shift-Tab>", lambda e, p=panel: self._focus_adjacent_input(p, e.widget, -1), add="+")
                entry.bind("<ISO_Left_Tab>", lambda e, p=panel: self._focus_adjacent_input(p, e.widget, -1), add="+")
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
        return [key for key, _value in planned]

    def on_tab_changed(self, _event=None):
        """탭 이동 시 의미와 단위가 같은 공통값만 다음 계산창으로 전달합니다."""
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

    def _shortcut_calculate(self, _event=None):
        self.active_panel().calculate()
        return "break"

    def _shortcut_clear(self, _event=None):
        panel = self.active_panel()
        clear_command = getattr(panel, "clear", None) or getattr(panel, "reset", None)
        if clear_command:
            clear_command()
        return "break"

    def _shortcut_undo(self, _event=None):
        self.active_panel().undo_last()
        return "break"

    def _shortcut_history(self, _event=None):
        self.active_panel().show_history()
        return "break"

    def _shortcut_projects(self, _event=None):
        self.open_project_manager()
        return "break"

    def _shortcut_integrated(self, _event=None):
        self.calculate_all()
        return "break"

    def _shortcut_next_tab(self, event=None):
        """Space 또는 Ctrl+Right로 네 계산 탭을 순서대로 순환합니다."""
        focus = self.root.focus_get()
        if focus is not None and focus.winfo_toplevel() is not self.root:
            return None
        if event is not None and event.keysym == "space":
            # 문자 입력칸과 버튼에서 필요한 공백/클릭 동작은 가로채지 않습니다.
            if isinstance(focus, (tk.Text, ttk.Combobox, tk.Button)):
                return None
            if isinstance(focus, tk.Entry):
                # 교통량의 메모 입력칸은 실제 문장에 공백이 필요합니다.
                if focus is self.traffic_panel.entries.get("criterion_source"):
                    return None
        try:
            current = self.notebook.index(self.notebook.select())
            next_index = (current + 1) % self.notebook.index("end")
            self.notebook.select(next_index)
            panels = self.panels + [self.criteria_panel, self.scurve_panel]
            self.root.after_idle(lambda i=next_index: self._focus_first_input(panels[i]))
        except (tk.TclError, IndexError):
            return None
        return "break"

    def _focus_first_input(self, panel):
        """탭 이동 직후 첫 번째 사용 가능한 입력칸에 커서를 놓습니다."""
        for entry in getattr(panel, "entries", {}).values():
            try:
                if str(entry.cget("state")) != "disabled" and entry.winfo_viewable():
                    focus_input_for_replacement(entry)
                    return
            except (tk.TclError, AttributeError):
                continue

    def _focus_adjacent_input(self, panel, current, direction=1):
        entries = []
        candidates = list(getattr(panel, "entries", {}).values())
        if panel is self.criteria_panel:
            candidates += list(panel.traction_entries.values())
        for entry in candidates:
            try:
                if str(entry.cget("state")) != "disabled" and entry.winfo_viewable():
                    entries.append(entry)
            except (tk.TclError, AttributeError):
                pass
        if not entries:
            return "break"
        try:
            index = entries.index(current)
        except ValueError:
            index = -1 if direction > 0 else 0
        target_index = index + direction
        if 0 <= target_index < len(entries):
            target = entries[target_index]
            focus_input_for_replacement(target)
        else:
            # 마지막 입력칸에서 Tab을 누르면 다음 계산창으로 넘어가고 첫 입력칸에 즉시 포커스합니다.
            current_tab = self.notebook.index(self.notebook.select())
            next_tab = (current_tab + (1 if direction > 0 else -1)) % self.notebook.index("end")
            self.notebook.select(next_tab)
            panels = self.panels + [self.criteria_panel, self.scurve_panel]
            self.root.after_idle(lambda i=next_tab: self._focus_first_input(panels[i]))
        return "break"

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
        raw = state.get("values", {}).get(key, "")
        if str(raw).strip() == "":
            return None
        try:
            return parse_number(raw, key)
        except ValueError:
            return None

    def _project_snapshot(self):
        """여섯 탭의 입력과 선택 상태를 각각 보존해 저장 자료를 만든다."""
        states = {
            "motor": copy.deepcopy(self.motor_panel.capture_state()),
            "traction": copy.deepcopy(self.traction_panel.capture_state()),
            "brake": copy.deepcopy(self.brake_panel.capture_state()),
            "traffic": copy.deepcopy(self.traffic_panel.capture_state()),
            "criteria": copy.deepcopy(self.criteria_panel.capture_state()),
            "scurve": copy.deepcopy(self.scurve_panel.capture_state()),
        }
        motor = states["motor"]
        traction = states["traction"]
        brake = states["brake"]
        criteria = states["criteria"]
        active_key = ("motor", "traction", "brake", "traffic", "criteria", "scurve")[
            self.notebook.index(self.notebook.select())]

        def first_value(candidates):
            ordered = sorted(candidates, key=lambda item: item[0] != active_key)
            for source, state, key in ordered:
                value = self._state_number(state, key)
                if value is not None:
                    return value
            return None

        q_value = first_value((("motor", motor, "Q"), ("traction", traction, "Q")))
        ob_value = first_value((("motor", motor, "OB"), ("traction", traction, "OB")))
        wc_value = self._state_number(traction, "Wc")
        rope_count = self._state_number(traction, "n")
        if active_key == "criteria" and criteria.get("__drive__", "권상식") == "권상식":
            rope_count = self._state_number({"values": criteria}, "count") or rope_count

        speed_ms = None
        motor_speed = self._state_number(motor, "V")
        criteria_speed = self._state_number({"values": criteria}, "rated")
        if active_key == "criteria" and criteria_speed is not None:
            speed_ms = criteria_speed
        elif motor_speed is not None:
            speed_ms = motor_speed / (60 if motor.get("units", {}).get("V") == "m/min" else 1)
        elif criteria_speed is not None:
            speed_ms = criteria_speed

        if q_value is not None:
            motor["values"]["Q"] = clean_number_text(q_value)
            traction["values"]["Q"] = clean_number_text(q_value)
        if ob_value is not None:
            motor["values"]["OB"] = clean_number_text(ob_value)
            traction["values"]["OB"] = clean_number_text(ob_value)
        if speed_ms is not None:
            motor_factor = 60 if motor.get("units", {}).get("V") == "m/min" else 1
            if not str(motor["values"].get("V", "")).strip() or active_key == "criteria":
                motor["values"]["V"] = clean_number_text(speed_ms * motor_factor)
            if not str(criteria.get("rated", "")).strip() or active_key == "motor":
                criteria["rated"] = clean_number_text(speed_ms)
        if rope_count is not None:
            if not str(traction["values"].get("n", "")).strip() or active_key == "criteria":
                traction["values"]["n"] = clean_number_text(rope_count)
            if criteria.get("__drive__", "권상식") == "권상식" and (
                    not str(criteria.get("count", "")).strip() or active_key == "traction"):
                criteria["count"] = clean_number_text(rope_count)
        common = {"Q": q_value, "OB": ob_value, "Wc": wc_value,
                  "speed_m_s": speed_ms, "rope_count": rope_count}
        return states, common

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
                    log_unexpected_error(error)
        finally:
            self.store._suppress_history = False

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
