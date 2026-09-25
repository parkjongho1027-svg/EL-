"""Three opt-in research tools. Tk stays on its main thread during file analysis."""

from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, ttk

from src.core.design_explorer import DesignRequest, explore_designs
from src.ui.document_reader import read_document
from src.core.errors import CalculationInputError
from src.core.vibration_analysis import load_csv_signal, load_wav_signal
from theme_manager import apply_theme
from ui_components import SkyButton, messagebox


def open_engineering_tools(panel):
    root = panel.winfo_toplevel()
    window = tk.Toplevel(panel)
    window.title("공학 데이터 도구 — 검증용")
    window.geometry("900x680")
    window.minsize(900, 600)
    window.transient(root)
    window._ui_theme = getattr(root, "_ui_theme", "light")
    notebook = ttk.Notebook(window)
    notebook.pack(fill="both", expand=True, padx=12, pady=12)
    design = tk.Frame(notebook)
    vibration = tk.Frame(notebook)
    drawing = tk.Frame(notebook)
    notebook.add(design, text="설계 후보 탐색")
    notebook.add(vibration, text="진동 데이터 분석")
    notebook.add(drawing, text="도면 입력 후보 추출")
    completed = Queue()
    busy = set()

    def work(label, button, worker, on_success):
        if label in busy:
            return
        busy.add(label)
        button.configure(state="disabled")

        def run():
            try:
                result = worker()
                completed.put((label, button, on_success, result, None))
            except Exception as error:
                completed.put((label, button, on_success, None, error))

        Thread(target=run, daemon=True).start()

    def poll():
        if not window.winfo_exists():
            return
        while True:
            try:
                label, button, on_success, result, error = completed.get_nowait()
            except Empty:
                break
            busy.discard(label)
            button.configure(state="normal")
            if error is not None:
                messagebox.showerror(label, str(error), parent=window)
            else:
                on_success(result)
        window.after(100, poll)

    def note(parent, message):
        tk.Label(parent, text=message, justify="left", anchor="w", wraplength=820).pack(
            fill="x", padx=12, pady=(8, 4)
        )

    def result_box(parent):
        holder = tk.Frame(parent)
        holder.pack(fill="both", expand=True, padx=12, pady=8)
        scroll = ttk.Scrollbar(holder)
        output = tk.Text(
            holder,
            wrap="word",
            yscrollcommand=scroll.set,
            font=("맑은 고딕", 10),
            padx=8,
            pady=8,
        )
        scroll.config(command=output.yview)
        scroll.pack(side="right", fill="y")
        output.pack(fill="both", expand=True)
        output.configure(state="disabled")
        return output

    def show(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    note(
        design,
        "등가 로프 질량·일정 저항의 단순 모델입니다. 81개 조합의 4개 운행 조건을 물리식으로 다시 계산합니다.\n"
        "학습 근사치는 오차를 공개하며 순위·안전 판정에 사용하지 않습니다. 로프 강도·KC 적합·전동기 토크 정격은 검증하지 않습니다.",
    )
    form = tk.Frame(design)
    form.pack(fill="x", padx=14, pady=3)
    specs = (
        ("distance_m", "승강행정 (m)", panel.entries["distance"].get() or "30"),
        ("speed_m_s", "정격속도 (m/s)", panel.entries["vmax"].get() or "2"),
        ("rated_load_kg", "정격하중 (kg)", "1000"),
        ("car_kg", "카 자중 (kg)", "1000"),
        ("rope_kg_m", "로프 가닥당 단위질량 (kg/m)", "0.8"),
        ("sheave_radius_m", "도르래 반지름 (m)", "0.4"),
        ("motor_inertia_kg_m2", "회전자 관성 (kg·m²)", "2"),
        ("cycle_s", "운전 반복주기 (s)", "120"),
        (
            "motor_options_kw",
            "사용 가능한 전동기 (kW, 쉼표 구분)",
            "7.5,11,15,18.5,22,30",
        ),
    )
    inputs = {}
    for index, (key, label, default) in enumerate(specs):
        col = index // 5
        row = index % 5
        cell = tk.Frame(form)
        cell.grid(row=row, column=col, sticky="w", padx=(0, 18), pady=2)
        tk.Label(cell, text=label, width=29, anchor="w").pack(side="left")
        entry = tk.Entry(cell, width=18)
        entry.insert(0, default)
        entry.pack(side="left")
        inputs[key] = entry

    def run_design():
        try:
            data = {
                key: float(entry.get())
                for key, entry in inputs.items()
                if key != "motor_options_kw"
            }
            data["motor_options_kw"] = tuple(
                float(item.strip())
                for item in inputs["motor_options_kw"].get().split(",")
            )
            request = DesignRequest(**data)
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "설계 후보", f"입력값을 확인하세요: {error}", parent=window
            )
            return
        work("설계 후보", design_button, lambda: explore_designs(request), show_design)

    def show_design(report):
        lines = [
            f"81개 조합 중 모델 계산 가능한 후보 {report['feasible_count']}개 / 용량 부족 {report['rejected_count']}개",
            f"근사 모델 미사용 검증 집합 8건 오차: 평균 {report['holdout_mean_error_pct']:.2f}%, 최대 {report['holdout_max_error_pct']:.2f}%",
            "선정 용량(모델 피크×1.15), 로프 가닥 수, 필요 피크 순으로 정렬. 제시된 모터 목록 안에서만 탐색합니다.",
            "",
        ]
        for rank, row in enumerate(report["top"], 1):
            lines += [
                f"{rank}순위: {row['selected_motor_kw']:g} kW / 로프 {row['ropes']}가닥 / 균형률 {row['balance_pct']:g}%",
                f"  4운행 최악 필요 피크 {row['required_peak_kw']:.3f} kW / 모터축 토크 {row['peak_torque_nm']:.1f} N·m",
                f"  로프 가닥당 최대 정적 장력 {row['max_static_tension_n_per_rope']:.1f} N (강도 비교 전)",
                "",
            ]
        if not report["top"]:
            lines.append(
                "설정한 전동기 목록으로는 어떤 조합도 15% 용량 여유를 만족하지 않습니다."
            )
        lines.append(
            "※ 제어/인버터 피크 정격, 가열, 파단하중 및 KC 조항을 제조사 도서로 별도 확인해야 합니다."
        )
        show(design_result, "\n".join(lines))

    design_button = SkyButton(design, text="후보 계산", command=run_design, width=14)
    design_button.pack(anchor="w", padx=14)
    design_result = result_box(design)

    note(
        vibration,
        "CSV: time_s,acceleration_m_s2 또는 vibration 열. time_s가 없으면 샘플링 주파수를 입력하세요.\n"
        "WAV는 보정되지 않은 오디오 진폭입니다. 고장 확률·잔여 수명·승강기 진단 판정을 제공하지 않습니다.",
    )
    vib_form = tk.Frame(vibration)
    vib_form.pack(fill="x", padx=12)
    vib_path = tk.Entry(vib_form, width=69)
    vib_path.pack(side="left", fill="x", expand=True)
    SkyButton(
        vib_form,
        text="CSV/WAV 선택",
        command=lambda: choose(vib_path, (("데이터", "*.csv *.wav"),)),
        width=13,
    ).pack(side="left", padx=4)
    vib_controls = tk.Frame(vibration)
    vib_controls.pack(fill="x", padx=12, pady=8)
    tk.Label(vib_controls, text="샘플링 Hz (time_s 없을 때)").pack(side="left")
    sampling = tk.Entry(vib_controls, width=12)
    sampling.pack(side="left", padx=7)
    baseline_row = tk.Frame(vibration)
    baseline_row.pack(fill="x", padx=12)
    tk.Label(baseline_row, text="같은 측정 조건의 비교 신호 (선택)").pack(side="left")
    baseline_path = tk.Entry(baseline_row, width=42)
    baseline_path.pack(side="left", fill="x", expand=True, padx=5)
    SkyButton(
        baseline_row,
        text="비교 파일",
        command=lambda: choose(baseline_path, (("데이터", "*.csv *.wav"),)),
        width=11,
    ).pack(side="left")
    vibration_chart = tk.Canvas(vibration, height=155, highlightthickness=0)
    vibration_chart.pack(fill="x", padx=12, pady=4)
    vibration_result = result_box(vibration)

    def choose(entry, types):
        filename = filedialog.askopenfilename(parent=window, filetypes=types)
        if filename:
            entry.delete(0, "end")
            entry.insert(0, filename)

    def run_vibration():
        filename = vib_path.get().strip()
        if not filename:
            messagebox.showinfo(
                "진동 분석", "먼저 데이터 파일을 선택하세요.", parent=window
            )
            return
        try:
            rate = float(sampling.get()) if sampling.get().strip() else None
        except ValueError:
            messagebox.showerror(
                "진동 분석", "샘플링 주파수는 숫자로 입력하세요.", parent=window
            )
            return
        baseline = baseline_path.get().strip()

        def analyse(path):
            return (
                load_wav_signal(path)
                if Path(path).suffix.lower() == ".wav"
                else load_csv_signal(path, rate)
            )

        def worker():
            data = analyse(filename)
            comparison = analyse(baseline) if baseline else None
            if comparison and data["source_kind"] != comparison["source_kind"]:
                raise CalculationInputError(
                    "비교하려면 두 파일의 신호 형식과 단위를 일치시키세요."
                )
            if (
                comparison
                and abs(data["sampling_hz"] / comparison["sampling_hz"] - 1) > 0.05
            ):
                raise CalculationInputError(
                    "비교 파일의 샘플링 주파수가 5% 이상 다릅니다."
                )
            return data, comparison

        work("진동 분석", vib_button, worker, show_vibration)

    def show_vibration(results):
        data, comparison = results
        text = (
            f"형식: {data['source_kind']} / 샘플 {data['sample_count']}개 / {data['sampling_hz']:.2f} Hz\n"
            f"평균 제거 RMS: {data['rms']:.5g} / 피크: {data['peak']:.5g} / 첨두율: {data['crest_factor'] or 0:.3f}\n"
            f"관찰 범위 최고 {data['scanned_max_hz']:.1f} Hz / 주파수 분해능 {data['frequency_resolution_hz']:.2f} Hz\n"
            f"범위 안의 최강 주파수: {data['dominant_hz']:.1f} Hz (진폭 {data['dominant_amplitude']:.5g})\n\n"
            "이 수치만으로 베어링 결함 종류·고장 확률·RUL을 산정하지 않습니다. "
        )
        if comparison:
            text += (
                f"\n비교 신호 RMS {comparison['rms']:.5g} / 현재÷비교 "
                f"{data['rms'] / comparison['rms']:.3f}배\n"
                if comparison["rms"]
                else "\n비교 신호의 RMS가 0이므로 비율을 계산하지 않습니다.\n"
            )
        vibration_chart.delete("all")
        width = max(500, vibration_chart.winfo_width())
        mid, amplitude = 78, max(data["peak"], 1e-10)
        for y in (20, mid, 136):
            vibration_chart.create_line(35, y, width - 12, y, fill="#dce2e9")
        samples = data["waveform"]
        points = [
            coordinate
            for index, value in enumerate(samples)
            for coordinate in (
                35 + (width - 50) * index / max(1, len(samples) - 1),
                mid - 53 * value / amplitude,
            )
        ]
        if len(points) >= 4:
            vibration_chart.create_line(*points, fill="#2879cc", width=2)
        vibration_chart.create_text(
            40, 12, text="입력 신호 (처음 8192샘플)", anchor="w"
        )
        show(vibration_result, text)

    vib_button = SkyButton(
        vib_controls, text="신호 분석", command=run_vibration, width=12
    )
    vib_button.pack(side="left")

    note(
        drawing,
        "PDF(앞 5쪽)의 텍스트 또는 PNG/JPG OCR에서 명시된 수치와 단위를 찾습니다.\n"
        "추출값은 원본 줄과 비교해 직접 선택해야 입력됩니다. KC 적합 판정은 수행하지 않습니다.",
    )
    doc_form = tk.Frame(drawing)
    doc_form.pack(fill="x", padx=12)
    doc_path = tk.Entry(doc_form, width=68)
    doc_path.pack(side="left", fill="x", expand=True)
    SkyButton(
        doc_form,
        text="문서 선택",
        command=lambda: choose(doc_path, (("도면/문서", "*.pdf *.png *.jpg *.jpeg"),)),
        width=13,
    ).pack(side="left", padx=4)
    doc_button = SkyButton(drawing, text="입력 후보 추출", width=15)
    doc_button.pack(anchor="w", padx=12, pady=7)
    table_holder = tk.Frame(drawing)
    table_holder.pack(fill="both", expand=True, padx=12)
    tree = ttk.Treeview(
        table_holder,
        columns=("key", "value", "line"),
        show="headings",
        selectmode="extended",
    )
    for key, label, width in (
        ("key", "항목", 145),
        ("value", "추출값", 125),
        ("line", "원본 텍스트 (직접 대조)", 580),
    ):
        tree.heading(key, text=label)
        tree.column(key, width=width, anchor="w")
    scroll = ttk.Scrollbar(table_holder, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    extracted = []

    def show_document(items):
        extracted[:] = items
        tree.delete(*tree.get_children())
        for index, candidate in enumerate(items):
            tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    candidate.label,
                    f"{candidate.value:g} {candidate.unit}",
                    candidate.source_line,
                ),
            )
        if not items:
            messagebox.showinfo(
                "문서 입력 후보",
                "명시적인 항목·단위 조합을 찾지 못했습니다. 원본 문서를 직접 입력하세요.",
                parent=window,
            )

    def run_document():
        filename = doc_path.get().strip()
        if not filename:
            messagebox.showinfo(
                "문서 입력 후보", "먼저 문서를 선택하세요.", parent=window
            )
            return
        work(
            "문서 입력 후보", doc_button, lambda: read_document(filename), show_document
        )

    doc_button.configure(command=run_document)

    def apply_selection():
        selected = [extracted[int(row)] for row in tree.selection()]
        if not selected:
            messagebox.showinfo(
                "문서 입력 후보", "원본과 대조해 적용할 행을 선택하세요.", parent=window
            )
            return
        if len({item.key for item in selected}) != len(selected):
            messagebox.showerror(
                "문서 입력 후보",
                "동일 항목의 서로 다른 값을 동시에 적용할 수 없습니다.",
                parent=window,
            )
            return
        app = getattr(root, "_elevator_app", None)
        if app is None:
            messagebox.showerror(
                "문서 입력 후보", "계산 화면을 찾지 못했습니다.", parent=window
            )
            return
        if not messagebox.askyesno(
            "문서 입력 후보",
            "선택한 수치를 계산 입력칸에 넣을까요? 원본과 단위를 먼저 확인했어야 합니다.",
            parent=window,
        ):
            return
        mappings = {
            "rated_load_kg": ((app.motor_panel, "Q", 1), (app.traction_panel, "Q", 1)),
            "speed_m_s": (
                (
                    app.motor_panel,
                    "V",
                    60 if app.motor_panel.unit_vars["V"].get() == "m/min" else 1,
                ),
                (app.criteria_panel, "rated", 1),
                (panel, "vmax", 1),
            ),
            "distance_m": ((app.traction_panel, "H", 1), (panel, "distance", 1)),
            "car_kg": ((app.traction_panel, "Wc", 1),),
            "rope_count": (
                (app.traction_panel, "n", 1),
                (app.criteria_panel, "count", 1),
            ),
            "motor_kw": ((app.criteria_panel, "selected_motor", 1),),
        }
        changed = 0
        for item in selected:
            for target_panel, key, factor in mappings.get(item.key, ()):
                entry = target_panel.entries.get(key)
                if entry is None or str(entry.cget("state")) == "disabled":
                    continue
                entry.delete(0, "end")
                entry.insert(0, f"{item.value * factor:g}")
                entry.event_generate("<KeyRelease>")
                changed += 1
        messagebox.showinfo(
            "문서 입력 후보",
            f"{changed}개 입력칸에 반영했습니다. 계산 결과와 원본을 다시 대조하세요.",
            parent=window,
        )

    SkyButton(drawing, text="선택한 값 입력", command=apply_selection, width=15).pack(
        anchor="e", padx=12, pady=8
    )
    apply_theme(window, window._ui_theme)
    window.after(100, poll)
    return window
