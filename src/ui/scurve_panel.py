"""S-Curve 계산 결과, 비교 그래프, 시뮬레이션 기록을 표시하는 Tk 화면."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import tkinter as tk
from tkinter import filedialog, ttk

from src.core.elevator_review_engine import scurve_profile
from src.core.energy_model import compare_trips, read_measurement
from src.ui.engineering_tools_dialog import open_engineering_tools
from src.ui.graph_workspace import (
    manage_graphs,
    save_current_graph,
    panel_state,
    refresh_live_graphs,
)
from src.ui.simulation_plot import draw_scurve_plot, draw_energy_comparison
from src.ui.theme_manager import get_theme, apply_theme
from src.ui.ui_components import (
    WindowManager,
    SkyButton,
    attach_numeric_validation,
    messagebox,
)
from src.common.utils import parse_number


@dataclass(frozen=True)
class SCurvePanelServices:
    create_result_display: Callable[..., Any]
    set_result_display: Callable[..., Any]
    push_undo_state: Callable[..., Any]
    undo_panel: Callable[..., Any]
    log_unexpected_error: Callable[..., Any]


class SCurvePanel(tk.Frame):
    """기존 기계동력 곡선과 같은 운행 조건의 전기에너지 비교."""

    ENERGY_FIELDS = (
        ("car_mass", "카 질량 kg", "1000"),
        ("load_mass", "적재 질량 kg", "500"),
        ("counterweight_mass", "균형추 질량 kg", "1500"),
        ("equivalent_extra_mass", "로프·회전부 등가질량 kg", "300"),
        ("resistance", "이동 저항력 N", "100"),
        ("drive_efficiency", "구동 효율 (0~1)", "0.85"),
        ("regen_efficiency", "회생 효율 (0~1; 미설치 0)", "0"),
        ("auxiliary_kw", "운행 중 보조전력 kW", "0.15"),
        ("ref_vmax", "기준 최고속도 m/s", "2"),
        ("ref_amax", "기준 최대 가속도 m/s²", "1"),
        ("ref_jerk", "기준 저크 m/s³", "0.8"),
        ("candidate_vmax", "후보 최고속도 m/s", "2"),
        ("candidate_amax", "후보 최대 가속도 m/s²", "0.8"),
        ("candidate_jerk", "후보 저크 m/s³", "0.6"),
    )

    def __init__(self, parent, store, services):
        super().__init__(parent, bg="white")
        self.services = services
        self.entries = {}
        self.storage_key = "scurve"
        self.store = store
        self.undo_stack = []
        self._profile = None
        self._energy_profile = None
        self._reference_energy_profile = None
        self._graph_state_mechanical = None
        self._graph_state_electrical = None
        self.mode_tabs = ttk.Notebook(self)
        self.mode_tabs.pack(fill="both", expand=True)
        basic = tk.Frame(self.mode_tabs, bg="white")
        energy = tk.Frame(self.mode_tabs, bg="white")
        self.mode_tabs.add(basic, text="기계동력 곡선")
        self.mode_tabs.add(energy, text="전기에너지 비교")
        heading = tk.Frame(basic, bg="white")
        heading.pack(fill="x", padx=10, pady=8)
        tk.Label(
            heading,
            text="대칭 S-Curve: 일정 저크로 가감속하는 단순화 운행 모델",
            bg="white",
            font=("맑은 고딕", 11, "bold"),
        ).pack(side="left")
        SkyButton(
            heading,
            text="공학 데이터 도구",
            command=lambda: open_engineering_tools(self),
            font=("맑은 고딕", 9),
            width=14,
        ).pack(side="right")
        for key, label, default in (
            ("distance", "운행거리 m", "30"),
            ("vmax", "설정 최고속도 m/s", "2"),
            ("amax", "최대 가속도 m/s²", "1"),
            ("jerk", "저크 한계 m/s³", "0.8"),
            ("mass", "등가 이동질량 kg", "1500"),
            ("force", "불평형·저항 합력 N", "0"),
        ):
            row = tk.Frame(basic, bg="white")
            row.pack(anchor="w", padx=10, pady=2)
            tk.Label(row, text=label, width=27, anchor="w", bg="white").pack(
                side="left"
            )
            entry = tk.Entry(row, width=14)
            attach_numeric_validation(entry)
            entry.insert(0, default)
            entry.pack(side="left")
            self.entries[key] = entry
            entry.bind("<Return>", lambda _event: self.calculate(record=True))
        self.plot = tk.Canvas(basic, height=255, highlightthickness=0)
        self.plot.pack(fill="x", padx=10, pady=(0, 5))
        self._simulation_actions(basic, "mechanical")
        self.plot.bind(
            "<Configure>", lambda _event: self._queue_plot_redraw("mechanical")
        )
        self.result_text = self.services.create_result_display(basic)
        self._show(
            "예상 기계동력만 계산합니다. 전기에너지는 오른쪽 비교 탭에서 계산합니다."
        )
        self._build_energy(energy)
        self.default_state = self.capture_state()
        # 실행 버튼 없이도 기본 입력의 그래프를 첫 화면에 표시한다.
        self.after_idle(self.calculate)
        self.after_idle(self.calculate_energy)

    def _build_energy(self, host):
        self.energy_entries = {}
        self.measurement_paths = {}
        self.direction = tk.StringVar(value="상승")
        outer = tk.Frame(host, bg="white")
        outer.pack(fill="x")
        canvas = tk.Canvas(outer, height=290, highlightthickness=0, bg="white")
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="x", expand=True)
        form = tk.Frame(canvas, bg="white")
        canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        tk.Label(
            form,
            text="운행거리: 기계동력 탭의 입력값 사용. 나머지 하중·방향·효율은 두 곡선에 동일 적용.",
            bg="white",
        ).pack(anchor="w", padx=10, pady=4)
        row = tk.Frame(form, bg="white")
        row.pack(anchor="w", padx=10)
        tk.Label(row, text="운행 방향", width=27, anchor="w", bg="white").pack(
            side="left"
        )
        ttk.Combobox(
            row,
            textvariable=self.direction,
            values=("상승", "하강"),
            state="readonly",
            width=13,
        ).pack(side="left")
        for key, label, default in self.ENERGY_FIELDS:
            row = tk.Frame(form, bg="white")
            row.pack(anchor="w", padx=10, pady=2)
            tk.Label(row, text=label, width=27, anchor="w", bg="white").pack(
                side="left"
            )
            entry = tk.Entry(row, width=15)
            attach_numeric_validation(entry)
            entry.insert(0, default)
            entry.pack(side="left")
            entry.bind("<Return>", lambda _event: self.calculate_energy(record=True))
            self.energy_entries[key] = entry
        for key, label in (
            ("reference", "기준 실측 CSV"),
            ("candidate", "후보 실측 CSV"),
        ):
            row = tk.Frame(form, bg="white")
            row.pack(anchor="w", padx=10, pady=2)
            tk.Label(row, text=label, width=27, anchor="w", bg="white").pack(
                side="left"
            )
            entry = tk.Entry(row, width=40)
            entry.pack(side="left")
            self.measurement_paths[key] = entry
            SkyButton(
                row, text="찾기", command=lambda e=entry: self._choose_measurement(e)
            ).pack(side="left")
        # Tab 이동은 ElevatorApp에서 다른 다섯 탭과 같은 순서로 연결한다.
        self.energy_plot = tk.Canvas(host, height=235, highlightthickness=0)
        self.energy_plot.pack(fill="x", padx=10)
        self.energy_plot.bind(
            "<Configure>", lambda _event: self._queue_plot_redraw("electrical")
        )
        self._simulation_actions(host, "electrical")
        self.energy_result = self.services.create_result_display(host, copy_width=19)
        self._show_energy(
            "예측 비교입니다. 실측 두 운행 CSV가 없으면 절감 성능 검증으로 표시하지 않습니다."
        )

    def _simulation_actions(self, host, mode):
        bar = tk.Frame(host, bg="white")
        bar.pack(fill="x", padx=10, pady=(4, 6))
        for index, (label, action) in enumerate(
            (
                ("이전 시뮬레이션", lambda: self._load_previous_simulation(mode)),
                ("시뮬레이션 관리", lambda: manage_graphs(self, mode)),
                ("시뮬레이션 저장", lambda: save_current_graph(self, mode)),
                ("시뮬레이션 복사 (PNG)", lambda: self._save_simulation_png(mode)),
            )
        ):
            bar.columnconfigure(index, weight=1, uniform="simulation_actions")
            SkyButton(
                bar, text=label, command=action, width=19, font=("맑은 고딕", 10)
            ).grid(row=0, column=index, sticky="ew", padx=(0, 6))

    def _record_simulation(self, mode, summary):
        self.store.add_simulation(mode, self.capture_state(), summary)

    def _load_simulation_record(self, record):
        state = record.get("__state__")
        if not isinstance(state, dict):
            return
        self.apply_state(state)
        mode = record.get("__simulation_mode__", "mechanical")
        self.mode_tabs.select(1 if mode == "electrical" else 0)
        if mode == "electrical":
            self.calculate_energy()
        else:
            self.calculate()

    def _load_previous_simulation(self, mode):
        records = self.store.simulation_history(mode)
        if not records:
            messagebox.showinfo(
                "이전 시뮬레이션", "저장된 시뮬레이션이 없습니다.", parent=self
            )
            return
        self._load_simulation_record(records[-1][1])

    def _delete_displayed_simulation(self, mode):
        if mode == "electrical":
            self._energy_profile = None
            self._reference_energy_profile = None
            self._graph_state_electrical = None
            self.redraw_energy_plot()
            self._show_energy(
                "화면의 시뮬레이션을 삭제했습니다. 저장된 기록은 기록창에서 삭제할 수 있습니다."
            )
        else:
            self._profile = None
            self._graph_state_mechanical = None
            self.redraw_plot()
            self._show(
                "화면의 시뮬레이션을 삭제했습니다. 저장된 기록은 기록창에서 삭제할 수 있습니다."
            )

    def _show_simulation_history(self):
        window = tk.Toplevel(self)
        window.title("시뮬레이션 기록")
        window._ui_theme = getattr(self.winfo_toplevel(), "_ui_theme", "light")
        window.transient(self.winfo_toplevel())
        WindowManager.center(window, self.winfo_toplevel(), 780, 480)
        frame = tk.Frame(window)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        tree = ttk.Treeview(
            frame,
            columns=("time", "mode", "summary"),
            show="headings",
            selectmode="browse",
        )
        for key, label, width in (
            ("time", "저장 시각", 150),
            ("mode", "종류", 100),
            ("summary", "결과", 480),
        ):
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor="w")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            for index, record in reversed(self.store.simulation_history()):
                mode = (
                    "전기에너지 비교"
                    if record["__simulation_mode__"] == "electrical"
                    else "기계동력"
                )
                tree.insert(
                    "",
                    "end",
                    iid=str(index),
                    values=(
                        record.get("__timestamp__", ""),
                        mode,
                        record.get("__result_summary__", ""),
                    ),
                )

        def selected():
            ids = tree.selection()
            if not ids:
                messagebox.showinfo(
                    "시뮬레이션 기록", "기록을 하나 선택하세요.", parent=window
                )
                return None
            return int(ids[0])

        def load():
            index = selected()
            if index is None:
                return
            history = self.store.data["calculators"]["scurve"]["history"]
            if index < len(history):
                self._load_simulation_record(history[index])
                window.destroy()

        def delete():
            index = selected()
            if index is None:
                return
            if not messagebox.askyesno(
                "기록 삭제", "선택한 시뮬레이션 기록을 삭제할까요?", parent=window
            ):
                return
            self.store.delete_simulation(index)
            refresh()

        row = tk.Frame(window)
        row.pack(fill="x", padx=12, pady=(0, 10))
        SkyButton(row, text="불러오기", command=load).pack(side="left", padx=4)
        SkyButton(row, text="선택 기록 삭제", command=delete).pack(side="left", padx=4)
        SkyButton(row, text="닫기", command=window.destroy).pack(side="right", padx=4)
        tree.bind("<Double-1>", lambda _event: load())
        refresh()
        apply_theme(window, window._ui_theme)

    def _save_simulation_png(self, mode):
        profile = self._energy_profile if mode == "electrical" else self._profile
        reference = self._reference_energy_profile if mode == "electrical" else None
        if profile is None or (mode == "electrical" and reference is None):
            messagebox.showinfo(
                "PNG 저장", "먼저 시뮬레이션을 실행하세요.", parent=self
            )
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="그래프 PNG 저장",
            defaultextension=".png",
            initialfile="승강기_전기에너지비교.png"
            if mode == "electrical"
            else "승강기_S-Curve.png",
            filetypes=[("PNG 이미지", "*.png")],
        )
        if not path:
            return
        try:
            palette = get_theme(self)[1]
            try:
                from src.ui.plot_render import render_plot
            except ImportError:
                from src.ui.native_plot import render_png

                Path(path).write_bytes(
                    render_png(profile, palette, reference, size=(1100, 440))
                )
            else:
                render_plot(
                    profile, palette, reference, size=(1100, 440), scale=2
                ).save(path, format="PNG")
        except (OSError, ValueError) as error:
            messagebox.showerror("PNG 저장 실패", str(error), parent=self)
        else:
            messagebox.showinfo(
                "PNG 저장", f"그래프를 저장했습니다.\n{path}", parent=self
            )

    def _choose_measurement(self, entry):
        path = filedialog.askopenfilename(
            parent=self, title="실측 운행 CSV 선택", filetypes=[("CSV", "*.csv")]
        )
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def _show(self, s, error=False):
        self.services.set_result_display(self.result_text, s, error)

    def _show_energy(self, s, error=False):
        self.services.set_result_display(self.energy_result, s, error)

    def _queue_plot_redraw(self, mode):
        key = "_pending_" + mode + "_redraw"
        pending = getattr(self, key, None)
        if pending is not None:
            self.after_cancel(pending)
        action = self.redraw_energy_plot if mode == "electrical" else self.redraw_plot

        def render():
            setattr(self, key, None)
            action()

        setattr(self, key, self.after(80, render))

    def redraw_plot(self):
        if hasattr(self, "plot"):
            draw_scurve_plot(self.plot, self._profile, get_theme(self.plot)[1])
            refresh_live_graphs(self, "mechanical")

    def redraw_energy_plot(self):
        if hasattr(self, "energy_plot"):
            draw_energy_comparison(
                self.energy_plot,
                self._reference_energy_profile,
                self._energy_profile,
                get_theme(self.energy_plot)[1],
            )
            refresh_live_graphs(self, "electrical")

    def capture_state(self):
        state = {key: entry.get() for key, entry in self.entries.items()}
        if hasattr(self, "energy_entries"):
            state["_energy"] = {
                key: entry.get() for key, entry in self.energy_entries.items()
            }
            state["_direction"] = self.direction.get()
            state["_measurement_paths"] = {
                key: entry.get() for key, entry in self.measurement_paths.items()
            }
        return state

    def apply_state(self, state, remember_undo=True):
        if not isinstance(state, dict):
            return
        if remember_undo:
            self.services.push_undo_state(self)
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, str(state.get(key, "")))
        if hasattr(self, "energy_entries"):
            energy = state.get("_energy", {})
            defaults = {key: default for key, _, default in self.ENERGY_FIELDS}
            for key, entry in self.energy_entries.items():
                entry.delete(0, tk.END)
                entry.insert(0, str(energy.get(key, defaults[key])))
            self.direction.set(state.get("_direction", "상승"))
            paths = state.get("_measurement_paths", {})
            for key, entry in self.measurement_paths.items():
                entry.delete(0, tk.END)
                entry.insert(0, str(paths.get(key, "")))

    def undo_last(self):
        self.services.undo_panel(self)

    def clear(self):
        self.services.push_undo_state(self)
        for entry in (
            *self.entries.values(),
            *getattr(self, "energy_entries", {}).values(),
            *getattr(self, "measurement_paths", {}).values(),
        ):
            entry.delete(0, tk.END)
        self._show("입력값을 삭제했습니다.")
        if hasattr(self, "energy_result"):
            self._show_energy("입력값을 삭제했습니다.")

    def calculate_energy(self, record=False, precomputed=None, premeasurements=None):
        try:
            values = {
                key: parse_number(entry.get(), key)
                for key, entry in self.energy_entries.items()
            }
            shared = dict(
                distance=parse_number(self.entries["distance"].get(), "운행거리"),
                car_mass=values["car_mass"],
                load_mass=values["load_mass"],
                counterweight_mass=values["counterweight_mass"],
                equivalent_extra_mass=values["equivalent_extra_mass"],
                resistance=values["resistance"],
                direction=self.direction.get(),
                drive_efficiency=values["drive_efficiency"],
                regen_efficiency=values["regen_efficiency"],
                auxiliary_kw=values["auxiliary_kw"],
            )
            result = (
                precomputed
                if precomputed is not None
                else compare_trips(
                    shared,
                    dict(
                        vmax=values["ref_vmax"],
                        amax=values["ref_amax"],
                        jerk=values["ref_jerk"],
                    ),
                    dict(
                        vmax=values["candidate_vmax"],
                        amax=values["candidate_amax"],
                        jerk=values["candidate_jerk"],
                    ),
                )
            )
            self._reference_energy_profile = result["reference"]
            self._energy_profile = result["candidate"]
            self._graph_state_electrical = panel_state(self, "electrical")
            self.redraw_energy_plot()
            lines = [
                "[동일 조건 두 곡선의 전기에너지 추정]",
                "일정 효율·일정 저항의 단순 모델. 실측 없이 제조사 절감 성능으로 해석할 수 없습니다.",
                f"운행거리 {shared['distance']:g} m · {shared['direction']} · 적재 {shared['load_mass']:g} kg",
            ]
            for label, key in (("기준", "reference"), ("후보", "candidate")):
                p = result[key]
                lines.append(
                    f"{label}: 운행 {p['duration_s']:.2f} s / 실제 최고속도 {p['peak_speed_m_s']:.3f} m/s / "
                    f"구동 {p['draw_kwh']:.6f}, 회수 {p['returned_kwh']:.6f}, 보조 {p['auxiliary_kwh']:.6f} kWh → 순 {p['net_kwh']:.6f} kWh"
                )
            percent = (
                f"{result['difference_pct']:+.2f}% (모델 추정)"
                if result["difference_pct"] is not None
                else "기준 순사용량 ≤ 0: 비율 미표시"
            )
            lines.append(
                f"순 사용량 차이(기준−후보): {result['difference_kwh']:+.6f} kWh / {percent}"
            )
            lines.append(
                f"운행시간 차이(후보−기준): {result['candidate']['duration_s'] - result['reference']['duration_s']:+.2f} s"
            )
            measurements = {}
            for key, label in (("reference", "기준"), ("candidate", "후보")):
                path = self.measurement_paths[key].get().strip()
                if path:
                    m = (
                        premeasurements[key]
                        if premeasurements is not None
                        else read_measurement(path, result[key])
                    )
                    measurements[key] = m
                    error = (
                        f"{m['energy_error_pct']:+.2f}%"
                        if m["energy_error_pct"] is not None
                        else "실측 0: 비율 미표시"
                    )
                    lines.append(
                        f"{label} 실측: {m['measured_kwh']:.6f} kWh / 예측 오차 {m['energy_error_kwh']:+.6f} kWh ({error}) / 속도 RMSE {m['speed_rmse_m_s']:.3f} m/s"
                    )
            if len(measurements) == 2:
                measured = (
                    measurements["reference"]["measured_kwh"]
                    - measurements["candidate"]["measured_kwh"]
                )
                lines.append(
                    f"두 실측 운행 사용량 차이(기준−후보): {measured:+.6f} kWh (해당 한 쌍만)"
                )
            else:
                lines.append("실측 두 운행이 없으므로 절감률은 모델 추정치입니다.")
            lines.append("※ 운행시간·승차감·정지 오차를 별도로 확인해야 합니다.")
            self._show_energy("\n".join(lines))
            if record:
                self._record_simulation(
                    "electrical", f"순 사용량 {result['candidate']['net_kwh']:.6f} kWh"
                )
            return result
        except (ValueError, OverflowError, OSError) as error:
            self._energy_profile = None
            self._reference_energy_profile = None
            self._graph_state_electrical = None
            self.redraw_energy_plot()
            self._show_energy(f"입력/실측 오류: {error}", True)
            return None
        except Exception as error:
            self.services.log_unexpected_error("전기에너지 시뮬레이션", error)
            self._show_energy("계산 오류가 발생했습니다. 오류 로그를 확인하세요.", True)
            return None

    def calculate(self, record=False, precomputed=None):
        try:
            p = (
                precomputed
                if precomputed is not None
                else scurve_profile(
                    *(
                        parse_number(self.entries[k].get(), k)
                        for k in ("distance", "vmax", "amax", "jerk", "mass", "force")
                    )
                )
            )
            self._profile = p
            self._graph_state_mechanical = panel_state(self, "mechanical")
            self.redraw_plot()
            rows = p["samples"]
            stride = max(1, len(rows) // 18)
            lines = [
                "[단순화 S-Curve 운행 결과]",
                f"운행시간 {p['duration_s']:.2f} s / 최고속도 {p['peak_speed_m_s']:.3f} m/s / 정속 구간 {p['cruise_s']:.2f} s",
                f"최고 예상 기계동력(절댓값) {p['peak_mechanical_kw']:.2f} kW",
                f"구동 구간 기계적 일 {p['motoring_mechanical_wh']:.2f} Wh / 제동 구간 기계적 일 {p['braking_mechanical_wh']:.2f} Wh",
                "",
                "시간 s | 위치 m | 속도 m/s | 가속도 m/s² | 예상 기계동력 kW",
            ]
            lines.extend(
                f"{t:7.2f} | {x:7.2f} | {v:7.3f} | {a:8.3f} | {power:7.2f}"
                for t, x, v, a, power in rows[::stride]
            )
            lines.extend(
                [
                    "",
                    "※ F=(등가 이동질량×가속도)+입력한 불평형 합력, P=F×v로 계산한 기계적 일입니다. 제동 구간 수치는 회생 가능한 전기에너지가 아닙니다.",
                    "※ 구동 효율·회생 경로·손실·대기전력을 반영하지 않습니다. S-Curve만으로 에너지 절감을 판정할 수 없습니다.",
                ]
            )
            self._show("\n".join(lines))
            if record:
                self._record_simulation(
                    "mechanical",
                    f"운행 {p['duration_s']:.2f} s / 최고속도 {p['peak_speed_m_s']:.3f} m/s",
                )
        except (ValueError, OverflowError) as error:
            self._profile = None
            self._graph_state_mechanical = None
            self.redraw_plot()
            self._show(f"입력 오류: {error}", True)
        except Exception as error:
            self.services.log_unexpected_error("기계동력 시뮬레이션", error)
            self._show("계산 오류가 발생했습니다. 오류 로그를 확인하세요.", True)
