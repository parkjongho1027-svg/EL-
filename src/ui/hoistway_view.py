"""Scrollable floor-selection and motion view for the engineering tools dialog."""

import tkinter as tk
from tkinter import ttk

from src.core.errors import CalculationInputError
from src.core.hoistway import HoistwayTrip, PHASE_NAMES, trip_phase
from src.core.trajectory import scurve_profile
from src.ui.hoistway_geometry import HoistwayGeometry, HoistwayOverviewGeometry
from src.ui.theme_manager import get_theme
from src.ui.record_manager import open_record_manager
from src.ui.ui_components import SkyButton, app_ask_string, messagebox


class HoistwayView(tk.Frame):
    def __init__(self, parent, panel, window):
        super().__init__(parent)
        self.panel, self.window = panel, window
        self.profile = None
        self.playing = False
        self.after_id = None
        self.arrived = False
        self.structure_key = None
        self.source_snapshot = None
        self.floor_count = tk.StringVar(value="10")
        self.start_floor = tk.StringVar(value="1")
        self.end_floor = tk.StringVar(value="10")

        left_host = tk.Frame(self, width=365)
        left_host.pack(side="left", fill="y", padx=(12, 5), pady=8)
        left_host.pack_propagate(False)
        self.input_canvas = tk.Canvas(left_host, highlightthickness=0)
        input_scrollbar = ttk.Scrollbar(left_host, orient="vertical", command=self.input_canvas.yview)
        self.input_canvas.configure(yscrollcommand=input_scrollbar.set)
        input_scrollbar.pack(side="right", fill="y")
        self.input_canvas.pack(side="left", fill="both", expand=True)
        left = tk.Frame(self.input_canvas)
        left_window = self.input_canvas.create_window((2, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda _event: self.input_canvas.configure(
            scrollregion=self.input_canvas.bbox("all")))
        self.input_canvas.bind("<Configure>", lambda event: self.input_canvas.itemconfigure(
            left_window, width=max(1, event.width - 5)))
        right = tk.Frame(self)
        right.pack(side="right", fill="both", expand=True, padx=(5, 12), pady=8)

        tk.Label(left, text="운행 설정", font=("맑은 고딕", 12, "bold"), anchor="w").pack(fill="x", pady=(0, 10))
        self.count_box = self._row(left, "전체 층수", self.floor_count)
        self.start_box = self._row(left, "출발층", self.start_floor)
        self.end_box = self._row(left, "도착층", self.end_floor)
        tk.Label(left, text="도착 후 출발층이 자동으로 바뀝니다.\n오른쪽 층 번호를 눌러 바로 이동할 수도 있습니다.",
                 anchor="w", justify="left", wraplength=315).pack(fill="x", pady=(12, 10))
        tk.Label(left, text="운행 시간 (s)", anchor="w").pack(fill="x")
        self.slider = tk.Scale(left, orient="horizontal", resolution=0.05,
                               showvalue=True, command=self.redraw)
        self.slider.pack(fill="x", pady=(0, 8))
        SkyButton(left, text="재생 / 정지", command=self.toggle, width=16).pack(anchor="w", pady=6)
        history_buttons = tk.Frame(left)
        history_buttons.pack(fill="x", pady=(2, 6))
        SkyButton(history_buttons, text="시뮬레이션 저장", command=self.save_simulation, width=15).pack(side="left")
        SkyButton(history_buttons, text="시뮬레이션 관리", command=self.manage_simulations, width=15).pack(side="left", padx=6)

        current = tk.LabelFrame(left, text="현재 상태", padx=9, pady=10)
        current.pack(fill="x", pady=(18, 8))
        self.phase_label = tk.Label(current, text="jerk", anchor="w", font=("맑은 고딕", 18, "bold"))
        self.phase_label.pack(fill="x")
        self.phase_bar = tk.Frame(current)
        self.phase_bar.pack(fill="x", pady=8)
        self.phase_labels = {}
        for column in range(4):
            self.phase_bar.grid_columnconfigure(column, weight=1)
        for position, phase in enumerate((*PHASE_NAMES, "도착")):
            label = tk.Label(self.phase_bar, text=phase, font=("맑은 고딕", 9))
            label.grid(row=position // 4, column=position % 4, sticky="ew", padx=1, pady=2)
            self.phase_labels[phase] = label
        tk.Label(current, text="착상부: 감속을 완화하는 모델의 마지막 구간 (정밀 착상 제어 아님)",
                 anchor="w", justify="left", wraplength=305,
                 font=("맑은 고딕", 9)).pack(fill="x", pady=(0, 5))
        self.status_label = tk.Label(current, text="운행 경로를 선택하세요.", anchor="w",
                                     justify="left", wraplength=305)
        self.status_label.pack(fill="x", pady=(3, 0))
        source = tk.LabelFrame(left, text="시뮬레이션 입력 출처", padx=12, pady=12)
        source.pack(fill="x", pady=(12, 8))
        self.source_label = tk.Label(source, text="기계동력 곡선 탭의 입력값을 사용합니다.",
                                     anchor="w", justify="left", wraplength=305,
                                     font=("맑은 고딕", 10))
        self.source_label.pack(fill="x")
        tk.Label(left, text="1:1 로핑 위치 도식입니다. 기계동력 입력의 거리를 전체 승강행정으로 보고 층고를 동일하게 나눕니다. 카와 균형추 크기는 실제 치수가 아니며 간섭·안전 검증에 사용할 수 없습니다.",
                 anchor="nw", justify="left", wraplength=315).pack(fill="x", pady=(15, 8))

        def scroll_input(event):
            if getattr(event, "num", None) in (4, 5):
                amount = -1 if event.num == 4 else 1
            else:
                amount = -1 if event.delta > 0 else 1
            self.input_canvas.yview_scroll(amount * 2, "units")
            return "break"

        def bind_input_wheel(widget):
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(sequence, scroll_input, add="+")
            for child in widget.winfo_children():
                bind_input_wheel(child)

        bind_input_wheel(left)
        bind_input_wheel(self.input_canvas)

        tk.Label(right, text="승강로 위치 · 층 번호 클릭으로 이동", anchor="w",
                 font=("맑은 고딕", 11, "bold")).pack(fill="x", pady=(0, 5))
        chart = tk.Frame(right)
        chart.pack(fill="both", expand=True)
        self.overview_box = tk.LabelFrame(chart, text="전체 운행 축소도", width=210, padx=4, pady=4)
        self.overview_box.pack_propagate(False)
        self.overview_box.pack(side="right", fill="y", padx=(8, 0))
        self.overview_visible = True
        self.overview_canvas = tk.Canvas(self.overview_box, width=200, highlightthickness=0)
        self.overview_canvas.pack(fill="both", expand=True)
        self.overview_canvas.bind("<Configure>", self.redraw)
        self.canvas = tk.Canvas(chart, highlightthickness=1, cursor="arrow")
        self.scrollbar = ttk.Scrollbar(chart, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self.redraw)
        self.canvas.bind("<MouseWheel>", self.scroll_wheel)
        self.canvas.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(2, "units"))
        for entry in (self.count_box, self.start_box, self.end_box):
            entry.bind("<Return>", self.keyboard_route_changed)
            entry.bind("<KP_Enter>", self.keyboard_route_changed)
        self.count_box.bind("<FocusOut>", self.floor_count_focus_out)

    @staticmethod
    def _row(parent, name, value, options=None, readonly_entry=False):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=name, width=9, anchor="w").pack(side="left")
        entry = ttk.Entry(row, textvariable=value, width=9)
        entry.pack(side="left", padx=5)
        return entry

    def keyboard_route_changed(self, _event=None):
        """키보드로 입력한 층수를 검증하고 바로 해당 운행을 시작한다."""
        try:
            count = int(self.floor_count.get())
            start = int(self.start_floor.get())
            destination = int(self.end_floor.get())
            if not 2 <= count <= 100:
                raise ValueError
            if not 1 <= start <= count or not 1 <= destination <= count:
                raise ValueError
        except ValueError:
            self.status_label.configure(
                text="층수는 정수로 입력하세요. 전체 층수는 2~100, 출발층·도착층은 그 범위 안이어야 합니다."
            )
            return "break"
        self.structure_key = None
        if start == destination:
            self.status_label.configure(text=f"현재 {start}층입니다. 다른 목적층을 입력하세요.")
            return "break"
        if self.calculate():
            self.play()
        return "break"

    def floor_count_focus_out(self, _event=None):
        try:
            count = int(self.floor_count.get())
        except ValueError:
            return
        if 2 <= count <= 100:
            self.structure_key = None

    def _simulation_payload(self):
        if not self.profile:
            return None
        keys = ("distance", "vmax", "amax", "jerk", "mass", "force")
        return {
            "floor_count": self.floor_count.get(),
            "start_floor": self.start_floor.get(),
            "end_floor": self.end_floor.get(),
            "time_s": float(self.slider.get()),
            "motion_inputs": {key: self.panel.entries[key].get() for key in keys},
            "duration_s": float(self.profile.get("duration_s", 0.0)),
        }

    def save_simulation(self):
        payload = self._simulation_payload()
        if payload is None:
            messagebox.showinfo("시뮬레이션 저장", "운행 경로를 먼저 계산하세요.", parent=self.window)
            return
        name = app_ask_string(
            "시뮬레이션 저장", "시뮬레이션 이름", parent=self.window,
            initialvalue=f"{self.start_floor.get()}층 → {self.end_floor.get()}층",
        )
        if name is None or not name.strip():
            return
        owner = app_ask_string("시뮬레이션 저장", "담당자 이름 (선택)", parent=self.window)
        if owner is None:
            return
        try:
            self.panel.store.add_engineering_record("hoistway_simulation", name, owner, payload)
        except (ValueError, OSError) as error:
            messagebox.showerror("시뮬레이션 저장", str(error), parent=self.window)
            return
        messagebox.showinfo("시뮬레이션 저장", "현재 승강로 시뮬레이션을 저장했습니다.", parent=self.window)

    def _load_simulation(self, payload):
        inputs = payload.get("motion_inputs", {})
        for key, value in inputs.items():
            entry = self.panel.entries.get(key)
            if entry is not None:
                entry.delete(0, "end")
                entry.insert(0, str(value))
                entry.event_generate("<KeyRelease>")
        self.floor_count.set(str(payload.get("floor_count", "10")))
        count = max(2, min(100, int(self.floor_count.get())))
        self.start_floor.set(str(payload.get("start_floor", "1")))
        self.end_floor.set(str(payload.get("end_floor", str(count))))
        if self.calculate():
            saved_time = float(payload.get("time_s", 0.0))
            self.slider.set(max(0.0, min(saved_time, self.profile["duration_s"])))
            self.redraw()

    def manage_simulations(self):
        store = self.panel.store

        def records():
            rows = store.engineering_records("hoistway_simulation")
            output = []
            for index, record in reversed(list(enumerate(rows))):
                payload = record.get("payload", {})
                route = f"{payload.get('start_floor', '?')}층 → {payload.get('end_floor', '?')}층"
                output.append((index, (record.get("name", ""), record.get("owner", ""), route, record.get("saved_at", ""))))
            return output

        def load(indices):
            record = store.engineering_records("hoistway_simulation")[indices[0]]
            self._load_simulation(record.get("payload", {}))

        def delete(indices):
            store.delete_engineering_records("hoistway_simulation", indices)

        def rename(index, name):
            store.update_engineering_record("hoistway_simulation", index, name=name)

        def change_owner(indices, owner):
            for index in indices:
                store.update_engineering_record("hoistway_simulation", index, owner=owner)

        open_record_manager(
            self.window, "승강로 시뮬레이션 관리",
            (("name", "시뮬레이션명", 220), ("owner", "담당자", 120),
             ("route", "운행 구간", 160), ("date", "저장 시각", 160)),
            records, load, delete, rename=rename, change_owner=change_owner,
            multi_load=False, save_current=self.save_simulation, close_on_load=True,
        )

    def stop(self):
        self.playing = False
        if self.after_id is not None:
            try:
                self.window.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None

    def change_floor_count(self, _event=None):
        count = int(self.floor_count.get())
        if int(self.start_floor.get()) > count:
            self.start_floor.set("1")
        if int(self.end_floor.get()) > count or self.end_floor.get() == self.start_floor.get():
            self.end_floor.set(str(count if int(self.start_floor.get()) != count else 1))
        self.structure_key = None
        self.calculate()

    def destination_selected(self, _event=None):
        destination = int(self.end_floor.get())
        if self.profile is not None and 0 < self.slider.get() < self.profile["duration_s"]:
            # A new route from a moving car requires a stop model. Snap to the
            # nearest floor and state this approximation explicitly in the UI.
            trip = self.profile["trip"]
            samples = self.profile["samples"]
            time = float(self.slider.get())
            index = min(range(len(samples)), key=lambda i: abs(samples[i][0] - time))
            position, _ = trip.position(samples[index][1])
            nearest = min(trip.floors, max(1, int(position / trip.floor_height_m + 1.5)))
            self.start_floor.set(str(nearest))
            self.stop()
        if destination == int(self.start_floor.get()):
            self.status_label.configure(text=f"현재 {destination}층입니다. 다른 목적층을 선택하세요.")
            return
        if self.calculate():
            self.play()

    def select_floor(self, floor):
        self.end_floor.set(str(floor))
        self.destination_selected()

    def calculate(self, *, show_errors=True):
        if self.start_floor.get() == self.end_floor.get():
            self.status_label.configure(text="현재 층과 다른 목적층을 선택하세요.")
            return False
        try:
            values = [float(self.panel.entries[key].get()) for key in
                      ("distance", "vmax", "amax", "jerk", "mass", "force")]
            trip = HoistwayTrip(int(self.floor_count.get()), int(self.start_floor.get()),
                                int(self.end_floor.get()), values[0])
            result = scurve_profile(trip.distance_m, *values[1:])
        except (ValueError, CalculationInputError) as error:
            self.stop()
            self.profile = None
            self.canvas.delete("all")
            self.overview_canvas.delete("all")
            self.status_label.configure(text="기계동력 탭에서 운행 조건을 입력하세요.")
            if show_errors:
                messagebox.showerror("승강로 위치", f"기계동력 입력을 확인하세요: {error}", parent=self.window)
            return False
        self.stop()
        self.arrived = False
        self.profile = {**result, "trip": trip}
        self.source_snapshot = tuple(self.panel.entries[key].get() for key in
                                     ("distance", "vmax", "amax", "jerk", "mass", "force"))
        self.source_label.configure(text=(
            "기계동력 곡선 탭에서 가져옴\n"
            f"운행거리 {values[0]:g} m → 전체 {trip.floors}층 행정으로 가정\n"
            f"선택 구간 {trip.distance_m:g} m\n"
            f"최고속도 {values[1]:g} m/s · 가속도 {values[2]:g} m/s²\n"
            f"저크 {values[3]:g} m/s³\n"
            f"등가질량 {values[4]:g} kg · 합력 {values[5]:g} N\n"
            "질량·합력은 동력 계산용이며 위치에는 영향이 없습니다."
        ))
        self.structure_key = None
        self.slider.configure(to=result["duration_s"])
        self.slider.set(0)
        self.redraw()
        return True

    def play(self):
        if not self.profile and not self.calculate():
            return
        if self.arrived or float(self.slider.get()) >= self.profile["duration_s"] - 0.026:
            # The previous arrival has become the current departure floor.
            # A new destination must be chosen before another trip can start.
            self.status_label.configure(text="도착했습니다. 다음 목적층을 선택하세요.")
            return
        self.playing = True
        self.tick()

    def toggle(self):
        if self.playing:
            self.stop()
        else:
            self.play()

    def tick(self):
        self.after_id = None
        if not self.playing or not self.window.winfo_exists():
            return
        duration = self.profile["duration_s"]
        next_time = min(duration, float(self.slider.get()) + 0.08)
        self.slider.set(next_time)
        if next_time >= duration:
            # Tk Scale rounds values to 0.05 s. The rounded display position
            # can precede the exact final sample, so finish explicitly here.
            self.redraw(force_finish=True)
            self.stop()
            return
        self.redraw()
        self.after_id = self.window.after(80, self.tick)

    def scroll_wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120) * 2, "units")

    def draw_structure(self, trip, geom, width, palette):
        key = (trip.floors, width, palette["background"])
        if self.structure_key == key:
            return
        self.canvas.delete("all")
        self.structure_key = key
        self.canvas.configure(scrollregion=(0, 0, width, geom.height_px))
        cx = width / 2
        ink, line_color = palette["text"], palette["border"]
        for floor in range(1, trip.floors + 1):
            y = geom.floor_y(floor)
            tag = f"floor_{floor}"
            self.canvas.create_line(cx - 210, y, cx - 136, y, fill=line_color,
                                    width=10, tags=(tag, "structure"))
            self.canvas.create_text(cx - 218, y, text=f"{floor}층", anchor="e",
                                    fill=ink, font=("맑은 고딕", 10, "bold"),
                                    tags=(tag, "structure"))
            self.canvas.tag_bind(tag, "<Button-1>", lambda _event, n=floor: self.select_floor(n))
            self.canvas.tag_bind(tag, "<Enter>", lambda _event: self.canvas.configure(cursor="hand2"))
            self.canvas.tag_bind(tag, "<Leave>", lambda _event: self.canvas.configure(cursor="arrow"))
        for x in (cx - 96, cx + 96):
            self.canvas.create_line(x - 35, geom.top_px - 12, x - 35, geom.floor_y(1) + 8,
                                    fill=line_color, width=2, tags="structure")
            self.canvas.create_line(x + 35, geom.top_px - 12, x + 35, geom.floor_y(1) + 8,
                                    fill=line_color, width=2, tags="structure")

    def draw_overview(self, trip, traveled_m, palette):
        """Always show both moving bodies, even when the detailed view scrolls."""
        canvas = self.overview_canvas
        canvas.delete("all")
        geometry = HoistwayOverviewGeometry(trip.floors, max(220, canvas.winfo_height()))
        ink, border = palette["text"], palette["border"]
        car_x, weight_x = 82, 161
        sheave_y = geometry.top_px - 33
        canvas.create_text(7, 15, text=f"출발 {trip.start_floor}층", anchor="w", fill=ink)
        canvas.create_text(7, 36, text=f"도착 {trip.end_floor}층", anchor="w", fill=ink)
        canvas.create_text(166, 15, text="권상기", anchor="e", fill=ink)
        canvas.create_rectangle(67, sheave_y - 12, 176, sheave_y + 12,
                                fill=palette["surface"], outline=border)
        for x in (car_x, weight_x):
            canvas.create_line(x, geometry.top_px - 27, x, geometry.bottom_px + 4,
                               fill=border, width=2)
            canvas.create_oval(x - 8, sheave_y - 8, x + 8, sheave_y + 8,
                               fill=palette["surface"], outline=ink)
        canvas.create_line(car_x, sheave_y, weight_x, sheave_y, fill=ink, width=2)
        for floor, color in ((trip.start_floor, "#2879cc"), (trip.end_floor, "#d46a17")):
            y = geometry.floor_y(floor)
            canvas.create_line(14, y, 53, y, fill=color, width=2)
            canvas.create_line(53, y, 62, y, fill=color, width=1, dash=(2, 2))
        car_y = geometry.car_bottom_y(trip, traveled_m)
        weight_y = geometry.counterweight_bottom_y(trip, traveled_m)
        canvas.create_line(car_x, sheave_y, car_x, car_y - 26, fill=ink)
        canvas.create_line(weight_x, sheave_y, weight_x, weight_y - 30, fill=ink)
        canvas.create_rectangle(car_x - 13, car_y - 26, car_x + 13, car_y,
                                fill="#2879cc", outline="#164e87", width=2)
        canvas.create_rectangle(weight_x - 12, weight_y - 30, weight_x + 12, weight_y,
                                fill="#d46a17", outline="#9a470d", width=2)
        canvas.create_text(car_x, car_y - 13, text="카", fill="white", font=("맑은 고딕", 8))
        canvas.create_text(weight_x, weight_y - 15, text="추", fill="white", font=("맑은 고딕", 8))

    def sync_overview_visibility(self, geom, viewport_height):
        """전체 운행 축소도는 상세 화면 높이와 관계없이 항상 표시한다."""
        self.overview_visible = True

    def redraw(self, _event=None, *, force_finish=False):
        if not self.profile:
            return
        samples = self.profile["samples"]
        time = float(self.slider.get())
        if force_finish or time >= self.profile["duration_s"] - 0.026:
            index = len(samples) - 1
        else:
            index = min(len(samples) - 1, max(0, int(time / max(self.profile["duration_s"], .01) * (len(samples) - 1))))
            while index + 1 < len(samples) and samples[index + 1][0] <= time:
                index += 1
            while index > 0 and samples[index][0] > time:
                index -= 1
        trip = self.profile["trip"]
        geom = HoistwayGeometry(trip.floors)
        palette = get_theme(self.canvas)[1]
        visible = max(1, self.canvas.winfo_height())
        self.sync_overview_visibility(geom, visible)
        width = max(500, self.canvas.winfo_width())
        self.draw_structure(trip, geom, width, palette)
        self.draw_overview(trip, samples[index][1], palette)
        self.canvas.delete("moving")
        cx = width / 2
        car_x, cw_x = cx - 45, cx + 45
        car_y = geom.car_bottom_y(trip, samples[index][1])
        weight_y = geom.counterweight_bottom_y(trip, samples[index][1])
        traction_x = car_x + 8
        traction_y = geom.top_px - 88
        deflector_x = cw_x
        deflector_y = geom.top_px - 54
        car_rope_top = car_y - 58
        cw_rope_top = weight_y - 64
        self.canvas.create_line(car_x, car_rope_top, car_x, traction_y,
                                fill=palette["muted"], width=2, tags="moving")
        self.canvas.create_line(car_x, traction_y, traction_x, traction_y,
                                fill=palette["muted"], width=2, tags="moving")
        self.canvas.create_line(traction_x, traction_y, deflector_x, deflector_y,
                                fill=palette["muted"], width=2, tags="moving")
        self.canvas.create_line(deflector_x, deflector_y, cw_x, cw_rope_top,
                                fill=palette["muted"], width=2, tags="moving")
        self.canvas.create_oval(traction_x - 30, traction_y - 30,
                                traction_x + 30, traction_y + 30,
                                fill=palette["surface"], outline=palette["text"], width=3,
                                tags="moving")
        self.canvas.create_oval(deflector_x - 12, deflector_y - 12,
                                deflector_x + 12, deflector_y + 12,
                                fill=palette["surface"], outline=palette["muted"], width=2,
                                tags="moving")
        # The car bottom (not its centre) coincides with each floor line.
        self.canvas.create_rectangle(car_x - 26, car_y - 58, car_x + 26, car_y,
                                     fill="#2879cc", outline="#164e87", width=2, tags="moving")
        self.canvas.create_text(car_x, car_y - 28, text="카", fill="white", font=("맑은 고딕", 12, "bold"), tags="moving")
        self.canvas.create_rectangle(cw_x - 18, weight_y - 64, cw_x + 18, weight_y,
                                     fill="#d46a17", outline="#9a470d", width=2, tags="moving")
        self.canvas.create_text(cw_x, weight_y - 32, text="균형추", fill="white", font=("맑은 고딕", 10, "bold"), tags="moving")
        phase = trip_phase(samples, index, self.profile["phase_durations_s"])
        self.phase_label.configure(text=phase)
        for name, label in self.phase_labels.items():
            label.configure(bg=palette["accent"] if name == phase else palette["surface"],
                            fg="white" if name == phase else palette["text"])
        car_height, _ = trip.position(samples[index][1])
        current = 1 + car_height / trip.floor_height_m
        self.status_label.configure(text=f"{trip.start_floor}층 → {trip.end_floor}층 · {'상승' if trip.direction > 0 else '하강'}\n"
                                         f"현재 약 {current:.1f}층 · {samples[index][0]:.2f}/{self.profile['duration_s']:.2f}초")
        if index == len(samples) - 1 and not self.arrived:
            self.arrived = True
            self.start_floor.set(str(trip.end_floor))
        total = geom.height_px
        if total > visible:
            offset = max(0, min(total - visible, car_y - visible / 2))
            self.canvas.yview_moveto(offset / total)
