"""Motor duty input dialog; engineering formulas remain in src.core."""

import tkinter as tk
from tkinter import ttk

from src.core.motor_dynamics import MotorDutyInput, estimate_motor_duty
from src.core.errors import CalculationInputError
from theme_manager import apply_theme
from ui_components import SkyButton, messagebox
from src.ui.record_manager import open_record_manager


FIELD_SPECS = (
    ("distance_m", "운행 거리 (m)", "30"),
    ("speed_m_s", "카 속도 (m/s)", "2"),
    ("accel_m_s2", "최대 가속도 (m/s²)", "1"),
    ("jerk_m_s3", "저크 (m/s³)", ".8"),
    ("car_kg", "카 질량 (kg)", "1000"),
    ("load_kg", "실제 적재 (kg)", "500"),
    ("rated_load_kg", "정격 적재 (kg)", "1000"),
    ("counterweight_kg", "균형추 질량 (kg)", "1500"),
    ("extra_mass_kg", "추가 등가 질량 (kg)", "300"),
    ("sheave_radius_m", "권상 도르래 반지름 (m)", ".4"),
    ("gear_ratio", "기어비 (모터축/도르래축)", "1"),
    ("roping_ratio", "로핑비 (로프속도/카속도)", "1"),
    ("motor_inertia_kg_m2", "모터축 합성 관성 J (kg·m²)", "2"),
    ("resistance_n", "운행 방향 저항력 (N)", "100"),
    ("efficiency", "구동 효율 (0~1)", ".85"),
    ("cycle_s", "운전 반복 주기 (s)", "120"),
    ("regen_fraction", "회생 분담 비율 (0~1)", "0"),
    ("step_s", "궤적 시간 간격 (s)", ".05"),
)


def format_duty_result(data):
    return "\n".join(
        (
            f"주행 {data['run_time_s']:.3f} s / 반복 주기 {data['cycle_s']:.1f} s / 운전율 {data['duty_ed_pct']:.2f}% ED",
            f"모터축 환산 관성 {data['reflected_inertia_kg_m2']:.4f} kg·m² / 최대 축속도 {data['peak_motor_rad_s']:.3f} rad/s",
            f"최대 요구 축토크(절댓값) {data['peak_torque_nm']:.3f} N·m / 최고 구동 입력 {data['peak_input_kw']:.3f} kW",
            f"모터 열 추정용 반복주기 RMS 토크 {data['thermal_rms_torque_nm']:.3f} N·m",
            f"저항기 최고 {data['resistor_peak_kw']:.3f} kW / 회당 {data['resistor_cycle_kj']:.3f} kJ / 반복주기 평균 {data['resistor_average_kw']:.3f} kW",
            "※ 모터 허용 피크·연속 토크 및 저항기 피크·평균·펄스 정격은 제조사 자료와 비교하세요.",
            "※ 회생 비율은 브레이크 에너지의 분담 가정이며 마찰식 안전제동기 온도는 계산하지 않습니다.",
        )
    )


