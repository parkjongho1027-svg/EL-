"""승강로 층 선택, 운행 재생, 카·균형추 화면 표시를 담당하는 UI 모듈."""

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
        """승강로 시뮬레이션에 필요한 입력창, 상태창, 그림 영역을 만든다."""
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

        # 왼쪽 설정·상태 영역은 내용이 창 높이보다 길어져도 모두 확인할 수 있게
        # Canvas 안에 넣고 세로 스크롤을 항상 제공한다.
        left_shell = tk.Frame(self, width=330)
        left_shell.pack(side="left", fill="y", padx=(12, 5), pady=8)
        left_shell.pack_propagate(False)
        left_canvas = tk.Canvas(left_shell, highlightthickness=0, width=305)
        left_scrollbar = ttk.Scrollbar(left_shell, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        left_scrollbar.pack(side="right", fill="y")
        left_canvas.pack(side="left", fill="both", expand=True)
        left = tk.Frame(left_canvas, width=295)
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def update_left_scroll(_event=None):
            """왼쪽 내용 크기에 맞춰 스크롤 범위와 내부 폭을 갱신한다."""
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))
            left_canvas.itemconfigure(left_window, width=max(280, left_canvas.winfo_width()))

        left.bind("<Configure>", update_left_scroll)
        left_canvas.bind("<Configure>", update_left_scroll)

        def scroll_left(event):
            """마우스 휠로 왼쪽 설정·현재 상태·입력 출처를 위아래로 이동한다."""
            if getattr(event, "delta", 0):
                left_canvas.yview_scroll(-int(event.delta / 120) * 2, "units")

        left_canvas.bind("<MouseWheel>", scroll_left)
        left.bind("<MouseWheel>", scroll_left)

        right = tk.Frame(self)
        right.pack(side="right", fill="both", expand=True, padx=(5, 12), pady=8)

        tk.Label(left, text="운행 설정", font=("맑은 고딕", 12, "bold"), anchor="w").pack(fill="x", pady=(0, 10))
        self.count_box = self._row(left, "전체 층수", self.floor_count)
        self.start_box = self._row(left, "출발층", self.start_floor)
        self.end_box = self._row(left, "도착층", self.end_floor)
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
        self.phase_bar.pack(fill="x", pady=(8, 4))
        self.phase_labels = {}
        phases = ("Jerk", "일정가속", "가속라운드", "전속",
                  "감속라운드", "일정감속", "착상부", "도착")
        for number, phase in enumerate(phases):
            label = tk.Label(self.phase_bar, text=phase, font=("맑은 고딕", 8, "bold"))
            label.grid(row=number // 4, column=number % 4, padx=3, pady=2, sticky="w")
            self.phase_labels[phase] = label
        self.phase_description = tk.Label(current, text="", anchor="w",
                                          justify="left", wraplength=270)
        self.phase_description.pack(fill="x", pady=(5, 3))
        self.status_label = tk.Label(current, text="운행 경로를 선택하세요.", anchor="w",
                                     justify="left", wraplength=270)
        self.status_label.pack(fill="x", pady=(3, 0))

        source = tk.LabelFrame(left, text="시뮬레이션 입력 출처", padx=9, pady=8)
        source.pack(fill="x", pady=(8, 6))
        self.source_label = tk.Label(source, text="기계동력 곡선 탭의 입력값을 사용합니다.",
                                     anchor="w", justify="left", wraplength=270,
                                     font=("맑은 고딕", 9))
        self.source_label.pack(fill="x")
        tk.Label(left, text="1:1 로핑 위치 도식입니다. 기계동력 입력의 거리를 전체 승강행정으로 보고 층고를 동일하게 나눕니다. 카와 균형추 크기는 실제 치수가 아니며 간섭·안전 검증에 사용할 수 없습니다.",
                 anchor="nw", justify="left", wraplength=285).pack(fill="x", pady=(8, 0))

        tk.Label(right, text="승강로 위치 · 층 번호 클릭으로 이동", anchor="w",
                 font=("맑은 고딕", 11, "bold")).pack(fill="x", pady=(0, 5))
        chart = tk.Frame(right)
        chart.pack(fill="both", expand=True)

        # 왼쪽은 층별 위치를 자세히 보는 일반 시뮬레이션이다.
        self.canvas = tk.Canvas(chart, highlightthickness=1, cursor="arrow")
        self.scrollbar = ttk.Scrollbar(chart, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # 오른쪽 축소도는 전체 운행을 항상 한눈에 볼 수 있게 동시에 표시한다.
        mini_frame = tk.LabelFrame(chart, text="전체 운행 축소도", padx=4, pady=4)
        mini_frame.pack(side="right", fill="y", padx=(8, 0))
        self.mini_canvas = tk.Canvas(mini_frame, width=190, highlightthickness=0)
        self.mini_canvas.pack(fill="both", expand=True)
        self.mini_canvas.bind("<Configure>", self.redraw)

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

        # 라벨·입력칸 위에서도 마우스 휠이 왼쪽 영역을 스크롤하도록 연결한다.
        def bind_left_wheel(widget):
            widget.bind("<MouseWheel>", scroll_left, add="+")
            for child in widget.winfo_children():
                bind_left_wheel(child)

        bind_left_wheel(left)

    @staticmethod
    def _row(parent, name, value, options=None, readonly_entry=False):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=name, width=9, anchor="w").pack(side="left")
        entry = ttk.Entry(row, textvariable=value, width=9)
        entry.pack(side="left", padx=5)
        return entry

    def keyboard_route_changed(self, _event=None):
        """Apply floor values typed directly with the keyboard."""
        try:
            count = int(self.floor_count.get())
            start = int(self.start_floor.get())
            destination = int(self.end_floor.get())
            if not 2 <= count <= 100:
                raise ValueError
            if not 1 <= start <= count or not 1 <= destination <= count:
                raise ValueError
        except ValueError:
            self.status_label.configure(text="층수는 정수로 입력하세요. 전체 층수는 2~100, 출발층·도착층은 그 범위 안이어야 합니다.")
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


    def stop(self):
        """재생 중인 시뮬레이션을 멈추고 예약된 화면 갱신을 취소한다."""
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
        """새 목적층을 선택하면 현재 위치를 기준으로 다음 운행을 준비한다."""
        destination = int(self.end_floor.get())
        if self.profile is not None and 0 < self.slider.get() < self.profile["duration_s"]:
            # 운행 중 목적층을 바꾸면 정확한 정지 제어 모델이 필요하므로,
            # 현재 카와 가장 가까운 층에 정차한 것으로 단순화해 새 운행을 시작한다.
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
        """기계동력 탭의 입력값으로 선택한 층 사이의 S-Curve 운행을 계산한다."""
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
            if hasattr(self, "mini_canvas"):
                self.mini_canvas.delete("all")
            self.status_label.configure(text="기계동력 탭에서 운행 조건을 입력하세요.")
            if show_errors:
                messagebox.showerror("승강로 위치", f"기계동력 입력을 확인하세요: {error}", parent=self.window)
            return False
        self.stop()
        self.arrived = False
        self.profile = {**result, "trip": trip}
        self.source_label.configure(
            text=("시뮬레이션 입력 출처: 기계동력 곡선 탭\n"
                  f"운행거리 {values[0]:g} m · 최고속도 {values[1]:g} m/s · "
                  f"가속도 {values[2]:g} m/s² · 저크 {values[3]:g} m/s³\n"
                  f"등가 이동질량 {values[4]:g} kg · 불평형·저항 합력 {values[5]:g} N")
        )
        self.structure_key = None
        self.slider.configure(to=result["duration_s"])
        self.slider.set(0)
        self.redraw()
        return True

    def play(self):
        """계산된 운행 데이터를 처음 또는 현재 시점부터 재생한다."""
        if not self.profile and not self.calculate():
            return
        if float(self.slider.get()) >= self.profile["duration_s"]:
            # 도착한 층은 다음 운행의 출발층이므로 새 목적층을 먼저 선택해야 한다.
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
        """80ms마다 운행 시간을 조금씩 진행시키고 화면을 다시 그린다."""
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
        """층 눈금과 승강로처럼 움직이지 않는 배경 구조를 그린다."""
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

    def draw_miniature(self, trip, traveled_m, palette):
        """전체 승강행정을 한 화면에 축소해 카와 균형추 위치를 함께 보여준다."""
        if not hasattr(self, "mini_canvas"):
            return
        canvas = self.mini_canvas
        canvas.delete("all")
        width = max(170, canvas.winfo_width())
        height = max(360, canvas.winfo_height())
        top, bottom = 62, height - 35
        center = width / 2
        car_x, cw_x = center - 30, center + 30

        # 전체 행정을 고정된 세로 길이에 맞춰 표시한다.
        car_height, counter_height = trip.position(traveled_m)
        usable = max(1, bottom - top)
        car_y = bottom - (car_height / trip.height_m) * usable
        cw_y = bottom - (counter_height / trip.height_m) * usable

        canvas.create_text(8, 8, anchor="nw",
                           text=f"출발 {trip.start_floor}층\n도착 {trip.end_floor}층",
                           fill=palette["text"], font=("맑은 고딕", 9, "bold"))

        traction_y = 48
        deflector_y = 55
        canvas.create_line(car_x, traction_y, car_x, car_y - 18,
                           fill=palette["muted"], width=2)
        canvas.create_line(car_x, traction_y, cw_x, deflector_y,
                           fill=palette["muted"], width=2)
        canvas.create_line(cw_x, deflector_y, cw_x, cw_y - 20,
                           fill=palette["muted"], width=2)
        canvas.create_oval(car_x - 12, traction_y - 12, car_x + 12, traction_y + 12,
                           fill=palette["surface"], outline=palette["text"], width=2)
        canvas.create_oval(cw_x - 7, deflector_y - 7, cw_x + 7, deflector_y + 7,
                           fill=palette["surface"], outline=palette["muted"], width=2)

        canvas.create_line(car_x - 24, top, car_x - 24, bottom,
                           fill=palette["border"], width=2)
        canvas.create_line(cw_x + 24, top, cw_x + 24, bottom,
                           fill=palette["border"], width=2)
        canvas.create_rectangle(car_x - 15, car_y - 28, car_x + 15, car_y,
                                fill="#2879cc", outline="#164e87", width=2)
        canvas.create_text(car_x, car_y - 14, text="카", fill="white",
                           font=("맑은 고딕", 9, "bold"))
        canvas.create_rectangle(cw_x - 11, cw_y - 32, cw_x + 11, cw_y,
                                fill="#d46a17", outline="#9a470d", width=2)
        canvas.create_text(cw_x, cw_y - 16, text="추", fill="white",
                           font=("맑은 고딕", 8, "bold"))

    def redraw(self, _event=None):
        """현재 시간에 맞춰 카·균형추·로프와 운행 상태를 화면에 갱신한다."""
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
        geom = HoistwayGeometry(trip.floors, pitch_px=68, top_px=155, bottom_px=90)
        palette = get_theme(self.canvas)[1]
        width = max(500, self.canvas.winfo_width())
        self.draw_structure(trip, geom, width, palette)
        self.canvas.delete("moving")
        cx = width / 2
        car_x, cw_x = cx - 45, cx + 45
        car_y = geom.car_bottom_y(trip, samples[index][1])
        weight_y = geom.counterweight_bottom_y(trip, samples[index][1])
        # 1:1 로핑을 알아보기 쉽게 권상기 쉬브와 편향도르래를 떨어뜨려 표시한다.
        # 실제 설치 치수를 뜻하는 도면이 아니라 카와 균형추의 이동 관계를 보여주는 도식이다.
        machine_x = car_x + 8
        traction_y = geom.top_px - 88
        deflector_x = cw_x
        deflector_y = geom.top_px - 54
        car_rope_top = car_y - 58
        cw_rope_top = weight_y - 64
        self.canvas.create_line(car_x, car_rope_top, car_x, traction_y,
                                fill=palette["muted"], width=2, tags="moving")
        self.canvas.create_line(car_x, traction_y, machine_x, traction_y,
                                fill=palette["muted"], width=2, tags="moving")
        self.canvas.create_line(machine_x, traction_y, deflector_x, deflector_y,
                                fill=palette["muted"], width=2, tags="moving")
        self.canvas.create_line(deflector_x, deflector_y, cw_x, cw_rope_top,
                                fill=palette["muted"], width=2, tags="moving")
        self.canvas.create_oval(machine_x - 30, traction_y - 30, machine_x + 30, traction_y + 30,
                                fill=palette["surface"], outline=palette["text"], width=3,
                                tags="moving")
        self.canvas.create_oval(deflector_x - 12, deflector_y - 12,
                                deflector_x + 12, deflector_y + 12,
                                fill=palette["surface"], outline=palette["muted"], width=2,
                                tags="moving")
        # 카의 중심이 아니라 카 바닥이 각 층 바닥선과 맞도록 그린다.
        self.canvas.create_rectangle(car_x - 26, car_y - 58, car_x + 26, car_y,
                                     fill="#2879cc", outline="#164e87", width=2, tags="moving")
        self.canvas.create_text(car_x, car_y - 28, text="카", fill="white",
                                font=("맑은 고딕", 12, "bold"), tags="moving")
        self.canvas.create_rectangle(cw_x - 18, weight_y - 64, cw_x + 18, weight_y,
                                     fill="#d46a17", outline="#9a470d", width=2, tags="moving")
        self.canvas.create_text(cw_x, weight_y - 32, text="균형추", fill="white",
                                font=("맑은 고딕", 10, "bold"), tags="moving")
        phase = trip_phase(samples, index)
        self.phase_label.configure(text=phase)
        for name, label in self.phase_labels.items():
            label.configure(bg=palette["accent"] if name == phase else palette["surface"],
                            fg="white" if name == phase else palette["text"])

        # 예전 화면처럼 현재 단계의 뜻을 바로 아래에서 짧게 설명한다.
        descriptions = {
            "Jerk": "Jerk: 가속도가 서서히 증가하는 출발 구간",
            "일정가속": "일정가속: 설정한 가속도를 유지하는 구간",
            "가속라운드": "가속라운드: 가속을 줄이며 전속 운전으로 넘어가는 구간",
            "전속": "전속: 최고속도를 일정하게 유지하는 구간",
            "감속라운드": "감속라운드: 감속을 시작하며 속도를 부드럽게 낮추는 구간",
            "일정감속": "일정감속: 설정한 감속도를 유지하는 구간",
            "착상부": "착상부: 감속을 완화하는 모델의 마지막 구간\n(정밀 착상 제어 아님)",
            "도착": "도착: 선택한 목적층에 운행이 끝난 상태",
        }
        if hasattr(self, "phase_description"):
            self.phase_description.configure(text=descriptions.get(phase, ""))

        # 일반 시뮬레이션과 같은 시점의 전체 축소도를 오른쪽에 함께 표시한다.
        self.draw_miniature(trip, samples[index][1], palette)

        car_height, _ = trip.position(samples[index][1])
        current = 1 + car_height / trip.floor_height_m
        velocity = samples[index][2]
        acceleration = samples[index][3]
        self.status_label.configure(
            text=(f"{trip.start_floor}층 → {trip.end_floor}층 · {'상승' if trip.direction > 0 else '하강'}\n"
                  f"현재 약 {current:.1f}층 · {samples[index][0]:.2f}/{self.profile['duration_s']:.2f}초\n"
                  f"속도 {velocity:.3f} m/s · 가속도 {acceleration:.3f} m/s²\n"
                  f"카와 균형추는 1:1 로핑으로 반대 방향 이동")
        )
        if index == len(samples) - 1 and not self.arrived:
            self.arrived = True
            self.start_floor.set(str(trip.end_floor))
        visible = max(1, self.canvas.winfo_height())
        total = geom.height_px
        if total > visible:
            offset = max(0, min(total - visible, car_y - visible / 2))
            self.canvas.yview_moveto(offset / total)
