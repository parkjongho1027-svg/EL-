"""트랙션비 입력·기록·결과 패널. 공통 창 도우미를 명시적으로 전달한다."""
from dataclasses import dataclass
from typing import Any, Callable
import math
import tkinter as tk

from src.core.calculators import calculate_traction_values
from src.ui.engineering_charts import show_tension
from src.ui.graph_workspace import manage_graphs, save_current_graph
from src.ui.ui_components import SkyButton, attach_numeric_validation
from src.common.utils import (parse_number, ensure_positive, require_calculation, calculate_safely)


@dataclass(frozen=True)
class TractionPanelServices:
    create_calculation_layout: Callable[..., Any]
    create_action_buttons: Callable[..., Any]
    create_result_display: Callable[..., Any]
    initial_result_text: Callable[..., Any]
    set_result_display: Callable[..., Any]
    push_undo_state: Callable[..., Any]
    widget_language: Callable[..., Any]
    open_history_window: Callable[..., Any]
    undo_panel: Callable[..., Any]
    show_unexpected_error: Callable[..., Any]
    log_unexpected_error: Callable[..., Any]


class IntegratedTractionPanel(tk.Frame):
    """문제에서 주어진 값만 한 번 입력하는 트랙션비 통합 계산 화면.

    계산 순서:
    입력값 → 균형추 중량 → 로프 총중량 → 전반부/후반부 트랙션비
    → 둘 중 큰 값을 최종 트랙션비로 선택
    """
    def __init__(self, parent, store, services):
        super().__init__(parent, bg="white")
        self.store = store
        self.services = services
        self.storage_key = "traction"

        note = ("문제에서 주어진 값만 입력하면 균형추·로프·전반부·후반부·최종 트랙션비를 한 번에 계산합니다.\n"
                "※ 문제에 값이 없으면 보상체인 중량과 이동케이블 중량은 0으로 입력합니다.")
        left, right = self.services.create_calculation_layout(self, note, formula_key="traction")
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

        action_buttons = self.services.create_action_buttons(
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

        self.result_text = self.services.create_result_display(right)
        self._show(self.services.initial_result_text(self))

        chart_actions = tk.Frame(left, bg='white')
        chart_actions.pack(anchor='w', fill='x', padx=9, pady=3)
        for title, action in (
            ('로프 장력 분포 그래프', lambda: show_tension(self)),
            ('그래프 관리', lambda: manage_graphs(self, 'traction')),
            ('그래프 저장', lambda: save_current_graph(self, 'traction')),
        ):
            SkyButton(chart_actions, text=title, command=action,
                      font=('맑은 고딕', 9)).pack(side='left', padx=(0, 4))

    def _show(self, text, error=False):
        self.services.set_result_display(self.result_text, text, error)

    def _remember(self, values, result_summary):
        """성공적으로 계산한 입력값만 영구 기록에 저장합니다."""
        self.input_history = self.store.add_history(
            self.storage_key, values, result_summary
        )
        self.previous_values = self.store.previous(self.storage_key)
        self.previous_button.config(state="normal")
        self.history_button.config(state="normal")

    def reset(self):
        self.services.push_undo_state(self)
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
                   if self.services.widget_language(self) == "en" else
                   "입력값을 삭제했습니다. 보상체인·이동케이블은 기본값 0입니다.\n"
                   "삭제 직전 값은 ‘이전 입력값’ 버튼으로 복원할 수 있습니다.")
        self.entries["Q"].focus_set()
        self.entries["Q"].selection_range(0, tk.END)

    def restore_previous(self):
        """가장 최근에 계산했거나 삭제하기 전에 입력했던 값을 복원합니다."""
        if self.previous_values is None:
            return
        self.services.push_undo_state(self)
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, self.previous_values.get(key, ""))
        self._show("Previous inputs loaded. Check the values, then calculate."
                   if self.services.widget_language(self) == "en" else
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
        self.services.open_history_window(self, "트랙션비 입력 기록", self.input_history,
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
        self.services.push_undo_state(self)
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, record.get(key, ""))
        clean_record = {key: record.get(key, "") for key in self.entries}
        self.store.set_previous(self.storage_key, clean_record)
        self.previous_values = self.store.previous(self.storage_key)
        self._show((f"Input record {record_number} loaded. Check the values, then calculate."
                    if self.services.widget_language(self) == "en" else
                    f"입력 기록 {record_number}번을 불러왔습니다. 값을 확인한 뒤 계산하세요."))
        self.entries["Q"].focus_set()
        self.entries["Q"].selection_range(0, tk.END)

    def capture_state(self):
        return {"values": {key: entry.get() for key, entry in self.entries.items()}}

    def apply_state(self, state, remember_undo=True):
        if remember_undo:
            self.services.push_undo_state(self)
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, state.get("values", {}).get(key, self.defaults.get(key, "")))

    def undo_last(self):
        self.services.undo_panel(self)

    def calculate(self):
        english = self.services.widget_language(self) == "en"
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
            english = self.services.widget_language(self) == "en"
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
                       if self.services.widget_language(self) == "en" else
                       "오류: 계산식의 분모가 0입니다. 입력값을 확인하세요.", error=True)
        except ValueError as e:
            self._show("Input error: Check required values, units, and valid ranges."
                       if self.services.widget_language(self) == "en" else f"입력 오류: {e}", error=True)
        except Exception as e:
            if self.services.widget_language(self) == "en":
                self.services.log_unexpected_error("Traction ratio calculation", e)
                self._show("Unexpected calculation error. Check the error log.", error=True)
            else:
                self.services.show_unexpected_error(self, "트랙션비 계산", e)
