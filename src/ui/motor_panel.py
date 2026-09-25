"""전동기 용량 입력 화면과 역산 선택 동작."""

from dataclasses import dataclass
from typing import Any, Callable, Mapping
import math
import tkinter as tk
from tkinter import ttk

from src.ui.theme_manager import get_theme
from src.ui.ui_components import attach_numeric_validation
from src.common.utils import parse_number, calculate_safely, require_calculation


@dataclass(frozen=True)
class MotorPanelServices:
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
    initial_result_message: str
    english_ui: Mapping[str, str]


class SolverPanel(tk.Frame):
    def __init__(
        self,
        parent,
        vars_spec,
        formulas,
        note,
        store,
        storage_key,
        input_validator=None,
        result_validator=None,
        formula_key=None,
        services=None,
    ):
        """
        vars_spec : 화면에 표시할 변수의 이름, 단위, % 여부를 저장한 목록
        formulas  : 사용자가 선택한 '구하고자 하는 값'별 계산식

        예를 들어 전동기 용량 P를 선택하면 P 입력칸은 잠기고,
        나머지 Q, V, OB, 효율을 입력하여 P를 계산하는 방식입니다.
        % 값은 계산 직전에 100으로 나누어 45%를 0.45로 바꿉니다.
        """
        super().__init__(parent, bg="white")
        self.services = services
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
        self.input_area, result_area = self.services.create_calculation_layout(
            self, note, formula_key=formula_key
        )

        top = tk.Frame(self.input_area, bg="white")
        top.pack(anchor="w", pady=(12, 6), padx=10)
        tk.Label(
            top, text="구하고자 하는 값 :", font=("맑은 고딕", 11, "bold"), bg="white"
        ).pack(side="left")

        self.target_combo = ttk.Combobox(
            top,
            values=[v["label"] for v in vars_spec],
            state="readonly",
            width=22,
            font=("맑은 고딕", 11),
        )
        self.target_combo.current(0)
        self.target_combo.pack(side="left", padx=10)
        self.target_combo.bind("<<ComboboxSelected>>", self.on_target_change)

        self.form = tk.Frame(self.input_area, bg="white")
        self.form.pack(anchor="w", padx=10, pady=4)
        for v in vars_spec:
            row = tk.Frame(self.form, bg="white")
            row.pack(anchor="w", pady=3)
            tk.Label(
                row,
                text=v["label"],
                font=("맑은 고딕", 10),
                bg="white",
                width=18,
                anchor="w",
            ).pack(side="left")
            entry = tk.Entry(row, font=("맑은 고딕", 10), width=16, justify="right")
            attach_numeric_validation(entry)
            entry.pack(side="left", padx=5)
            entry.bind("<Return>", lambda _event: self.calculate())
            if v.get("unit_factors"):
                default_unit = v.get("default_unit") or next(iter(v["unit_factors"]))
                unit_var = tk.StringVar(value=default_unit)
                unit_combo = ttk.Combobox(
                    row,
                    textvariable=unit_var,
                    values=list(v["unit_factors"]),
                    state="readonly",
                    width=7,
                    font=("맑은 고딕", 9),
                )
                unit_combo.pack(side="left")
                unit_combo.bind(
                    "<<ComboboxSelected>>",
                    lambda _event, key=v["key"]: self.on_unit_change(key),
                )
                self.unit_vars[v["key"]] = unit_var
                self._last_units[v["key"]] = default_unit
            else:
                unit_text = "%" if v.get("percent") else v.get("unit", "")
                tk.Label(row, text=unit_text, font=("맑은 고딕", 10), bg="white").pack(
                    side="left"
                )
            self.entries[v["key"]] = entry
            self.entry_rows[v["key"]] = row

        action_buttons = self.services.create_action_buttons(
            self.input_area,
            self.calculate,
            [
                ("clear", "입력값 삭제", self.clear, "normal"),
                ("previous", "이전 입력값", self.restore_previous, "disabled"),
                ("history", "입력 기록", self.show_history, "disabled"),
            ],
        )
        self.action_buttons = action_buttons
        self.previous_button = action_buttons["previous"]
        self.history_button = action_buttons["history"]
        if self.previous_values:
            self.previous_button.config(state="normal")
        if self.input_history:
            self.history_button.config(state="normal")

        self.initial_result_message = services.initial_result_message
        self.result_text = self.services.create_result_display(result_area)
        self._show(self.services.initial_result_text(self))

        self.on_target_change()

    def _target_key(self):
        idx = self.target_combo.current()
        return self.vars_spec[idx]["key"]

    def _show(self, text, error=False):
        """전동기 결과와 오류를 공통 결과창 형식으로 표시합니다."""
        self.services.set_result_display(self.result_text, text, error)

    def on_unit_change(self, key):
        """한 입력칸에서 단위를 바꾸면 현재 숫자도 같은 물리량으로 변환합니다."""
        self.services.push_undo_state(self)
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
                self._show(
                    "Input error: Check the value and selected unit."
                    if self.services.widget_language(self) == "en"
                    else f"입력 오류: {error}",
                    error=True,
                )
        self._last_units[key] = new_unit

    def on_target_change(self, event=None):
        # 목표 항목을 바꾸기 전에 현재 값을 모두 보관합니다.
        # 예: P를 계산한 뒤 목표를 Q로 바꾸면, 방금 구한 P는 다음 역산에
        # 그대로 사용할 수 있어야 하므로 새 목표인 Q만 비웁니다.
        if event is not None:
            self.services.push_undo_state(self)
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
                entry.config(
                    state="disabled", disabledbackground=colors["disabled_entry"]
                )
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

            result = require_calculation(
                calculate_safely(self.formulas[target_key], vals)
            )
            if not math.isfinite(result):
                raise ValueError(
                    "계산 결과가 유한한 숫자가 아닙니다. 입력값을 확인하세요."
                )
            if self.result_validator:
                self.result_validator(result, target_key)
            display_val = result * 100 if target_spec.get("percent") else result
            if target_spec.get("unit_factors"):
                display_val = (
                    result
                    / target_spec["unit_factors"][self.unit_vars[target_key].get()]
                )

            # 계산 결과를 목표 입력칸에 쓰기 직전 상태를 보관해 Ctrl+Z로 되돌립니다.
            self.services.push_undo_state(self)
            entry = self.entries[target_key]
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, f"{display_val:.4f}")
            entry.config(state="disabled")
            if sync:
                sync()

            unit = (
                self.unit_vars[target_key].get()
                if target_spec.get("unit_factors")
                else (
                    "%" if target_spec.get("percent") else target_spec.get("unit", "")
                )
            )
            english = self.services.widget_language(self) == "en"
            target_label = (
                self.services.english_ui.get(target_spec["label"], target_spec["label"])
                if english
                else target_spec["label"]
            )
            result_summary = f"{target_label} = {display_val:.4f} {unit}".strip()
            # 계산이 끝난 뒤에만 전체 기록에 추가합니다.
            self._remember_input(target_key, target_spec["label"], result_summary)
            used_values = []
            for spec in self.vars_spec:
                if spec["key"] == target_key:
                    continue
                used_unit = (
                    self.unit_vars[spec["key"]].get()
                    if spec.get("unit_factors")
                    else ("%" if spec.get("percent") else spec.get("unit", ""))
                )
                used_label = (
                    self.services.english_ui.get(spec["label"], spec["label"])
                    if english
                    else spec["label"]
                )
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
                    "",
                    "[Calculation Process]" if english else "[계산 과정]",
                    (
                        "1. Check the entered values and units."
                        if english
                        else "1. 입력값과 단위를 확인합니다."
                    ),
                    (
                        "2. Convert speed to the formula base unit (m/min)."
                        if english
                        else "2. 속도를 계산식 기준 단위(m/min)로 통일합니다."
                    ),
                    ("3. Apply formula: " if english else "3. 공식 적용: ")
                    + formula_map_ko.get(target_key, ""),
                    (
                        "4. Calculate and round the display value to four decimals."
                        if english
                        else "4. 계산 후 표시값을 소수 넷째 자리까지 정리합니다."
                    ),
                ]
            displayed = (
                f"▶ {result_summary}\n\n[Inputs Used]\n"
                if english
                else f"▶ {result_summary}\n\n[계산에 사용한 입력값]\n"
            )
            displayed += "\n".join(used_values + process_lines)
            self._show(displayed)
        except ZeroDivisionError:
            self._show(
                "Error: Division by zero. Check the inputs."
                if self.services.widget_language(self) == "en"
                else "오류: 0으로 나누는 값이 있습니다. 입력값을 확인하세요.",
                error=True,
            )
        except ValueError as e:
            self._show(
                "Input error: Check all required values, units, and percentage ranges."
                if self.services.widget_language(self) == "en"
                else f"오류: {e}",
                error=True,
            )
        except Exception as e:
            if self.services.widget_language(self) == "en":
                self.services.log_unexpected_error("Motor capacity calculation", e)
                self._show(
                    "Unexpected calculation error. Check the error log.", error=True
                )
            else:
                self.services.show_unexpected_error(self, "전동기 용량 계산", e)

    def _remember_input(self, target_key, target_label, result_summary):
        record = {
            "__target_key__": target_key,
            "__target_label__": target_label,
            "__units__": {key: var.get() for key, var in self.unit_vars.items()},
        }
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
        self.services.push_undo_state(self)
        self._apply_record(self.previous_values)
        self._show(
            "Previous inputs loaded. Check the values, then calculate."
            if self.services.widget_language(self) == "en"
            else "이전 입력값을 불러왔습니다. 값을 확인한 뒤 계산하세요."
        )

    def show_history(self):
        specs = [("__target_label__", "구한 값", 140)]
        specs.extend((v["key"], v["label"], 110) for v in self.vars_spec)
        self.services.open_history_window(
            self,
            "전동기 용량 입력 기록",
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
        self.services.push_undo_state(self)
        self._apply_record(record)
        clean_record = {
            key: value
            for key, value in record.items()
            if key not in ("__saved_at__", "__result_summary__")
        }
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

    def _apply_record(self, record):
        """이전 값과 입력 기록이 같은 방식으로 입력칸에 적용되게 합니다."""
        for key, unit in record.get("__units__", {}).items():
            if key in self.unit_vars and unit in next(
                item["unit_factors"] for item in self.vars_spec if item["key"] == key
            ):
                self.unit_vars[key].set(unit)
                self._last_units[key] = unit
        target_key = record["__target_key__"]
        target_index = next(
            i for i, spec in enumerate(self.vars_spec) if spec["key"] == target_key
        )
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
        self.services.push_undo_state(self)
        target_key = self._target_key()
        current = {
            "__target_key__": target_key,
            "__target_label__": next(
                v["label"] for v in self.vars_spec if v["key"] == target_key
            ),
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
                entry.config(
                    state="disabled", disabledbackground=colors["disabled_entry"]
                )
        self._show(self.services.initial_result_text(self))
        for key, entry in self.entries.items():
            if key != target_key:
                entry.focus_set()
                break
        sync = getattr(self, "sync_speed_display", None)
        if sync:
            sync()

    def capture_state(self):
        state = {
            "target": self._target_key(),
            "values": {key: entry.get() for key, entry in self.entries.items()},
            "units": {key: var.get() for key, var in self.unit_vars.items()},
        }
        if self.storage_key == "motor":
            state["advanced_inputs"] = getattr(self, "advanced_inputs", {}).copy()
        return state

    def apply_state(self, state, remember_undo=True):
        if remember_undo:
            self.services.push_undo_state(self)
        if self.storage_key == "motor":
            self.advanced_inputs = state.get("advanced_inputs", {}).copy()
        for key, unit in state.get("units", {}).items():
            if key in self.unit_vars:
                self.unit_vars[key].set(unit)
                self._last_units[key] = unit
        target = state.get("target", self._target_key())
        target_index = next(
            (i for i, spec in enumerate(self.vars_spec) if spec["key"] == target), 0
        )
        self.target_combo.current(target_index)
        for key, entry in self.entries.items():
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, state.get("values", {}).get(key, ""))
            if key == target:
                _mode, colors = get_theme(entry)
                entry.config(
                    state="disabled", disabledbackground=colors["disabled_entry"]
                )

    def undo_last(self):
        self.services.undo_panel(self)
