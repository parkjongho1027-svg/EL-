"""KC 개별 조항 검토 화면. 계산은 순수 검토 엔진에 위임한다."""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from src.core.elevator_review_engine import (
    INTERNAL_NOTICE,
    KC_SOURCE,
    KC_URL,
    evaluate_actual_speed,
    evaluate_brake_evidence,
    evaluate_motor_capacity,
    evaluate_rope_clause,
    evaluate_traction_case,
    review_guidance,
)
from src.core.design_documents import normalize_design_documents
from ui_components import SkyButton, attach_numeric_validation
from utils import parse_number


@dataclass(frozen=True)
class CriteriaPanelServices:
    """응용 프로그램의 공통 UI 동작을 기준 검토 화면에 전달한다."""

    create_result_display: Callable[..., Any]
    set_result_display: Callable[..., Any]
    push_undo_state: Callable[..., Any]
    open_history_window: Callable[..., Any]
    undo_panel: Callable[..., Any]


class CriteriaPanel(tk.Frame):
    """법령 단일 조항과 설계용 계산을 별도 표시한다."""

    def __init__(self, parent, store, services):
        super().__init__(parent, bg="white")
        self.store = store
        self.services = services
        self.entries = {}
        self.design_documents = normalize_design_documents({})
        self.undo_stack = []
        self.storage_key = "criteria"
        self.previous_values = store.previous(self.storage_key)
        self.input_history = store.history(self.storage_key)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1, uniform="criteria_split")
        self.grid_columnconfigure(1, weight=1, uniform="criteria_split")
        holder = tk.LabelFrame(
            self,
            text=f" {KC_SOURCE.partition(' (')[0]} · 개별 조항 검토 ",
            font=("맑은 고딕", 11, "bold"),
            bg="white",
            padx=6,
            pady=6,
        )
        holder.grid(row=0, column=0, sticky="nsew", padx=(0, 7), pady=(3, 6))
        canvas = tk.Canvas(holder, bg="white", highlightthickness=0)
        bar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        frame = tk.Frame(canvas, bg="white")
        canvas.create_window((8, 8), window=frame, anchor="nw")
        frame.bind(
            "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"),
        )

        self.drive = tk.StringVar(value="권상식")
        drive_combo = ttk.Combobox(
            frame,
            textvariable=self.drive,
            values=("권상식", "기타"),
            state="readonly",
            width=18,
        )
        drive_combo.pack(anchor="w")
        drive_combo.bind("<Return>", self._calculate_on_return)
        for key, label in (
            ("count", "로프 가닥 수"),
            ("diameter", "로프 공칭직경 mm"),
            ("breaking", "1가닥 최소 파단하중 N"),
            ("force", "최하층 정격하중 최대 장력 N"),
            ("rated", "정격속도 m/s"),
            ("measured_up", "중간구간 실측 상승 m/s"),
            ("measured_down", "중간구간 실측 하강 m/s"),
            ("selected_motor", "선정 전동기 kW"),
        ):
            row = tk.Frame(frame, bg="white")
            row.pack(anchor="w", pady=2)
            tk.Label(row, text=label, width=25, anchor="w", bg="white").pack(
                side="left"
            )
            entry = tk.Entry(row, width=12)
            attach_numeric_validation(entry)
            entry.pack(side="left")
            self.entries[key] = entry
            entry.bind("<Return>", self._calculate_on_return)
        self.speed_conditions = tk.BooleanVar(value=False)
        tk.Checkbutton(
            frame,
            text="50% 하중, 중간 주행, 정격 전압·주파수 모두 확인",
            variable=self.speed_conditions,
            bg="white",
        ).pack(anchor="w")
        self.brake_checks = {}
        for key, label in (
            ("load", "125% 하강에서 브레이크 단독 정지 시험"),
            ("sets", "제동 기계부품 최소 2세트 확인"),
            ("failure", "한 세트 고장 시 양방향 조건 정지·유지"),
            ("decel", "안전장치·완충기 감속도와 비교"),
        ):
            var = tk.StringVar(value="자료 없음")
            self.brake_checks[key] = var
            row = tk.Frame(frame, bg="white")
            row.pack(anchor="w")
            tk.Label(row, text=label, width=39, anchor="w", bg="white").pack(
                side="left"
            )
            combo = ttk.Combobox(
                row,
                textvariable=var,
                values=("자료 없음", "충족 증빙", "미충족 증빙"),
                state="readonly",
                width=12,
            )
            combo.pack(side="left")
            combo.bind("<Return>", self._calculate_on_return)
        tk.Label(
            frame,
            text="부속서 IX: 최악 조건에서 산정한 장력과 마찰값 직접 입력",
            bg="white",
        ).pack(anchor="w", pady=(6, 1))
        self.traction_entries = {}
        for case, title in (
            ("load", "125% 적재"),
            ("emergency", "비상제동"),
            ("stationary", "카·균형추 정지"),
        ):
            row = tk.Frame(frame, bg="white")
            row.pack(anchor="w")
            tk.Label(row, text=title, width=16, anchor="w", bg="white").pack(
                side="left"
            )
            for key, label in (
                ("t1", "T1 N"),
                ("t2", "T2 N"),
                ("f", "f"),
                ("alpha", "α rad"),
            ):
                tk.Label(row, text=label, bg="white").pack(side="left")
                e = tk.Entry(row, width=7)
                attach_numeric_validation(e)
                e.pack(side="left", padx=2)
                e.bind("<Return>", self._calculate_on_return)
                self.traction_entries[(case, key)] = e
        actions = tk.Frame(frame, bg="white")
        actions.pack(anchor="w", fill="x", pady=8)
        SkyButton(actions, text="기준 검토", command=self.calculate, width=11).pack(
            side="left"
        )
        SkyButton(actions, text="입력값 삭제", command=self.clear, width=11).pack(
            side="left", padx=5
        )
        self.previous_button = SkyButton(
            actions,
            text="이전 입력값",
            command=self.restore_previous,
            width=11,
            state="normal" if self.previous_values else "disabled",
        )
        self.previous_button.pack(side="left", padx=5)
        self.history_button = SkyButton(
            actions,
            text="입력 기록",
            command=self.show_history,
            width=11,
            state="normal" if self.input_history else "disabled",
        )
        self.history_button.pack(side="left", padx=5)
        from src.ui.design_documents_dialog import open_design_documents_dialog
        SkyButton(
            frame, text="설치 전 설계자료", command=lambda: open_design_documents_dialog(self), width=15,
        ).pack(anchor="w", pady=(0, 9))

        result_holder = tk.LabelFrame(
            self,
            text=" 검토 결과 ",
            font=("맑은 고딕", 11, "bold"),
            bg="white",
            padx=6,
            pady=6,
        )
        result_holder.grid(row=0, column=1, sticky="nsew", padx=(7, 0), pady=(3, 6))
        self.result_text = self.services.create_result_display(result_holder)
        self._show(
            "입력 자료별 개별 조항만 검토합니다. 검사기관의 최종 판정 대상입니다."
        )

    def _calculate_on_return(self, _event=None):
        self.calculate()
        return "break"

    def _show(self, s, error=False):
        self.services.set_result_display(self.result_text, s, error)

    def capture_state(self):
        state = {key: entry.get() for key, entry in self.entries.items()}
        state.update(
            {
                f"{case}_{key}": entry.get()
                for (case, key), entry in self.traction_entries.items()
            }
        )
        state["__drive__"] = self.drive.get()
        state["__speed_conditions__"] = self.speed_conditions.get()
        state.update(
            {f"__brake_{key}__": var.get() for key, var in self.brake_checks.items()}
        )
        state["__design_documents__"] = normalize_design_documents(
            getattr(self, "design_documents", None))
        return state

    def apply_state(self, state, remember_undo=True):
        if not isinstance(state, dict):
            return
        if remember_undo:
            self.services.push_undo_state(self)
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, str(state.get(key, "")))
        for (case, key), entry in self.traction_entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, str(state.get(f"{case}_{key}", "")))
        self.drive.set(state.get("__drive__", "권상식"))
        self.speed_conditions.set(state.get("__speed_conditions__", False))
        for key, var in self.brake_checks.items():
            var.set(state.get(f"__brake_{key}__", "자료 없음"))
        self.design_documents = normalize_design_documents(state.get("__design_documents__"))

    def _remember(self, summary):
        if getattr(self.store, "_suppress_history", False):
            return
        self.input_history = self.store.add_history(
            self.storage_key, self.capture_state(), summary
        )
        self.previous_values = self.store.previous(self.storage_key)
        self.previous_button.config(state="normal")
        self.history_button.config(state="normal")

    def clear(self):
        current = self.capture_state()
        self.services.push_undo_state(self)
        if (
            any(current[key].strip() for key in self.entries)
            or any(
                current[f"{case}_{key}"].strip() for case, key in self.traction_entries
            )
            or (
                current["__drive__"] != "권상식"
                or current["__speed_conditions__"]
                or any(var.get() != "자료 없음" for var in self.brake_checks.values())
            )
            or current["__design_documents__"] != normalize_design_documents({})
        ):
            self.store.set_previous(self.storage_key, current)
            self.previous_values = self.store.previous(self.storage_key)
            self.previous_button.config(state="normal")
        for e in list(self.entries.values()) + list(self.traction_entries.values()):
            e.delete(0, tk.END)
        for v in self.brake_checks.values():
            v.set("자료 없음")
        self.drive.set("권상식")
        self.speed_conditions.set(False)
        self.design_documents = normalize_design_documents({})
        self._show("입력값을 삭제했습니다.")

    def restore_previous(self):
        if self.previous_values is None:
            return
        self.apply_state(self.previous_values)
        self._show("이전 입력값을 불러왔습니다. 값을 확인한 뒤 기준 검토를 누르세요.")

    def show_history(self):
        specs = [
            ("__drive__", "구동 방식", 95),
            ("count", "로프 가닥 수", 85),
            ("diameter", "로프 직경", 85),
            ("breaking", "파단하중", 100),
            ("force", "최대 장력", 90),
            ("rated", "정격속도", 85),
            ("measured_up", "실측 상승", 85),
            ("measured_down", "실측 하강", 85),
            ("selected_motor", "선정 전동기", 90),
            ("__speed_conditions__", "속도 측정조건", 95),
        ]
        specs.extend(
            (f"__brake_{key}__", f"브레이크 {key}", 115) for key in self.brake_checks
        )
        specs.extend(
            (f"{case}_{key}", f"{case} {key}", 85)
            for case, key in self.traction_entries
        )
        self.services.open_history_window(
            self,
            "기준 검토 입력 기록",
            self.input_history,
            specs,
            self._load_history_record,
            self._delete_history_record,
            self._clear_history,
            self._rename_history_record,
        )

    def _load_history_record(self, record, number):
        self.apply_state(record)
        self.store.set_previous(self.storage_key, self.capture_state())
        self.previous_values = self.store.previous(self.storage_key)
        self.previous_button.config(state="normal")
        self._show(
            f"입력 기록 {number}번을 불러왔습니다. 값을 확인한 뒤 기준 검토를 누르세요."
        )

    def _delete_history_record(self, index):
        self.input_history = self.store.delete_history(self.storage_key, index)
        if not self.input_history:
            self.history_button.config(state="disabled")
        return self.input_history

    def _clear_history(self):
        self.store.clear_history(self.storage_key)
        self.input_history = []
        self.history_button.config(state="disabled")

    def _rename_history_record(self, index, name):
        self.input_history = self.store.rename_history(self.storage_key, index, name)
        return self.input_history

    def undo_last(self):
        self.services.undo_panel(self)

    def calculate(self):
        try:

            def number(k):
                s = self.entries[k].get().strip()
                return parse_number(s, k) if s else None

            def add_review(lines, topic, **details):
                lines.append("  [권장 검토 — 자동 설계변경 지시가 아닙니다]")
                lines.extend("  " + item for item in review_guidance(topic, **details))

            rope = evaluate_rope_clause(
                "traction" if self.drive.get() == "권상식" else "other",
                "rope",
                *(number(k) for k in ("count", "diameter", "breaking", "force")),
            )
            lines = [
                "[9.2.2 매다는 장치 안전율 — 수치항목]",
                f"상태: {rope['status']} / {rope['reason']}",
            ]
            if "value" in rope:
                lines.append(
                    f"안전율 {rope['value']:.3f} / 하한 {rope['limit']:g} / 여유율 {rope['margin_pct']:.2f}% / {rope['engineering']} ({rope['clause']})"
                )
            if rope["status"] == "NONCOMPLIANT":
                add_review(lines, "rope")
            lines.extend(["", "[9.3 / 부속서 IX 권상 3조건 — 조건식 계산]"])
            legal_notes = []
            for case, title in (
                ("load", "적재"),
                ("emergency", "비상제동"),
                ("stationary", "카·균형추 정지"),
            ):
                vals = []
                for key in ("t1", "t2", "f", "alpha"):
                    raw = self.traction_entries[(case, key)].get().strip()
                    vals.append(parse_number(raw, key) if raw else None)
                traction = evaluate_traction_case(case, *vals)
                if "ratio" in traction:
                    lines.append(
                        f"{title}: {traction['ratio']:.4f} {traction['comparison']} {traction['limit']:.4f}  /  여유율 {traction['margin_pct']:.2f}%  /  {traction['status']}"
                    )
                else:
                    lines.append(f"{title}: 조건식 자료 부족")
                legal_notes.append(
                    (
                        title,
                        traction.get("legal_status", traction["status"]),
                        traction["reason"],
                    )
                )
                if traction["status"] == "조건식 미충족":
                    add_review(lines, "traction", case=case)
            lines.append("")
            for title, status, _reason in legal_notes:
                lines.append(f"※ {title} 법정 상태: {status}")
            reasons = list(
                dict.fromkeys(reason for _title, _status, reason in legal_notes)
            )
            if len(reasons) == 1:
                lines.append("   공통 사유: " + reasons[0])
            else:
                for title, _status, reason in legal_notes:
                    lines.append(f"   {title} 사유: {reason}")
            lines.extend(["", "[13.2.4 실측 운행속도 — 상승·하강 별도]"])
            for name, key in (("상승", "measured_up"), ("하강", "measured_down")):
                speed = evaluate_actual_speed(
                    number("rated"),
                    number(key),
                    self.speed_conditions.get(),
                    self.speed_conditions.get(),
                    self.speed_conditions.get(),
                )
                line = f"{name}: {speed['status']} / {speed.get('ratio_pct', '—')}%"
                if "margin_percentage_points" in speed:
                    line += f" / 경계까지 {speed['margin_percentage_points']:.2f}%p"
                lines.append(line + " / " + speed["reason"])
                if speed["status"] == "NONCOMPLIANT":
                    add_review(lines, "speed", measured_ratio=speed["ratio_pct"])
            mapping = {"자료 없음": None, "충족 증빙": True, "미충족 증빙": False}
            failed_checks = tuple(
                key
                for key, var in self.brake_checks.items()
                if var.get() == "미충족 증빙"
            )
            brake = evaluate_brake_evidence(
                *(mapping[v.get()] for v in self.brake_checks.values())
            )
            lines.extend(
                [
                    "",
                    "[13.2.2.2.1 브레이크 증빙]",
                    f"상태: {brake['status']} / {brake['reason']}",
                ]
            )
            if brake["status"] == "NONCOMPLIANT":
                add_review(lines, "brake", failed_checks=failed_checks)
            selected = number("selected_motor")
            motor_panel = self.winfo_toplevel()._elevator_app.motor_panel
            # 역산 모드에서 P 입력값은 필요동력 계산 결과가 아니므로 비교하지 않는다.
            raw = (
                motor_panel.entries["P"].get().strip()
                if motor_panel._target_key() == "P"
                else ""
            )
            needed = parse_number(raw, "필요동력") if raw else None
            lines.extend(["", "[전동기 선정 — 설계용량, 법정 판정 아님]"])
            if needed is None or selected is None:
                lines.append(
                    "선정값과 필요동력이 모두 있어야 용량을 비교할 수 있습니다."
                )
            else:
                capacity = evaluate_motor_capacity(needed, selected)
                label = "설계용량 충족" if capacity["adequate"] else "설계용량 부족"
                lines.append(
                    f"선정 {selected:g} kW ≥ 필요 {needed:g} kW: {label}"
                    if capacity["adequate"]
                    else f"선정 {selected:g} kW < 필요 {needed:g} kW: {label} ({capacity['shortfall_kw']:.4f} kW 부족)"
                )
                if not capacity["adequate"]:
                    add_review(lines, "motor")
            lines.extend(
                [
                    "",
                    INTERNAL_NOTICE,
                    "적용기준·제조사 설계도서 및 시험기록과 대조 필요. 검사기관의 최종 판정 대상.",
                    f"출처: {KC_SOURCE} / {KC_URL}",
                ]
            )
            self._show("\n".join(lines))
            if (
                any(
                    str(value).strip()
                    for key, value in self.capture_state().items()
                    if not key.startswith("__")
                )
                or self.drive.get() != "권상식"
                or self.speed_conditions.get()
                or any(var.get() != "자료 없음" for var in self.brake_checks.values())
            ):
                self._remember(f"로프: {rope['status']} / 브레이크: {brake['status']}")
        except (ValueError, OverflowError) as e:
            self._show(f"입력 오류: {e}", True)
