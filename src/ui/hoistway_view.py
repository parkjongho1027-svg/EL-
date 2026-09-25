"""Scrollable floor-selection and motion view for the engineering tools dialog."""

import tkinter as tk
from tkinter import ttk

from src.core.errors import CalculationInputError
from src.core.hoistway import HoistwayTrip, trip_phase
from src.core.trajectory import scurve_profile
from src.ui.hoistway_geometry import HoistwayGeometry
from src.ui.theme_manager import get_theme
from src.ui.ui_components import SkyButton, messagebox


class HoistwayView(tk.Frame):
    def __init__(self, parent, panel, window):
        super().__init__(parent)
        self.panel, self.window = panel, window
        self.profile = None
        self.playing = False
        self.after_id = None
        self.arrived = False
        self.structure_key = None
        self.floor_count = tk.StringVar(value="10")
        self.start_floor = tk.StringVar(value="1")
        self.end_floor = tk.StringVar(value="10")

        left = tk.Frame(self, width=315)
        left.pack(side="left", fill="y", padx=(12, 5), pady=8)
        left.pack_propagate(False)
        right = tk.Frame(self)
        right.pack(side="right", fill="both", expand=True, padx=(5, 12), pady=8)

        tk.Label(left, text="운행 설정", font=("맑은 고딕", 12, "bold"), anchor="w").pack(fill="x", pady=(0, 10))
        self.count_box = self._row(left, "전체 층수", self.floor_count, list(range(2, 101)))
        self.start_box = self._row(left, "출발층", self.start_floor, readonly_entry=True)
        self.end_box = self._row(left, "도착층", self.end_floor, list(range(1, 11)))
        tk.Label(left, text="도착 후 출발층이 자동으로 바뀝니다.\n오른쪽 층 번호를 눌러 바로 이동할 수도 있습니다.",
                 anchor="w", justify="left", wraplength=285).pack(fill="x", pady=(12, 10))
        tk.Label(left, text="운행 시간 (s)", anchor="w").pack(fill="x")
        self.slider = tk.Scale(left, orient="horizontal", resolution=0.05,
                               showvalue=True, command=self.redraw)
        self.slider.pack(fill="x", pady=(0, 8))
        buttons = tk.Frame(left)
        buttons.pack(fill="x", pady=6)
        SkyButton(buttons, text="위치 갱신", command=self.calculate, width=12).pack(side="left", padx=(0, 5))
        SkyButton(buttons, text="재생 / 정지", command=self.toggle, width=12).pack(side="left")

        current = tk.LabelFrame(left, text="현재 상태", padx=9, pady=10)
        current.pack(fill="x", pady=(18, 8))
        self.phase_label = tk.Label(current, text="출발", anchor="w", font=("맑은 고딕", 18, "bold"))
        self.phase_label.pack(fill="x")
        self.phase_bar = tk.Frame(current)
        self.phase_bar.pack(fill="x", pady=8)
        self.phase_labels = {}
        for phase in ("출발", "가속", "주행", "감속", "도착"):
            label = tk.Label(self.phase_bar, text=phase, width=5)
            label.pack(side="left", padx=1)
            self.phase_labels[phase] = label
        self.status_label = tk.Label(current, text="운행 경로를 선택하세요.", anchor="w",
                                     justify="left", wraplength=270)
        self.status_label.pack(fill="x", pady=(3, 0))
        tk.Label(left, text="1:1 로핑 위치 도식입니다. 기계동력 입력의 거리를 전체 승강행정으로 보고 층고를 동일하게 나눕니다. 카와 균형추 크기는 실제 치수가 아니며 간섭·안전 검증에 사용할 수 없습니다.",
                 anchor="nw", justify="left", wraplength=285).pack(fill="x", pady=(20, 0))

        tk.Label(right, text="승강로 위치 · 층 번호 클릭으로 이동", anchor="w",
                 font=("맑은 고딕", 11, "bold")).pack(fill="x", pady=(0, 5))
        chart = tk.Frame(right)
        chart.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(chart, highlightthickness=1, cursor="arrow")
        self.scrollbar = ttk.Scrollbar(chart, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self.redraw)
        self.canvas.bind("<MouseWheel>", self.scroll_wheel)
        self.canvas.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(2, "units"))
        self.count_box.bind("<<ComboboxSelected>>", self.change_floor_count)
        self.end_box.bind("<<ComboboxSelected>>", self.destination_selected)

    @staticmethod
    def _row(parent, name, value, options=None, readonly_entry=False):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=name, width=9, anchor="w").pack(side="left")
        if readonly_entry:
            entry = ttk.Entry(row, textvariable=value, width=8, state="readonly")
        else:
            entry = ttk.Combobox(row, textvariable=value, values=options,
                                 width=7, state="readonly")
        entry.pack(side="left", padx=5)
        return entry

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
        self.end_box["values"] = list(range(1, count + 1))
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
            self.status_label.configure(text="기계동력 탭에서 운행 조건을 입력하세요.")
            if show_errors:
                messagebox.showerror("승강로 위치", f"기계동력 입력을 확인하세요: {error}", parent=self.window)
            return False
        self.stop()
        self.arrived = False
        self.profile = {**result, "trip": trip}
        self.structure_key = None
        self.slider.configure(to=result["duration_s"])
        self.slider.set(0)
        self.redraw()
        return True

    def play(self):
        if not self.profile and not self.calculate():
            return
        if float(self.slider.get()) >= self.profile["duration_s"]:
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
        self.redraw()
        if next_time >= duration:
            self.stop()
            return
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

    def redraw(self, _event=None):
        if not self.profile:
            return
        samples = self.profile["samples"]
        time = float(self.slider.get())
        if time >= self.profile["duration_s"] - 0.025:
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
        width = max(500, self.canvas.winfo_width())
        self.draw_structure(trip, geom, width, palette)
        self.canvas.delete("moving")
        cx = width / 2
        car_x, cw_x = cx - 96, cx + 96
        car_y = geom.car_bottom_y(trip, samples[index][1])
        weight_y = geom.counterweight_bottom_y(trip, samples[index][1])
        sheave = geom.top_px - 68
        for x, y in ((car_x, car_y - 58), (cw_x, weight_y - 64)):
            self.canvas.create_line(x, sheave, x, y, fill=palette["muted"], width=2, tags="moving")
        self.canvas.create_line(car_x, sheave, cw_x, sheave, fill=palette["muted"], width=2, tags="moving")
        for x in (car_x, cw_x):
            self.canvas.create_oval(x - 14, sheave - 14, x + 14, sheave + 14,
                                    fill=palette["surface"], outline=palette["muted"], width=2,
                                    tags="moving")
        # The car bottom (not its centre) coincides with each floor line.
        self.canvas.create_rectangle(car_x - 26, car_y - 58, car_x + 26, car_y,
                                     fill="#2879cc", outline="#164e87", width=2, tags="moving")
        self.canvas.create_text(car_x, car_y - 28, text="카", fill="white", tags="moving")
        self.canvas.create_rectangle(cw_x - 18, weight_y - 64, cw_x + 18, weight_y,
                                     fill="#d46a17", outline="#9a470d", width=2, tags="moving")
        self.canvas.create_text(cw_x, weight_y - 32, text="균형추", fill="white", tags="moving")
        phase = trip_phase(samples, index)
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
        visible = max(1, self.canvas.winfo_height())
        total = geom.height_px
        if total > visible:
            offset = max(0, min(total - visible, car_y - visible / 2))
            self.canvas.yview_moveto(offset / total)
