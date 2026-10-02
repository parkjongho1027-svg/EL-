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
from src.core.motor_database import validate_motor_record, motor_matches
from src.core.measured_speed import compare_speed_log, load_speed_log
from src.core.synthetic_log import SyntheticOptions, save_synthetic_log
from src.core.trajectory import scurve_profile
from src.ui.document_reader import read_document
from src.core.errors import CalculationInputError
from src.core.vibration_analysis import load_csv_signal, load_wav_signal
from src.services.vibration_records import (
    archived_path, prepare_vibration_record, remove_unreferenced_files, result_only_record,
)
from src.ui.theme_manager import apply_theme
from src.ui.hoistway_view import HoistwayView
from src.ui.record_manager import open_record_manager
from src.ui.ui_components import SkyButton, app_ask_string, messagebox


def open_engineering_tools(panel):
    root = panel.winfo_toplevel()
    window = tk.Toplevel(panel)
    window.title("공학 데이터 도구 — 검증용")
    window.geometry("1200x800")
    window.minsize(980, 680)
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
            motor_db = panel.store.engineering_records("motor_component")
            if motor_db:
                data["motor_options_kw"] = tuple(sorted({
                    float(item.get("payload", {}).get("rated_power_kw")) for item in motor_db
                }))
                inputs["motor_options_kw"].delete(0, "end")
                inputs["motor_options_kw"].insert(0, ",".join(f"{v:g}" for v in data["motor_options_kw"]))
            else:
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
            ]
            db_matches = motor_matches(panel.store.engineering_records("motor_component"), row['selected_motor_kw'], row['peak_torque_nm'])
            if db_matches:
                passed = [m for m in db_matches if m.get('torque_status') == 'pass']
                unknown = [m for m in db_matches if m.get('torque_status') == 'unknown']
                failed = [m for m in db_matches if m.get('torque_status') == 'fail']
                shown = passed or unknown or failed
                label = ", ".join(f"{m['maker']} {m['model']}" for m in shown[:3])
                if passed:
                    suffix = " (정격토크 확인 완료)"
                elif unknown:
                    suffix = " (제조사 자료에 정격토크 미확인 · 토크 검증 제외)"
                else:
                    suffix = " (정격토크 부족 · 후보 재검토 필요)"
                lines.append(f"  실제 DB 모델: {label}{suffix}")
            lines.append("")
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

    SkyButton(design_actions, text="전체 후보 내보내기", command=export_design, width=19).pack(side="left")
    component_actions = tk.Frame(design)
    component_actions.pack(fill="x", padx=14, pady=3)
    db_status = tk.Label(component_actions, text="")

    def refresh_db_status():
        count = len(panel.store.engineering_records("motor_component"))
        db_status.configure(text=f"등록 전동기 {count}개 · DB가 있으면 후보 계산에 DB 정격을 자동 사용합니다.")

    def open_motor_db():
        manager = tk.Toplevel(window)
        manager.title("전동기 부품 DB 관리")
        manager.geometry("1040x620")
        manager.minsize(900, 520)
        manager.transient(window)
        outer = tk.Frame(manager)
        outer.pack(fill="both", expand=True, padx=14, pady=14)
        tk.Label(outer, text="전동기 부품 DB", font=("맑은 고딕", 14, "bold")).pack(anchor="w")
        tk.Label(outer, text="공개 제조사 자료에서 직접 확인한 모델만 등록하세요. 등록된 정격출력은 설계 후보 계산에 자동 반영됩니다.", anchor="w").pack(fill="x", pady=(2,8))
        cols=("maker","model","power","torque","speed","inertia","verified")
        tree=ttk.Treeview(outer, columns=cols, show="headings", selectmode="extended")
        heads=(("maker","제조사",130),("model","모델",180),("power","정격 kW",80),("torque","정격토크 N·m",110),("speed","rpm",80),("inertia","관성 kg·m²",100),("verified","확인일",100))
        for key,title,width in heads:
            tree.heading(key,text=title); tree.column(key,width=width,anchor="w")
        scroll=ttk.Scrollbar(outer,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left",fill="both",expand=True); scroll.pack(side="left",fill="y")
        side=tk.Frame(outer); side.pack(side="right",fill="y",padx=(12,0))

        def records(): return panel.store.engineering_records("motor_component")
        def refresh():
            tree.delete(*tree.get_children())
            for i,r in enumerate(records()):
                m=r.get("payload",{})
                tree.insert("","end",iid=str(i),values=(m.get("maker",""),m.get("model",""),f"{m.get('rated_power_kw',0):g}",('미확인' if m.get('rated_torque_nm') is None else f"{m['rated_torque_nm']:g}"),('미확인' if m.get('rated_speed_rpm') is None else f"{m['rated_speed_rpm']:g}"),('미확인' if m.get('inertia_kg_m2') is None else f"{m['inertia_kg_m2']:g}"),m.get("verified_date","")))
            refresh_db_status()

        def add_record(prefill=None):
            dialog=tk.Toplevel(manager); dialog.title("전동기 등록"); dialog.geometry("720x500"); dialog.transient(manager); dialog.grab_set()
            fields=(("maker","제조사"),("model","모델"),("rated_power_kw","정격출력 (kW)"),("rated_torque_nm","정격토크 (N·m, 선택)"),("rated_speed_rpm","정격속도 (rpm, 선택)"),("inertia_kg_m2","회전자 관성 (kg·m², 선택)"),("source","출처 (문서/URL/페이지)"),("verified_date","자료 확인일 (YYYY-MM-DD)"))
            entries={}
            for row,(key,label) in enumerate(fields):
                tk.Label(dialog,text=label,width=24,anchor="w").grid(row=row,column=0,padx=14,pady=7,sticky="w")
                e=tk.Entry(dialog,width=58); e.grid(row=row,column=1,padx=8,pady=7,sticky="ew"); entries[key]=e
                if prefill and key in prefill: e.insert(0,str(prefill[key]))
            dialog.columnconfigure(1,weight=1)
            def save():
                raw={k:e.get().strip() for k,e in entries.items()}
                for optional_key in ("rated_torque_nm","rated_speed_rpm","inertia_kg_m2"):
                    if not raw[optional_key]: raw[optional_key] = None
                try: motor=validate_motor_record(raw)
                except CalculationInputError as error: messagebox.showerror("전동기 DB",str(error),parent=dialog); return
                try: panel.store.add_engineering_record("motor_component", f"{motor['maker']} {motor['model']}", "", motor)
                except (ValueError,OSError) as error: messagebox.showerror("전동기 DB",str(error),parent=dialog); return
                dialog.destroy(); refresh()
            SkyButton(dialog,text="등록",command=save,width=12).grid(row=len(fields),column=1,pady=14,sticky="e",padx=8)

        def delete_selected():
            ids=tuple(sorted((int(x) for x in tree.selection()), reverse=True))
            if not ids: messagebox.showinfo("전동기 DB","삭제할 모델을 선택하세요.",parent=manager); return
            if messagebox.askyesno("전동기 DB",f"선택한 {len(ids)}개 모델을 삭제할까요?",parent=manager):
                panel.store.delete_engineering_records("motor_component",ids); refresh()

        def import_json():
            filename=filedialog.askopenfilename(parent=manager,filetypes=(("JSON","*.json"),))
            if not filename: return
            try:
                data=json.loads(Path(filename).read_text(encoding="utf-8-sig")); items=data.get("motors") if isinstance(data,dict) else data
                if not isinstance(items,list): raise CalculationInputError("JSON은 motors 배열 또는 전동기 배열이어야 합니다.")
                validated=[]
                for index, item in enumerate(items, 1):
                    try:
                        validated.append(validate_motor_record(item))
                    except CalculationInputError as error:
                        model = item.get("model", "모델 미상") if isinstance(item, dict) else "객체 아님"
                        raise CalculationInputError(f"{index}번 항목 [{model}] 오류: {error}") from error
                if len(records())+len(validated)>100: raise CalculationInputError("공학 데이터 기록 한도 100개를 초과합니다.")
                for m in validated: panel.store.add_engineering_record("motor_component",f"{m['maker']} {m['model']}","",m)
            except (OSError,json.JSONDecodeError,CalculationInputError,ValueError) as error:
                messagebox.showerror("전동기 DB",str(error),parent=manager); return
            refresh(); messagebox.showinfo("전동기 DB",f"{len(validated)}개 모델을 가져왔습니다.",parent=manager)

        def export_json():
            filename=filedialog.asksaveasfilename(parent=manager,defaultextension=".json",initialfile="motor_database.json",filetypes=(("JSON","*.json"),))
            if not filename:return
            payload={"schema":"motor-database-v2","motors":[r.get("payload",{}) for r in records()]}
            try: Path(filename).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
            except OSError as error: messagebox.showerror("전동기 DB",str(error),parent=manager); return
            messagebox.showinfo("전동기 DB","DB를 JSON으로 저장했습니다.",parent=manager)

        def save_template():
            filename=filedialog.asksaveasfilename(parent=manager,defaultextension=".json",initialfile="motor_database_template.json",filetypes=(("JSON","*.json"),))
            if not filename:return
            template={"schema":"motor-database-v2","description":"maker/model/rated_power_kw/source/verified_date는 필수. torque/speed/inertia는 제조사 자료에 없으면 null 허용.","motors":[{"maker":"","model":"","rated_power_kw":None,"rated_torque_nm":None,"rated_speed_rpm":None,"inertia_kg_m2":None,"source":"문서명/URL/페이지","verified_date":"YYYY-MM-DD"}]}
            Path(filename).write_text(json.dumps(template,ensure_ascii=False,indent=2),encoding="utf-8")

        SkyButton(side,text="전동기 등록",command=add_record,width=15).pack(fill="x",pady=3)
        SkyButton(side,text="DB 불러오기",command=import_json,width=15).pack(fill="x",pady=3)
        SkyButton(side,text="JSON 내보내기",command=export_json,width=15).pack(fill="x",pady=3)
        SkyButton(side,text="템플릿 저장",command=save_template,width=15).pack(fill="x",pady=3)
        SkyButton(side,text="선택 삭제",command=delete_selected,width=15).pack(fill="x",pady=(18,3))
        refresh(); apply_theme(manager,getattr(window,"_ui_theme","light"))

    SkyButton(component_actions, text="부품 DB 관리", command=open_motor_db, width=16).pack(side="left")
    db_status.pack(side="left", padx=10)
    refresh_db_status()
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
    vibration_snapshot = {}

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
            rate_text = sampling.get()
            rate = float(rate_text) if rate_text.strip() else None
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
            return data, comparison, filename, baseline, rate_text

        work("진동 분석", vib_button, worker, show_vibration)

    def show_vibration(results):
        data, comparison, filename, baseline, rate_text = results
        vibration_snapshot.clear()
        vibration_snapshot.update(primary=filename, baseline=baseline, rate_text=rate_text,
                                  data=data, comparison=comparison)
        display_vibration(data, comparison)

    def display_vibration(data, comparison, notice=""):
        text = (
            (notice + "\n\n" if notice else "")
            + f"형식: {data['source_kind']} / 샘플 {data['sample_count']}개 / {data['sampling_hz']:.2f} Hz\n"
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
        mid = 78
        amplitude = max(data["peak"], comparison["peak"] if comparison else 0, 1e-10)
        duration = max((report["sample_count"] - 1) / report["sampling_hz"]
                       for report in (data, comparison) if report)
        for y in (20, mid, 136):
            vibration_chart.create_line(35, y, width - 12, y, fill="#dce2e9")
        for report, color in ((data, "#2879cc"), (comparison, "#d46a17")):
            if not report:
                continue
            samples = report["waveform"]
            points = [
                coordinate
                for index, value in enumerate(samples)
                for coordinate in (
                    35 + (width - 50) * index / max(1, len(samples) - 1)
                    * (report["sample_count"] - 1) / report["sampling_hz"] / duration,
                    mid - 53 * value / amplitude,
                )
            ]
            if len(points) >= 4:
                vibration_chart.create_line(*points, fill=color, width=2)
        vibration_chart.create_text(
            40, 12, text=(f"0~{duration:.2f}초 · 파랑: 분석 / 주황: 비교" if comparison
                          else f"입력 신호 · 0~{duration:.2f}초 (처음 8192샘플)"), anchor="w"
        )
        show(vibration_result, text)

    vib_button = SkyButton(
        vib_controls, text="신호 분석", command=run_vibration, width=12
    )
    vib_button.pack(side="left")

    def save_vibration():
        if not vibration_snapshot:
            messagebox.showinfo("진동 기록 저장", "신호 분석을 먼저 실행하세요.", parent=window)
            return
        if len(panel.store.vibration_records()) >= 100:
            messagebox.showinfo("진동 기록 저장", "진동 기록은 최대 100개입니다. 관리에서 오래된 기록을 삭제하세요.", parent=window)
            return
        if (vibration_snapshot["primary"], vibration_snapshot["baseline"],
                vibration_snapshot["rate_text"]) != (
                vib_path.get().strip(), baseline_path.get().strip(), sampling.get()
        ):
            messagebox.showinfo("진동 기록 저장", "파일이나 샘플링 입력이 바뀌었습니다. 다시 분석하세요.", parent=window)
            return
        name = app_ask_string("진동 기록 저장", "기록 이름", parent=window,
                              initialvalue=Path(vibration_snapshot["primary"]).stem)
        if name is None:
            return
        if not name.strip():
            messagebox.showerror("진동 기록 저장", "기록 이름을 입력하세요.", parent=window)
            return
        owner = app_ask_string("진동 기록 저장", "담당자 이름 (선택)", parent=window)
        if owner is None:
            return
        filename, baseline = vibration_snapshot["primary"], vibration_snapshot["baseline"]
        rate_text = vibration_snapshot["rate_text"]
        rate = float(rate_text) if rate_text.strip() else None
        snapshot_data = vibration_snapshot["data"]
        snapshot_comparison = vibration_snapshot["comparison"]

        def worker():
            try:
                return prepare_vibration_record(panel.store, filename, baseline, rate)
            except (CalculationInputError, OSError) as error:
                return result_only_record(filename, baseline, rate, snapshot_data,
                                          snapshot_comparison, error)

        def finished(prepared):
            try:
                panel.store.add_vibration_record(name, owner, prepared)
            except (ValueError, OSError) as error:
                try:
                    remove_unreferenced_files(panel.store)
                except OSError:
                    pass
                messagebox.showerror("진동 기록 저장", str(error), parent=window)
                return
            show_vibration((prepared["data"], prepared["comparison"], filename, baseline, rate_text))
            if prepared.get("archive_warning"):
                try:
                    remove_unreferenced_files(panel.store)
                except OSError:
                    pass
                messagebox.showwarning(
                    "진동 기록 저장",
                    "첨부 복사에 실패해 비교 결과만 저장했습니다. 파일은 이 기록에서 복원할 수 없습니다.\n"
                    + prepared["archive_warning"], parent=window,
                )
            else:
                messagebox.showinfo("진동 기록 저장", "분석 결과와 첨부 파일 복사본을 저장했습니다.", parent=window)

        work("진동 기록 저장", vib_save_button, worker, finished)

    def manage_vibration():
        store = panel.store

        def records():
            return [(index, (item.get("name", ""), item.get("owner", ""),
                             item.get("primary", {}).get("name", ""),
                             (item.get("baseline") or {}).get("name", ""),
                             item.get("saved_at", "")))
                    for index, item in reversed(list(enumerate(store.vibration_records())))]

        def load(indices):
            record = store.vibration_records()[indices[0]]
            primary = archived_path(store, record.get("primary"))
            baseline = archived_path(store, record.get("baseline"))
            missing = [part.get("name", "파일") for part, path in
                       ((record.get("primary"), primary), (record.get("baseline"), baseline))
                       if isinstance(part, dict) and (path is None or not path.is_file())]
            source_path = str(primary) if primary and primary.is_file() else ""
            comparison_path = str(baseline) if baseline and baseline.is_file() else ""
            for entry, value in ((vib_path, source_path), (baseline_path, comparison_path),
                                 (sampling, str(record.get("sampling_hz") or ""))):
                entry.delete(0, "end")
                entry.insert(0, value)
            vibration_snapshot.clear()
            if not missing and source_path:
                vibration_snapshot.update(primary=source_path, baseline=comparison_path,
                                          rate_text=sampling.get())
            try:
                display_vibration(record["data"], record.get("comparison"),
                                  f"저장 기록: {record.get('name', '')} · {record.get('saved_at', '')}"
                                  + (f"\n첨부 파일 없음: {', '.join(missing)} · 저장된 분석 결과만 표시"
                                     if missing else "\n첨부 원본 복사본에서 다시 분석할 수 있습니다.")
                                  + (f"\n첨부 저장 실패 사유: {record['archive_warning']}"
                                     if record.get("archive_warning") else ""))
            except (KeyError, TypeError, ValueError) as error:
                messagebox.showerror("진동 데이터 관리", f"저장된 분석 결과가 손상되었습니다: {error}", parent=window)
                return
            notebook.select(vibration)

        def delete(indices):
            if "진동 기록 저장" in busy:
                messagebox.showinfo("진동 데이터 관리", "파일 저장이 끝난 뒤 삭제하세요.", parent=window)
                return
            try:
                store.delete_vibration_records(indices)
                remove_unreferenced_files(store)
            except OSError as error:
                messagebox.showerror("진동 데이터 관리", f"기록 또는 첨부 파일 삭제 실패: {error}", parent=window)

        def rename(index, name):
            store.update_vibration_record(index, name=name)

        def change_owner(indices, owner):
            for index in indices:
                store.update_vibration_record(index, owner=owner)

        open_record_manager(
            window, "진동 데이터 관리",
            (("name", "기록명", 205), ("owner", "담당자", 110),
             ("file", "분석 파일", 180), ("baseline", "비교 파일", 170),
             ("date", "저장 시각", 155)),
            records, load, delete, rename=rename, change_owner=change_owner,
            multi_load=False, save_current=save_vibration,
        )

    vib_save_button = SkyButton(vib_controls, text="진동 기록 저장", command=save_vibration, width=15)
    vib_save_button.pack(side="left", padx=(8, 0))
    SkyButton(vib_controls, text="진동 데이터 관리", command=manage_vibration, width=17).pack(side="left", padx=6)

    note(
        drawing,
        "PDF(앞 5쪽)의 텍스트 또는 PNG/JPG OCR에서 한글·영문 항목명과 수치·단위를 찾습니다.\n"
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

    drawing_controls = tk.Frame(drawing)
    drawing_controls.pack(fill="x", padx=12, pady=8)
    SkyButton(drawing_controls, text="선택한 값 입력", command=apply_selection, width=15).pack(side="right")

    def save_drawing_record():
        if not extracted:
            messagebox.showinfo("도면 기록 저장", "입력 후보 추출을 먼저 실행하세요.", parent=window); return
        name = app_ask_string("도면 기록 저장", "기록 이름", parent=window,
                              initialvalue=Path(doc_path.get().strip()).stem or "도면 추출")
        if name is None or not name.strip(): return
        owner = app_ask_string("도면 기록 저장", "담당자 이름 (선택)", parent=window)
        if owner is None: return
        payload = {"source_path": doc_path.get().strip(), "source_name": Path(doc_path.get().strip()).name,
                   "candidates": [asdict(item) for item in extracted]}
        try: panel.store.add_engineering_record("drawing", name, owner, payload)
        except (ValueError, OSError) as error:
            messagebox.showerror("도면 기록 저장", str(error), parent=window); return
        messagebox.showinfo("도면 기록 저장", "추출 후보 기록을 저장했습니다.", parent=window)

    def manage_drawing_records():
        store = panel.store
        def records():
            rows = store.engineering_records("drawing")
            return [(i, (r.get("name",""), r.get("owner",""), r.get("payload",{}).get("source_name",""), r.get("saved_at","")))
                    for i, r in reversed(list(enumerate(rows)))]
        def load(indices):
            r=store.engineering_records("drawing")[indices[0]]; payload=r.get("payload",{})
            path=payload.get("source_path",""); doc_path.delete(0,"end"); doc_path.insert(0,path)
            items=[]
            from src.core.document_fields import FieldCandidate
            for item in payload.get("candidates",[]):
                try: items.append(FieldCandidate(**item))
                except (TypeError, ValueError): pass
            show_document(items); notebook.select(drawing)
        def delete(indices): store.delete_engineering_records("drawing", indices)
        def rename(index,name): store.update_engineering_record("drawing",index,name=name)
        def change_owner(indices,owner):
            for index in indices: store.update_engineering_record("drawing",index,owner=owner)
        open_record_manager(window,"도면 입력 기록 관리",
            (("name","기록명",220),("owner","담당자",120),("file","원본 파일",260),("date","저장 시각",160)),
            records,load,delete,rename=rename,change_owner=change_owner,multi_load=False,save_current=save_drawing_record)

    SkyButton(drawing_controls, text="도면 기록 저장", command=save_drawing_record, width=15).pack(side="left")
    SkyButton(drawing_controls, text="도면 기록 관리", command=manage_drawing_records, width=15).pack(side="left", padx=6)

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
                 f"최대 절대 오차 {result['max_error_m_s']:.4f} m/s / 공통구간 {result.get('coverage_pct', 100):.1f}%. "
                 "파일 앞뒤의 비공통 정지구간은 제외하며 시각 자동 이동·센서 보정은 하지 않습니다."
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

    def save_measured_record():
        if not comparison:
            messagebox.showinfo("속도 기록 저장", "속도 비교를 먼저 실행하세요.", parent=window); return
        name=app_ask_string("속도 기록 저장","기록 이름",parent=window,
                            initialvalue=Path(measured_path.get().strip()).stem or "실측 속도 비교")
        if name is None or not name.strip(): return
        owner=app_ask_string("속도 기록 저장","담당자 이름 (선택)",parent=window)
        if owner is None: return
        payload={"source_path":measured_path.get().strip(),"source_name":Path(measured_path.get().strip()).name,
                 "comparison":comparison.copy()}
        try: panel.store.add_engineering_record("measured_speed",name,owner,payload)
        except (ValueError,OSError) as error:
            messagebox.showerror("속도 기록 저장",str(error),parent=window); return
        messagebox.showinfo("속도 기록 저장","실측 속도 비교 결과를 저장했습니다.",parent=window)

    def manage_measured_records():
        store=panel.store
        def records():
            rows=store.engineering_records("measured_speed")
            return [(i,(r.get("name",""),r.get("owner",""),r.get("payload",{}).get("source_name",""),r.get("saved_at","")))
                    for i,r in reversed(list(enumerate(rows)))]
        def load(indices):
            r=store.engineering_records("measured_speed")[indices[0]]; payload=r.get("payload",{})
            path=payload.get("source_path",""); measured_path.delete(0,"end"); measured_path.insert(0,path)
            result=payload.get("comparison",{}).copy()
            if "points" in result: result["points"]=[tuple(row) for row in result["points"]]
            show_measured(result); notebook.select(measured)
        def delete(indices): store.delete_engineering_records("measured_speed",indices)
        def rename(index,name): store.update_engineering_record("measured_speed",index,name=name)
        def change_owner(indices,owner):
            for index in indices: store.update_engineering_record("measured_speed",index,owner=owner)
        open_record_manager(window,"실측 속도 기록 관리",
            (("name","기록명",220),("owner","담당자",120),("file","실측 파일",260),("date","저장 시각",160)),
            records,load,delete,rename=rename,change_owner=change_owner,multi_load=False,save_current=save_measured_record)

    SkyButton(measured_controls,text="속도 기록 저장",command=save_measured_record,width=15).pack(side="left",padx=6)
    SkyButton(measured_controls,text="속도 기록 관리",command=manage_measured_records,width=15).pack(side="left")
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

    hoistway_view = HoistwayView(hoistway, panel, window)
    hoistway_view.pack(fill="both", expand=True)

    def preview_hoistway(_event=None):
        if notebook.select() != str(hoistway):
            return
        latest = tuple(panel.entries[key].get() for key in
                       ("distance", "vmax", "amax", "jerk", "mass", "force"))
        if hoistway_view.profile is None or latest != hoistway_view.source_snapshot:
            if hoistway_view.start_floor.get() == hoistway_view.end_floor.get():
                hoistway_view.source_label.configure(
                    text="기계동력 곡선 탭의 입력값이 바뀌었습니다. 다음 도착층을 선택하면 새 값으로 계산합니다."
                )
            else:
                hoistway_view.calculate(show_errors=False)

    notebook.bind("<<NotebookTabChanged>>", preview_hoistway, add="+")

    def stop_hoistway():
        hoistway_view.stop()
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", stop_hoistway)
    apply_theme(window, window._ui_theme)
    window.after(100, poll)
    return window