def open_motor_duty_dialog(panel):
    window = tk.Toplevel(panel)
    window.title("관성·가속 토크 및 운전주기 추정")
    window.geometry("860x830")
    window.minsize(720, 650)
    window.transient(panel.winfo_toplevel())
    window._ui_theme = getattr(panel.winfo_toplevel(), "_ui_theme", "light")
    body = tk.Frame(window, bg="white", padx=12, pady=12)
    body.pack(fill="both", expand=True)
    tk.Label(
        body,
        text="모터축 관성·열부하·제동저항기 추정 (제조사 정격 검토 필요)",
        font=("맑은 고딕", 11, "bold"),
        bg="white",
    ).pack(anchor="w", pady=(0, 8))
    # Pack the action row before the scrollable form so every button remains visible.
    actions = tk.Frame(body, bg="white")
    actions.pack(side="bottom", fill="x", pady=(8, 0))
    result_holder = tk.LabelFrame(
        body, text=" 계산 결과 ", bg="white", font=("맑은 고딕", 10, "bold")
    )
    result_holder.pack(side="bottom", fill="both", expand=True)
    result = tk.Text(
        result_holder,
        height=9,
        wrap="word",
        bg="#f7faff",
        relief="flat",
        padx=9,
        pady=7,
    )
    result_scroll = ttk.Scrollbar(
        result_holder, orient="vertical", command=result.yview
    )
    result.configure(yscrollcommand=result_scroll.set)
    result_scroll.pack(side="right", fill="y")
    result.pack(side="left", fill="both", expand=True)
    outer = tk.LabelFrame(
        body, text=" 입력값 ", bg="white", font=("맑은 고딕", 10, "bold")
    )
    outer.pack(fill="both", expand=True, pady=(0, 8))
    canvas = tk.Canvas(outer, highlightthickness=0, bg="white")
    scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    form = tk.Frame(canvas, bg="white")
    form_window = canvas.create_window((8, 4), window=form, anchor="nw")
    form.bind(
        "<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.bind(
        "<Configure>",
        lambda event: canvas.itemconfigure(
            form_window, width=max(100, event.width - 12)
        ),
    )

    saved = getattr(panel, "advanced_inputs", {})
    defaults = {key: default for key, _, default in FIELD_SPECS}
    if not saved:
        try:
            defaults["load_kg"] = (
                panel.entries["Q"].get().strip() or defaults["load_kg"]
            )
            velocity = float(panel.entries["V"].get())
            defaults["speed_m_s"] = str(
                velocity if panel.unit_vars["V"].get() == "m/s" else velocity / 60
            )
        except (ValueError, KeyError, AttributeError):
            pass
    entries = {}
    for row, (key, label, _default) in enumerate(FIELD_SPECS):
        tk.Label(form, text=label, width=36, anchor="w", bg="white").grid(
            row=row, column=0, sticky="w", pady=3
        )
        entry = tk.Entry(form, width=19, justify="right")
        entry.insert(0, saved.get(key, defaults[key]))
        entry.grid(row=row, column=1, sticky="w", pady=3)
        entries[key] = entry
    direction = tk.StringVar(value=saved.get("direction", "상승"))
    tk.Label(form, text="운행 방향", width=36, anchor="w", bg="white").grid(
        row=len(FIELD_SPECS), column=0, sticky="w"
    )
    direction_combo = ttk.Combobox(
        form,
        textvariable=direction,
        values=("상승", "하강"),
        state="readonly",
        width=16,
    )
    direction_combo.grid(row=len(FIELD_SPECS), column=1, sticky="w")

    def wheel(event):
        if event.num in (4, 5):
            amount = -1 if event.num == 4 else 1
        else:
            amount = -1 if event.delta > 0 else 1
        canvas.yview_scroll(amount, "units")
        return "break"

    for widget in (canvas, form, *form.winfo_children()):
        widget.bind("<MouseWheel>", wheel, add="+")
        widget.bind("<Button-4>", wheel, add="+")
        widget.bind("<Button-5>", wheel, add="+")

    def raw_state():
        return {
            **{key: entry.get() for key, entry in entries.items()},
            "direction": direction.get(),
        }

    def show(message):
        result.configure(state="normal")
        result.delete("1.0", "end")
        result.insert("1.0", message)
        result.configure(state="disabled")

    pending = None

    def calculate(record=False):
        raw = raw_state()
        try:
            data = estimate_motor_duty(MotorDutyInput(**raw))
        except (CalculationInputError, ValueError, OverflowError, TypeError) as exc:
            show(f"입력 확인: {exc}")
            return None
        panel.advanced_inputs = raw
        show(format_duty_result(data))
        if record:
            panel.store.add_history(
                "motor_duty",
                raw,
                f"최대 축토크 {data['peak_torque_nm']:.3f} N·m / 운전율 {data['duty_ed_pct']:.2f}%",
            )
        return data

    def schedule(_event=None):
        nonlocal pending
        if pending is not None:
            window.after_cancel(pending)
        pending = window.after(350, lambda: calculate())

    def apply_record(values):
        for key, entry in entries.items():
            entry.delete(0, "end")
            entry.insert(0, values.get(key, defaults[key]))
        direction.set(values.get("direction", "상승"))
        calculate()

    def previous():
        values = panel.store.previous("motor_duty")
        if values:
            apply_record(values)
        else:
            messagebox.showinfo("이전 입력", "저장된 입력이 없습니다.", parent=window)

    def history():
        def records():
            return [
                (
                    index,
                    (
                        record.get("__name__", ""),
                        record.get("__saved_at__", ""),
                        record.get("__result_summary__", ""),
                    ),
                )
                for index, record in reversed(
                    list(enumerate(panel.store.history("motor_duty")))
                )
            ]

        def load(indices):
            apply_record(panel.store.history("motor_duty")[indices[0]])

        def delete(indices):
            for index in sorted(indices, reverse=True):
                panel.store.delete_history("motor_duty", index)

        def rename(index, name):
            panel.store.rename_history("motor_duty", index, name)

        open_record_manager(
            window,
            "관성·열부하 입력 기록",
            (
                ("name", "기록명", 140),
                ("date", "저장 시각", 155),
                ("summary", "계산 결과", 460),
            ),
            records,
            load,
            delete,
            rename=rename,
            multi_load=False,
            save_current=lambda: calculate(record=True),
        )

    def clear():
        previous_values = raw_state()
        panel.store.set_previous("motor_duty", previous_values)
        panel.advanced_inputs = {}
        for entry in entries.values():
            entry.delete(0, "end")
        show("입력값을 삭제했습니다. 이전 입력에서 복원할 수 있습니다.")
        entries["distance_m"].focus_set()

    def copy():
        text = result.get("1.0", "end-1c").strip()
        if text:
            window.clipboard_clear()
            window.clipboard_append(text)
            copy_button.configure(text="복사 완료")
            window.after(
                1200,
                lambda: (
                    copy_button.winfo_exists()
                    and copy_button.configure(text="결과 복사")
                ),
            )

    for title, command in (
        ("계산", lambda: calculate(record=True)),
        ("입력값 삭제", clear),
        ("이전 입력", previous),
        ("입력 기록", history),
    ):
        SkyButton(actions, text=title, command=command, width=10).pack(
            side="left", padx=(0, 6)
        )
    copy_button = SkyButton(actions, text="결과 복사", command=copy, width=10)
    copy_button.pack(side="right")
    for entry in entries.values():
        entry.bind("<KeyRelease>", schedule, add="+")
        entry.bind(
            "<Return>", lambda _event: (calculate(record=True), "break")[1], add="+"
        )
    direction.trace_add("write", schedule)
    window.bind(
        "<Destroy>",
        lambda event: (
            pending is not None and window.after_cancel(pending)
            if event.widget is window and pending is not None
            else None
        ),
        add="+",
    )
    apply_theme(window, window._ui_theme)
    entries["distance_m"].focus_set()
    calculate()
    return window
