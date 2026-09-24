"""Shared live chart windows, PNG export, and saved-graph management."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from src.core.capacity import simulate_five_minutes
from src.core.rope_traction import tension_by_height
from src.core.elevator_review_engine import scurve_profile
from src.core.energy_model import compare_trips
from src.core.errors import CalculationInputError
from src.ui.chart_png import export_chart_png
from src.ui.graph_axes import axes_for_graphs
from src.ui.record_manager import open_record_manager
from native_plot import render_png
from theme_manager import apply_theme, get_theme
from ui_components import SkyButton, WindowManager, app_ask_string, messagebox
from utils import parse_number

TITLES = {
    "traction": "로프 가닥별 정적 장력 분포",
    "traffic": "층별 5분 수송 인원",
    "mechanical": "기계동력 곡선",
    "electrical": "전기에너지 비교",
}
NOTICES = {
    "traction": "정적 위치별 모델: 가속·보상체인 제외. 법정 권상 판정에 사용하지 마세요.",
    "traffic": "균등 목적층·고정 탑승률의 5분 가상 운행. 실제 배차/대기열 자료가 아닙니다.",
    "mechanical": "단순화 운행 모델의 예상 기계동력. 실측 전기에너지가 아닙니다.",
    "electrical": "동일 운행 조건의 모델 추정치. 실측 없이 절감 성능을 검증할 수 없습니다.",
}


def graph_data(kind, state):
    """Calculate a saved graph from its own validated input snapshot."""
    if kind == "traction":
        source = state["values"]
        return tension_by_height(
            *(
                parse_number(source[key], key) / (100 if key == "OB" else 1)
                for key in ("Wc", "Q", "OB", "H", "wr", "n")
            )
        )
    if kind == "traffic":
        return simulate_five_minutes(**state)
    if kind == "mechanical":
        return scurve_profile(
            *(
                parse_number(state[key], key)
                for key in ("distance", "vmax", "amax", "jerk", "mass", "force")
            )
        )
    if kind == "electrical":
        values = {key: parse_number(raw, key) for key, raw in state["_energy"].items()}
        shared = dict(
            distance=parse_number(state["distance"], "distance"),
            car_mass=values["car_mass"],
            load_mass=values["load_mass"],
            counterweight_mass=values["counterweight_mass"],
            equivalent_extra_mass=values["equivalent_extra_mass"],
            resistance=values["resistance"],
            direction=state["_direction"],
            drive_efficiency=values["drive_efficiency"],
            regen_efficiency=values["regen_efficiency"],
            auxiliary_kw=values["auxiliary_kw"],
        )
        reference = {key: values["ref_" + key] for key in ("vmax", "amax", "jerk")}
        candidate = {
            key: values["candidate_" + key] for key in ("vmax", "amax", "jerk")
        }
        return compare_trips(shared, reference, candidate)
    raise ValueError("지원하지 않는 그래프입니다.")


def panel_state(panel, kind):
    if kind == "traffic":
        if (
            getattr(panel, "_last_capacity_state", None) is not None
            and panel.capture_state() != panel._last_capacity_state
        ):
            raise CalculationInputError(
                "입력 변경 후 교통량 계산이 완료되면 그래프가 갱신됩니다."
            )
        data = getattr(panel, "last_capacity_inputs", None)
        if not data:
            raise CalculationInputError("교통량을 먼저 계산하고 입력값을 확인하세요.")
        return dict(data)
    state = panel.capture_state()
    if kind == "mechanical":
        return {
            key: state[key]
            for key in ("distance", "vmax", "amax", "jerk", "mass", "force")
        }
    if kind == "electrical":
        # CSV paths are local to the user's machine and irrelevant to the model plot.
        state.pop("_measurement_paths", None)
    return state


def _draw_tension(canvas, samples, axes):
    canvas.delete("all")
    palette = get_theme(canvas)[1]
    canvas.configure(bg=palette["surface"])
    ink, grid = palette["text"], palette["border"]
    w, h = max(500, canvas.winfo_width()), max(250, canvas.winfo_height())
    x0, x1, y0, y1 = 90, w - 28, 40, h - 54
    x_max, y_max = axes["x_max"], axes["y_max"]
    for tick in range(round(y_max / axes["y_step"]) + 1):
        value = tick * axes["y_step"]
        y = y1 - (y1 - y0) * value / y_max
        canvas.create_line(x0, y, x1, y, fill=grid)
        canvas.create_text(x0 - 8, y, text=f"{value:g}", anchor="e", fill=ink)
    for tick in range(round(x_max / axes["x_step"]) + 1):
        value = tick * axes["x_step"]
        x = x0 + (x1 - x0) * value / x_max
        canvas.create_line(x, y0, x, y1, fill=grid)
        canvas.create_text(x, y1 + 16, text=f"{value:g}", fill=ink)
    for col, color in (
        (1, palette["accent"]),
        (2, "#ffbb77" if palette["background"] == "#000000" else "#d37a28"),
    ):
        coords = []
        for distance, car, counterweight in samples:
            value = car if col == 1 else counterweight
            coords.extend(
                (x0 + (x1 - x0) * distance / x_max, y1 - (y1 - y0) * value / y_max)
            )
        canvas.create_line(*coords, fill=color, width=2)
    canvas.create_text(
        x0, y0 - 22, text="파랑: 카측 / 주황: 균형추측 · N/가닥", anchor="w", fill=ink
    )
    canvas.create_text(
        x1, y1 + 34, text="카의 최하층부터 위치 (m)", anchor="e", fill=ink
    )


def _draw_capacity(canvas, result, axes):
    canvas.delete("all")
    palette = get_theme(canvas)[1]
    canvas.configure(bg=palette["surface"])
    ink, grid = palette["text"], palette["border"]
    values = result["per_floor"]
    w, h = max(500, canvas.winfo_width()), max(250, canvas.winfo_height())
    x0, x1, y0, y1 = 70, w - 25, 35, h - 55
    y_max, x_max = axes["y_max"], axes["x_max"]
    for tick in range(round(y_max / axes["y_step"]) + 1):
        value = tick * axes["y_step"]
        y = y1 - (y1 - y0) * value / y_max
        canvas.create_line(x0, y, x1, y, fill=grid)
        canvas.create_text(x0 - 8, y, text=f"{value:g}", anchor="e", fill=ink)
    for tick in range(round(x_max / axes["x_step"]) + 1):
        floor = tick * axes["x_step"]
        x = x0 + (x1 - x0) * floor / x_max
        canvas.create_line(x, y0, x, y1, fill=grid)
        canvas.create_text(x, y1 + 15, text=f"{floor + 2:g}", fill=ink)
    bar = (x1 - x0) / x_max
    for index, count in enumerate(values):
        x = x0 + index * bar
        canvas.create_rectangle(
            x + 1,
            y1 - (y1 - y0) * count / y_max,
            x + max(2, bar - 1),
            y1,
            fill=palette["accent"],
            outline="",
        )
    canvas.create_text(
        x0,
        y0 - 18,
        text=f"5분 완료 탑승 인원: {result['completed_people']}명",
        anchor="w",
        fill=ink,
    )
    canvas.create_text(x1, y1 + 34, text="목적층", anchor="e", fill=ink)


def _draw_simulation(canvas, kind, data, axes):
    canvas.delete("all")
    palette = get_theme(canvas)[1]
    canvas.configure(bg=palette["surface"])
    ink, grid = palette["text"], palette["border"]
    w, h = max(500, canvas.winfo_width()), max(280, canvas.winfo_height())
    left, right = 85, w - 25
    profiles = (
        ((data, palette["accent"]),)
        if kind == "mechanical"
        else ((data["reference"], "#2879cc"), (data["candidate"], "#d37a28"))
    )
    topplots = (
        (45, h * 0.46, "속도 (m/s)", 0, axes["speed_max"], axes["speed_step"], "speed"),
        (
            h * 0.60,
            h - 42,
            "계통전력 (kW)" if kind == "electrical" else "기계동력 (kW)",
            axes["power_min"],
            axes["power_max"],
            axes["power_step"],
            "power",
        ),
    )
    for top, bottom, title, low, high, step, series in topplots:
        canvas.create_text(
            left,
            top - 18,
            text=title,
            anchor="w",
            fill=ink,
            font=("맑은 고딕", 9, "bold"),
        )
        count = min(12, round((high - low) / step))
        for tick in range(count + 1):
            value = low + tick * step
            y = bottom - (bottom - top) * (value - low) / (high - low)
            canvas.create_line(left, y, right, y, fill=grid)
            canvas.create_text(left - 7, y, text=f"{value:g}", anchor="e", fill=ink)
        for tick in range(round(axes["x_max"] / axes["x_step"]) + 1):
            time = tick * axes["x_step"]
            x = left + (right - left) * time / axes["x_max"]
            canvas.create_line(x, top, x, bottom, fill=grid)
            if series == "power":
                canvas.create_text(x, bottom + 16, text=f"{time:g}", fill=ink)
        for profile, color in profiles:
            samples = profile["samples"]
            values = (
                [sample[2] for sample in samples]
                if series == "speed"
                else profile["grid_kw_samples"]
                if kind == "electrical"
                else profile["signed_mechanical_kw_samples"]
            )
            stride = max(1, len(samples) // 600)
            indices = list(range(0, len(samples), stride))
            if indices[-1] != len(samples) - 1:
                indices.append(len(samples) - 1)
            coords = []
            for index in indices:
                coords.extend(
                    (
                        left + (right - left) * samples[index][0] / axes["x_max"],
                        bottom - (bottom - top) * (values[index] - low) / (high - low),
                    )
                )
            if len(coords) >= 4:
                canvas.create_line(*coords, fill=color, width=2)
    canvas.create_text(right, h - 9, text="시간 (s)", anchor="e", fill=ink)
    if kind == "electrical":
        canvas.create_text(
            left, 17, text="기준(파랑) / 후보(주황)", anchor="w", fill=ink
        )


def _render(canvas, kind, data, axes=None):
    axes = axes or axes_for_graphs(kind, [data])
    if kind == "traction":
        _draw_tension(canvas, data, axes)
    elif kind == "traffic":
        _draw_capacity(canvas, data, axes)
    else:
        _draw_simulation(canvas, kind, data, axes)


def _png(kind, data, palette, axes=None):
    axes = axes or axes_for_graphs(kind, [data])
    if kind in ("traction", "traffic"):
        return export_chart_png(
            kind, data if kind == "traction" else data["per_floor"], axes=axes
        )
    return render_png(
        data if kind == "mechanical" else data["candidate"],
        palette,
        data["reference"] if kind == "electrical" else None,
        size=(1100, 500),
        axes=axes,
    )


class GraphWindow:
    """One chart; live source recomputes after changes, saved source stays independent."""

    def __init__(
        self, panel, kind, *, source=None, state=None, name=None, owner="", axes=None
    ):
        self.panel, self.kind, self.source, self.state = panel, kind, source, state
        self.name, self.owner, self.data = name or TITLES[kind], owner, None
        self.axes = axes
        self.window = tk.Toplevel(panel)
        self.window._ui_theme = getattr(panel.winfo_toplevel(), "_ui_theme", "light")
        self.window.title(self.name)
        self.window.geometry("830x535")
        self.window.minsize(560, 350)
        self.window.transient(panel.winfo_toplevel())
        self.status = tk.Label(
            self.window, text=NOTICES[kind], anchor="w", wraplength=780
        )
        self.status.pack(fill="x", padx=12, pady=6)
        bar = tk.Frame(self.window)
        bar.pack(side="bottom", fill="x", padx=10, pady=8)
        for text, action in (
            ("창 고정", self.toggle_pin),
            ("PNG 저장", self.save_png),
            ("그래프 저장", self.save_graph),
            (
                "시뮬레이션 관리"
                if kind in ("mechanical", "electrical")
                else "그래프 관리",
                lambda: manage_graphs(panel, kind),
            ),
        ):
            button = SkyButton(bar, text=text, command=action, font=("맑은 고딕", 9))
            button.pack(side="left", padx=2)
            if text == "창 고정":
                self.pin_button = button
        self.canvas = tk.Canvas(self.window, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=4)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.window.bind("<Destroy>", self._destroyed, add="+")
        self._pinned = False
        self._pending = None
        apply_theme(self.window, self.window._ui_theme)
        self.refresh()
        root = panel.winfo_toplevel()
        if not hasattr(root, "_graph_windows"):
            root._graph_windows = []
        root._graph_windows.append(self)

    def _destroyed(self, event):
        if event.widget is self.window:
            if self._pending is not None:
                try:
                    self.window.after_cancel(self._pending)
                except tk.TclError:
                    pass
            try:
                root = self.panel.winfo_toplevel()
                if hasattr(root, "_graph_windows") and self in root._graph_windows:
                    root._graph_windows.remove(self)
            except tk.TclError:
                pass

    def schedule(self, _event=None):
        if not self.window.winfo_exists():
            return
        if self._pending is not None:
            self.window.after_cancel(self._pending)
        self._pending = self.window.after(550, self.refresh)

    def refresh(self):
        self._pending = None
        try:
            self.state = self.source() if self.source is not None else self.state
            if self.source is not None and self.kind in ("mechanical", "electrical"):
                state_key = "_graph_state_" + self.kind
                if self.state != getattr(self.panel, state_key, None):
                    self.data = None
                    self.canvas.delete("all")
                    self.status.configure(
                        text="계산이 완료되면 그래프가 갱신됩니다. 입력값을 확인하세요."
                    )
                    return
                if self.kind == "mechanical":
                    self.data = self.panel._profile
                else:
                    self.data = {
                        "reference": self.panel._reference_energy_profile,
                        "candidate": self.panel._energy_profile,
                    }
                if self.data is None or (
                    self.kind == "electrical"
                    and (
                        self.data["reference"] is None or self.data["candidate"] is None
                    )
                ):
                    self.status.configure(
                        text="시뮬레이션을 실행하면 그래프가 갱신됩니다."
                    )
                    return
            else:
                self.data = graph_data(self.kind, self.state)
        except (
            CalculationInputError,
            ValueError,
            KeyError,
            TypeError,
            OverflowError,
        ) as error:
            self.data = None
            self.canvas.delete("all")
            self.status.configure(text=f"입력 확인: {error}")
            return
        self.status.configure(text=NOTICES[self.kind])
        self.redraw()

    def redraw(self):
        if self.data is not None:
            _render(self.canvas, self.kind, self.data, self.axes)

    def toggle_pin(self):
        self._pinned = not self._pinned
        self.window.attributes("-topmost", self._pinned)
        self.pin_button.configure(text="고정 해제" if self._pinned else "창 고정")

    def save_png(self):
        if self.data is None:
            messagebox.showinfo(
                "PNG 저장",
                "먼저 올바른 입력값으로 그래프를 계산하세요.",
                parent=self.window,
            )
            return
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title="그래프 PNG 저장",
            defaultextension=".png",
            initialfile=f"{self.name}.png",
            filetypes=[("PNG 이미지", "*.png")],
        )
        if not path:
            return
        try:
            Path(path).write_bytes(
                _png(self.kind, self.data, get_theme(self.canvas)[1], self.axes)
            )
        except (OSError, ValueError) as error:
            messagebox.showerror("PNG 저장 실패", str(error), parent=self.window)
        else:
            messagebox.showinfo(
                "PNG 저장", f"그래프를 저장했습니다.\n{path}", parent=self.window
            )

    def save_graph(self):
        if self.data is None:
            messagebox.showinfo(
                "그래프 저장", "입력값을 확인하세요.", parent=self.window
            )
            return
        name = app_ask_string(
            "그래프 저장", "그래프 이름", parent=self.window, initialvalue=self.name
        )
        if name is None:
            return
        owner = app_ask_string(
            "그래프 저장", "담당자 이름", parent=self.window, initialvalue=self.owner
        )
        if owner is None:
            return
        if not name.strip() or not owner.strip():
            messagebox.showerror(
                "그래프 저장",
                "그래프 이름과 담당자 이름을 모두 입력하세요.",
                parent=self.window,
            )
            return
        self.panel.store.add_graph(self.kind, name, owner, self.state)
        self.name, self.owner = name.strip(), owner.strip()
        self.window.title(self.name)
        messagebox.showinfo(
            "그래프 저장",
            "입력 조건과 이름, 담당자를 저장했습니다.",
            parent=self.window,
        )


def open_graph(panel, kind, *, live=True, state=None, name=None, owner="", axes=None):
    if kind not in TITLES:
        raise ValueError("지원하지 않는 그래프입니다.")
    source = (lambda: panel_state(panel, kind)) if live else None
    chart = GraphWindow(
        panel, kind, source=source, state=state, name=name, owner=owner, axes=axes
    )
    if live:
        bindings = []
        traces = []
        entries = list(getattr(panel, "entries", {}).values())
        if kind == "electrical":
            entries += list(panel.energy_entries.values())
            traces.append(
                (
                    panel.direction,
                    panel.direction.trace_add("write", lambda *_: chart.schedule()),
                )
            )
        for entry in entries:
            for sequence in ("<KeyRelease>", "<FocusOut>"):
                bindings.append(
                    (entry, sequence, entry.bind(sequence, chart.schedule, add="+"))
                )
        if kind == "traffic":
            for variable in (
                panel.building_use,
                panel.criterion_mode,
                panel.stop_count_mode,
                panel.service_type,
            ):
                traces.append(
                    (variable, variable.trace_add("write", lambda *_: chart.schedule()))
                )

        def cleanup(event):
            if event.widget is chart.window:
                for entry, sequence, ident in bindings:
                    try:
                        if entry.winfo_exists():
                            entry.unbind(sequence, ident)
                    except tk.TclError:
                        pass
                for variable, ident in traces:
                    try:
                        variable.trace_remove("write", ident)
                    except tk.TclError:
                        pass

        chart.window.bind("<Destroy>", cleanup, add="+")
    return chart.window


def save_current_graph(panel, kind):
    try:
        state = panel_state(panel, kind)
        graph_data(kind, state)
    except (
        CalculationInputError,
        ValueError,
        KeyError,
        TypeError,
        OverflowError,
    ) as error:
        messagebox.showerror("그래프 저장", str(error), parent=panel)
        return None
    name = app_ask_string(
        "그래프 저장", "그래프 이름", parent=panel, initialvalue=TITLES[kind]
    )
    if name is None:
        return None
    owner = app_ask_string("그래프 저장", "담당자 이름", parent=panel)
    if owner is None:
        return None
    if not name.strip() or not owner.strip():
        messagebox.showerror(
            "그래프 저장", "그래프 이름과 담당자 이름을 모두 입력하세요.", parent=panel
        )
        return None
    return panel.store.add_graph(kind, name, owner, state)


def close_graphs(panel, kind):
    root = panel.winfo_toplevel()
    for graph in tuple(getattr(root, "_graph_windows", ())):
        if graph.panel is panel and graph.kind == kind and graph.window.winfo_exists():
            graph.window.destroy()


def refresh_live_graphs(panel, kind):
    root = panel.winfo_toplevel()
    for graph in tuple(getattr(root, "_graph_windows", ())):
        if graph.panel is panel and graph.kind == kind and graph.source is not None:
            graph.schedule()


def manage_graphs(panel, kind):
    """Show only the current chart type and compare selected records on common axes."""
    if kind not in TITLES:
        raise ValueError("지원하지 않는 그래프입니다.")
    store = panel.store
    title = (
        "시뮬레이션 관리 — "
        if kind in ("mechanical", "electrical")
        else "그래프 관리 — "
    ) + TITLES[kind]

    def records():
        return [
            (
                index,
                (item.get("name", ""), item.get("owner", ""), item.get("saved_at", "")),
            )
            for index, item in reversed(store.graph_history(kind))
        ]

    def load(indices):
        saved = dict(store.graph_history(kind))
        prepared = []
        invalid = []
        for index in indices:
            record = saved.get(index)
            if record is None:
                continue
            try:
                prepared.append((record, graph_data(kind, record["state"])))
            except (
                CalculationInputError,
                ValueError,
                TypeError,
                KeyError,
                OverflowError,
            ) as error:
                invalid.append(f"{record.get('name', index)}: {error}")
        if invalid:
            messagebox.showerror(
                title, "불러올 수 없는 기록:\n" + "\n".join(invalid), parent=panel
            )
        if not prepared:
            return
        axes = axes_for_graphs(kind, [data for _, data in prepared])
        created = [
            open_graph(
                panel,
                kind,
                live=False,
                state=record["state"],
                name=record.get("name"),
                owner=record.get("owner", ""),
                axes=axes,
            )
            for record, _data in prepared
        ]
        screen_w = created[0].winfo_screenwidth()
        screen_h = created[0].winfo_screenheight()
        columns = min(3, max(1, screen_w // 560), len(created))
        rows = (len(created) + columns - 1) // columns
        width = min(780, max(510, (screen_w - 40) // columns))
        height = min(535, max(320, (screen_h - 90) // rows))
        for index, chart in enumerate(created):
            chart.geometry(
                f"{width}x{height}+{20 + index % columns * width}+{30 + index // columns * height}"
            )

    def delete(indices):
        store.delete_graphs(indices)

    def rename(index, name):
        store.update_graph(index, name=name)

    def change_owner(indices, owner):
        for index in indices:
            store.update_graph(index, owner=owner)

    return open_record_manager(
        panel,
        title,
        (
            ("name", "그래프명", 330),
            ("owner", "담당자", 160),
            ("date", "저장 시각", 170),
        ),
        records,
        load,
        delete,
        rename=rename,
        change_owner=change_owner,
        save_current=lambda: save_current_graph(panel, kind),
    )
