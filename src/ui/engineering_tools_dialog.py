"""Three opt-in research tools. Tk stays on its main thread during file analysis."""

import csv
from dataclasses import asdict
import json
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, ttk

from src.core.design_explorer import DesignRequest, candidates_under_peak, explore_designs
from src.core.component_spec import load_component_spec
from src.core.measured_speed import compare_speed_log, load_speed_log
from src.core.synthetic_log import SyntheticOptions, save_synthetic_log
from src.core.trajectory import scurve_profile
from src.ui.document_reader import read_document
from src.core.errors import CalculationInputError
from src.core.vibration_analysis import load_csv_signal, load_wav_signal
from src.ui.theme_manager import apply_theme
from src.ui.ui_components import SkyButton, messagebox


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
    measured = tk.Frame(notebook)
    hoistway = tk.Frame(notebook)
    notebook.add(design, text="설계 후보 탐색")
    notebook.add(vibration, text="진동 데이터 분석")
    notebook.add(drawing, text="도면 입력 후보 추출")
    notebook.add(measured, text="실측 속도 비교")
    notebook.add(hoistway, text="승강로 위치 (모델)")
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

    design_snapshot = {}

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
        design_snapshot["request"] = request
        work("설계 후보", design_button, lambda: explore_designs(request), show_design)

    def show_design(report):
        design_snapshot["report"] = report
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

    design_actions = tk.Frame(design)
    design_actions.pack(fill="x", padx=14, pady=4)
    design_button = SkyButton(design_actions, text="후보 계산", command=run_design, width=14)
    design_button.pack(side="left")
    tk.Label(design_actions, text="목표 피크 kW 이하").pack(side="left", padx=(14, 4))
    target_entry = tk.Entry(design_actions, width=9)
    target_entry.pack(side="left")

    def search_target():
        try:
            result = candidates_under_peak(design_snapshot.get("report", {}), float(target_entry.get()))
        except (ValueError, CalculationInputError) as error:
            messagebox.showerror("목표 후보", str(error), parent=window)
            return
        lines = [f"목표 내 모델 후보 {len(result)}개 (81개 표본 중 전동기 목록으로 선정 가능한 조합)"]
        lines.extend(
            f"균형률 {row['balance_pct']:g}% / 로프 {row['ropes']}가닥 / 선정 {row['selected_motor_kw']:g} kW / 피크 {row['required_peak_kw']:.3f} kW"
            for row in result[:30]
        )
        if len(result) > 30:
            lines.append("화면에는 30개까지만 표시합니다. 전체 조합은 CSV로 저장하세요.")
        lines.append("최소 균형률은 이 표본 범위의 모델 값이며 로프 슬립/KC 판정이 아닙니다.")
        show(design_result, "\n".join(lines))

    SkyButton(design_actions, text="목표 검색", command=search_target, width=12).pack(side="left", padx=6)

    def export_design():
        report = design_snapshot.get("report")
        if not report:
            messagebox.showinfo("후보 저장", "후보 계산을 먼저 실행하세요.", parent=window)
            return
        filename = filedialog.asksaveasfilename(
            parent=window, defaultextension=".csv", filetypes=(("CSV", "*.csv"), ("JSON", "*.json"))
        )
        if not filename:
            return
        try:
            path = Path(filename)
            if path.suffix.lower() == ".json":
                payload = {"assumptions": asdict(design_snapshot["request"]), "model_cases": report["all_cases"],
                           "notice": "81개 표본의 계산 추정치. KC 적합, 로프 슬립, FEA 하중 조건 검증 아님."}
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                with path.open("w", encoding="utf-8-sig", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=tuple(report["all_cases"][0]))
                    writer.writeheader()
                    writer.writerows(report["all_cases"])
        except OSError as error:
            messagebox.showerror("후보 저장", str(error), parent=window)
            return
        messagebox.showinfo("후보 저장", f"81개 모델 계산값을 저장했습니다:\n{filename}", parent=window)

    SkyButton(design_actions, text="전체 후보 CSV/JSON", command=export_design, width=19).pack(side="left")
    component_actions = tk.Frame(design)
    component_actions.pack(fill="x", padx=14, pady=3)

    def save_component_template():
        filename = filedialog.asksaveasfilename(
            parent=window, defaultextension=".json", initialfile="component_template.json",
            filetypes=(("JSON", "*.json"),),
        )
        if not filename:
            return
        template = {"maker": "", "model": "", "source": "문서명/버전/페이지",
                    "rope_kg_m": None, "sheave_radius_m": None,
                    "motor_inertia_kg_m2": None, "motor_options_kw": []}
        try:
            Path(filename).write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("부품 명세", str(error), parent=window)
            return
        messagebox.showinfo("부품 명세", "원본 사양서의 출처와 수치를 템플릿에 직접 입력하세요.", parent=window)

    def import_component():
        filename = filedialog.askopenfilename(parent=window, filetypes=(("JSON", "*.json"),))
        if not filename:
            return
        try:
            spec = load_component_spec(filename)
        except CalculationInputError as error:
            messagebox.showerror("부품 명세", str(error), parent=window)
            return
        if not messagebox.askyesno(
            "부품 명세 확인",
            f"제조사: {spec.maker}\n모델: {spec.model}\n자료 출처: {spec.source}\n"
            f"로프 {spec.rope_kg_m:g} kg/m · 쉬브 반지름 {spec.sheave_radius_m:g} m\n"
            "원본과 대조한 후 설계 후보 입력에 적용할까요?",
            parent=window,
        ):
            return
        for key in ("rope_kg_m", "sheave_radius_m", "motor_inertia_kg_m2", "motor_options_kw"):
            value = getattr(spec, key)
            entry = inputs[key]
            entry.delete(0, "end")
            entry.insert(0, ",".join(f"{rating:g}" for rating in value) if isinstance(value, tuple) else f"{value:g}")
        design_snapshot.clear()
        show(design_result, f"{spec.maker} / {spec.model}: 입력만 반영했습니다. '후보 계산'으로 재계산하세요.\n출처: {spec.source}")

    SkyButton(component_actions, text="부품 명세 템플릿", command=save_component_template, width=19).pack(side="left")
    SkyButton(component_actions, text="부품 JSON 불러오기", command=import_component, width=20).pack(side="left", padx=6)
    tk.Label(component_actions, text="제조사 수치와 출처는 사용자가 검증합니다.").pack(side="left", padx=8)
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

    note(
        measured,
        "동일한 운행의 엔코더/센서 속도 CSV·TXT (time_s,speed_m_s)를 현재 기계동력 곡선의 속도와 겹쳐 비교합니다. "
        "파일은 최대 5 MB / 5만 행, 그래프는 최대 1,000점만 그립니다. 측정 시간 기준과 단위를 먼저 확인하세요.",
    )
    measured_form = tk.Frame(measured)
    measured_form.pack(fill="x", padx=12, pady=5)
    measured_path = tk.Entry(measured_form)
    measured_path.pack(side="left", fill="x", expand=True)
    SkyButton(
        measured_form,
        text="속도 기록 선택",
        command=lambda: choose(measured_path, (("CSV/TXT", "*.csv *.txt"),)),
        width=16,
    ).pack(side="left", padx=5)
    measured_controls = tk.Frame(measured)
    measured_controls.pack(fill="x", padx=12, pady=6)
    comparison = {}
    measured_chart = tk.Canvas(measured, height=370, bg="white", highlightthickness=1)
    measured_chart.pack(fill="both", expand=True, padx=12, pady=8)
    measured_result = tk.Label(measured, anchor="w", justify="left", wraplength=850)
    measured_result.pack(fill="x", padx=12, pady=6)

    def redraw_measured(_event=None):
        if not comparison:
            return
        measured_chart.delete("all")
        w, h = max(500, measured_chart.winfo_width()), max(230, measured_chart.winfo_height())
        x0, x1, y0, y1 = 65, w - 20, 32, h - 48
        rows = comparison["points"]
        duration = comparison["duration_s"]
        maximum = max(max(point[1], point[2]) for point in rows)
        maximum = max(maximum * 1.1, 0.1)
        for tick in range(6):
            value = maximum * tick / 5
            y = y1 - (y1 - y0) * tick / 5
            measured_chart.create_line(x0, y, x1, y, fill="#e2e7ee")
            measured_chart.create_text(x0 - 8, y, text=f"{value:.2f}", anchor="e")
            x = x0 + (x1 - x0) * tick / 5
            measured_chart.create_line(x, y0, x, y1, fill="#e2e7ee")
            measured_chart.create_text(x, y1 + 16, text=f"{duration * tick / 5:.1f}")
        measured_chart.create_text(x0, 14, text="파랑: 모델 / 주황: 실측 · 속도(m/s)", anchor="w")
        measured_chart.create_text(x1, h - 12, text="시간(s)", anchor="e")
        stride = max(1, (len(rows) + 999) // 1000)
        plotted = rows[::stride]
        if plotted[-1] != rows[-1]:
            plotted.append(rows[-1])
        for index, color in ((1, "#2879cc"), (2, "#d46a17")):
            coords = [coordinate for point in plotted for coordinate in
                      (x0 + (x1 - x0) * point[0] / duration,
                       y1 - (y1 - y0) * point[index] / maximum)]
            measured_chart.create_line(*coords, fill=color, width=2)

    measured_chart.bind("<Configure>", redraw_measured)

    def show_measured(result):
        comparison.clear()
        comparison.update(result)
        measured_result.configure(
            text=f"겹친 샘플 {result['sample_count']}개 / 속도 RMSE {result['rmse_m_s']:.4f} m/s / "
                 f"최대 절대 오차 {result['max_error_m_s']:.4f} m/s. 시각 자동 정렬·센서 보정은 하지 않습니다."
        )
        redraw_measured()

    def run_measured():
        filename = measured_path.get().strip()
        if not filename:
            messagebox.showinfo("속도 비교", "속도 CSV/TXT 파일을 선택하세요.", parent=window)
            return
        try:
            values = [float(panel.entries[key].get()) for key in
                      ("distance", "vmax", "amax", "jerk", "mass", "force")]
        except ValueError:
            messagebox.showerror("속도 비교", "기계동력 곡선의 수치 입력을 확인하세요.", parent=window)
            return

        def worker():
            profile = scurve_profile(*values)
            return compare_speed_log(profile, load_speed_log(filename))

        work("실측 속도 비교", measured_button, worker, show_measured)

    measured_button = SkyButton(measured_controls, text="속도 곡선 비교", command=run_measured, width=18)
    measured_button.pack(side="left")

    def export_measured():
        if not comparison:
            messagebox.showinfo("비교 저장", "속도 비교를 먼저 실행하세요.", parent=window)
            return
        filename = filedialog.asksaveasfilename(parent=window, defaultextension=".csv", filetypes=(("CSV", "*.csv"),))
        if not filename:
            return
        try:
            with Path(filename).open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(("time_s", "model_speed_m_s", "measured_speed_m_s"))
                writer.writerows(comparison["points"])
        except OSError as error:
            messagebox.showerror("비교 저장", str(error), parent=window)
            return
        messagebox.showinfo("비교 저장", f"비교한 값을 저장했습니다:\n{filename}", parent=window)

    SkyButton(measured_controls, text="비교 데이터 CSV", command=export_measured, width=18).pack(side="left", padx=6)
    synthetic_controls = tk.Frame(measured)
    synthetic_controls.pack(fill="x", padx=12, pady=(0, 8))
    tk.Label(synthetic_controls, text="합성 시드").pack(side="left")
    synthetic_seed = tk.Entry(synthetic_controls, width=8)
    synthetic_seed.insert(0, "42")
    synthetic_seed.pack(side="left", padx=5)
    tk.Label(synthetic_controls, text="속도 노이즈 σ (m/s)").pack(side="left")
    synthetic_noise = tk.Entry(synthetic_controls, width=7)
    synthetic_noise.insert(0, "0.015")
    synthetic_noise.pack(side="left", padx=5)
    tk.Label(synthetic_controls, text="지연 (s)").pack(side="left")
    synthetic_delay = tk.Entry(synthetic_controls, width=7)
    synthetic_delay.insert(0, "0.025")
    synthetic_delay.pack(side="left", padx=5)

    def make_synthetic():
        try:
            values = [float(panel.entries[key].get()) for key in
                      ("distance", "vmax", "amax", "jerk", "mass", "force")]
            options = SyntheticOptions(seed=int(synthetic_seed.get()),
                                       speed_noise_m_s=float(synthetic_noise.get()),
                                       delay_s=float(synthetic_delay.get()))
        except (ValueError, CalculationInputError) as error:
            messagebox.showerror("합성 기록", f"입력을 확인하세요: {error}", parent=window)
            return
        filename = filedialog.asksaveasfilename(
            parent=window, defaultextension=".csv", initialfile="SYNTHETIC_demo_speed.csv",
            filetypes=(("CSV", "*.csv"),),
        )
        if not filename:
            return

        def worker():
            profile = scurve_profile(*values)
            count = save_synthetic_log(filename, profile, options)
            return filename, count, compare_speed_log(profile, load_speed_log(filename))

        def finished(result):
            path, count, report = result
            measured_path.delete(0, "end")
            measured_path.insert(0, path)
            show_measured(report)
            messagebox.showinfo("합성 기록", f"합성 예제 {count}행을 저장하고 비교했습니다. 실측 데이터가 아닙니다.\n{path}", parent=window)

        work("합성 기록", synthetic_button, worker, finished)

    synthetic_button = SkyButton(synthetic_controls, text="합성 CSV 생성·비교", command=make_synthetic, width=22)
    synthetic_button.pack(side="left", padx=9)

    note(hoistway, "1:1 로핑을 가정한 카·균형추 위치 도식입니다. 실제 승강로 도면, 로프 슬립, 카 프레임 간섭, 완충기·오버슈트를 판정하지 않습니다.")
    hoist_controls = tk.Frame(hoistway)
    hoist_controls.pack(fill="x", padx=12, pady=4)
    hoist_canvas = tk.Canvas(hoistway, height=375, highlightthickness=1, bg="white")
    hoist_canvas.pack(fill="both", expand=True, padx=12, pady=10)
    hoist_status = tk.Label(hoistway, text="현재 기계동력 곡선 입력으로 위치를 계산하세요.")
    hoist_status.pack(fill="x", padx=12, pady=6)
    hoist_profile = {}
    motion = {"playing": False, "after_id": None}
    time_slider = tk.Scale(hoist_controls, orient="horizontal", resolution=0.05, length=460,
                           label="운행 시간 (s)")
    time_slider.pack(side="left", fill="x", expand=True, padx=8)

    def redraw_hoistway(_event=None):
        if not hoist_profile:
            return
        samples = hoist_profile["samples"]
        t = float(time_slider.get())
        index = min(len(samples) - 1, max(0, int(t / max(hoist_profile["duration_s"], 0.01) * (len(samples) - 1))))
        while index + 1 < len(samples) and samples[index + 1][0] <= t:
            index += 1
        while index > 0 and samples[index][0] > t:
            index -= 1
        car_pos, speed = samples[index][1], samples[index][2]
        distance = hoist_profile["distance_m"]
        cw_pos = distance - car_pos
        hoist_canvas.delete("all")
        width = max(500, hoist_canvas.winfo_width())
        height = max(290, hoist_canvas.winfo_height())
        top, bottom = 45, height - 42
        cx = width / 2
        for x in (cx - 125, cx + 125):
            hoist_canvas.create_rectangle(x - 53, top, x + 53, bottom, outline="#b6c6d9", width=2)
        hoist_canvas.create_oval(cx - 14, top - 25, cx + 14, top + 3, outline="#486689", width=2)
        for x, pos, color, label in ((cx - 125, car_pos, "#2879cc", "카"),
                                     (cx + 125, cw_pos, "#d46a17", "균형추")):
            y = bottom - (bottom - top - 32) * min(distance, max(0, pos)) / distance
            hoist_canvas.create_rectangle(x - 33, y - 30, x + 33, y, fill=color, outline="")
            hoist_canvas.create_text(x, y - 15, text=label, fill="white")
            hoist_canvas.create_text(x, bottom + 18, text=f"{pos:.2f} m")
        hoist_status.configure(text=f"운행 {samples[index][0]:.2f} / {hoist_profile['duration_s']:.2f} s · 카 속도 {speed:.3f} m/s · 1:1 위치 도식")

    time_slider.configure(command=lambda _value: redraw_hoistway())
    hoist_canvas.bind("<Configure>", redraw_hoistway)

    def calculate_hoistway():
        try:
            values = [float(panel.entries[key].get()) for key in
                      ("distance", "vmax", "amax", "jerk", "mass", "force")]
            profile = scurve_profile(*values)
        except (ValueError, CalculationInputError) as error:
            messagebox.showerror("승강로 위치", f"기계동력 입력을 확인하세요: {error}", parent=window)
            return
        hoist_profile.clear()
        hoist_profile.update(profile, distance_m=values[0])
        time_slider.configure(to=profile["duration_s"])
        time_slider.set(0)
        redraw_hoistway()

    def tick_hoistway():
        motion["after_id"] = None
        if not motion["playing"] or not window.winfo_exists():
            return
        next_time = float(time_slider.get()) + 0.08
        if next_time >= hoist_profile["duration_s"]:
            time_slider.set(hoist_profile["duration_s"])
            motion["playing"] = False
            return
        time_slider.set(next_time)
        motion["after_id"] = window.after(80, tick_hoistway)

    def toggle_hoistway():
        if not hoist_profile:
            calculate_hoistway()
        if not hoist_profile:
            return
        motion["playing"] = not motion["playing"]
        if motion["playing"]:
            if float(time_slider.get()) >= hoist_profile["duration_s"]:
                time_slider.set(0)
            tick_hoistway()
        elif motion["after_id"]:
            window.after_cancel(motion["after_id"])
            motion["after_id"] = None

    SkyButton(hoist_controls, text="위치 갱신", command=calculate_hoistway, width=13).pack(side="left", padx=4)
    SkyButton(hoist_controls, text="재생 / 정지", command=toggle_hoistway, width=13).pack(side="left", padx=4)

    def stop_hoistway():
        motion["playing"] = False
        if motion["after_id"]:
            window.after_cancel(motion["after_id"])
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", stop_hoistway)
    apply_theme(window, window._ui_theme)
    window.after(100, poll)
    return window
