"""브레이크 제동 입력/결과 화면. 공통 화면 서비스는 호출자가 주입한다."""
from dataclasses import dataclass
from typing import Any, Callable
import math
import tkinter as tk
from tkinter import ttk

from src.core.calculators import calculate_brake_values
from src.ui.ui_components import attach_numeric_validation
from src.ui.theme_manager import bind_combobox_popdown_theme
from src.common.utils import parse_number, require_calculation, calculate_safely


@dataclass(frozen=True)
class BrakePanelServices:
    create_calculation_layout: Callable[..., Any]
    create_action_buttons: Callable[..., Any]
    create_result_display: Callable[..., Any]
    initial_result_text: Callable[..., Any]
    set_result_display: Callable[..., Any]
    push_undo_state: Callable[..., Any]
    widget_language: Callable[..., Any]
    show_unexpected_error: Callable[..., Any]
    open_history_window: Callable[..., Any]
    undo_panel: Callable[..., Any]
    initial_result_message: str


class BrakePanel(tk.Frame):
    """네 물리량 중 사용자가 입력한 두 값을 찾아 나머지 두 값을 계산합니다.

    계산 결과를 입력칸에 다시 쓰지 않고 결과 영역에만 표시하여,
    이전 계산 결과가 다음 계산의 입력값으로 잘못 사용되는 것을 방지합니다.
    """
    def __init__(self, parent, store, services):
        super().__init__(parent, bg="white")
        self.store = store
        self.services = services
        self.storage_key = "brake"

        note = ("속도(v), 제동시간(t), 제동거리(d), 감속도(a) 중 알고 있는 값 2개 이상을 입력하세요.\n"
                "※ 일정한 감속도로 정지한다고 가정합니다. 3개 이상 입력하면 공식 일치 여부도 검사합니다.\n"
                "※ 속도 단위는 입력칸 옆에서 m/s 또는 m/min을 선택할 수 있습니다.")
        left, right = self.services.create_calculation_layout(self, note, formula_key="brake")
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

        action_buttons = self.services.create_action_buttons(
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

        self.initial_result_message = services.initial_result_message
        self.result_text = self.services.create_result_display(right)
        self._show(self.services.initial_result_text(self))

    def _show(self, text, error=False):
        """브레이크 결과와 오류를 공통 결과창 형식으로 표시합니다."""
        self.services.set_result_display(self.result_text, text, error)

    def on_speed_unit_change(self, _event=None):
        """브레이크 속도 단위를 바꿀 때 같은 입력칸의 숫자도 즉시 변환합니다."""
        self.services.push_undo_state(self)
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
                           if self.services.widget_language(self) == "en" else f"입력 오류: {error}", error=True)
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
        english = self.services.widget_language(self) == "en"
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
            self.services.show_unexpected_error(self, "브레이크 제동 계산", e)

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
        self.services.push_undo_state(self)
        self.speed_unit.set(self.previous_values.get("__speed_unit__", "m/s"))
        self._last_speed_unit = self.speed_unit.get()
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, self.previous_values.get(key, ""))
        self._show("Previous inputs loaded. Check the values, then calculate."
                   if self.services.widget_language(self) == "en" else
                   "이전 입력값을 불러왔습니다. 값을 확인한 뒤 계산하세요.")
        self.entries["v"].focus_set()

    def show_history(self):
        specs = [("__speed_unit__", "속도 단위", 90), ("v", "속도", 120), ("t", "제동시간(s)", 120),
                 ("d", "제동거리(m)", 120), ("a", "감속도(m/s²)", 140)]
        self.services.open_history_window(self, "브레이크 제동 입력 기록", self.input_history,
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
                    if self.services.widget_language(self) == "en" else
                    f"입력 기록 {record_number}번을 불러왔습니다. 값을 확인한 뒤 계산하세요."))

    def clear(self):
        self.services.push_undo_state(self)
        current = {key: entry.get() for key, entry in self.entries.items()}
        if any(value.strip() for value in current.values()):
            self.store.set_previous(self.storage_key, current)
            self.previous_values = self.store.previous(self.storage_key)
            self.previous_button.config(state="normal")
        for entry in self.entries.values():
            entry.delete(0, tk.END)
        self._show(self.services.initial_result_text(self))
        self.entries["v"].focus_set()

    def capture_state(self):
        return {
            "values": {key: entry.get() for key, entry in self.entries.items()},
            "speed_unit": self.speed_unit.get(),
        }

    def apply_state(self, state, remember_undo=True):
        if remember_undo:
            self.services.push_undo_state(self)
        self.speed_unit.set(state.get("speed_unit", "m/s"))
        self._last_speed_unit = self.speed_unit.get()
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, state.get("values", {}).get(key, ""))

    def undo_last(self):
        self.services.undo_panel(self)


def build_brake_tab(notebook, store, services):
    panel = BrakePanel(notebook, store, services)
    notebook.add(panel, text="브레이크 제동")
    return panel
