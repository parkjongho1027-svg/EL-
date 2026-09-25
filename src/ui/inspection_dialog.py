"""NCS-inspired observation worksheet, separate from KC clause calculations."""

import tkinter as tk
from tkinter import ttk

from src.core.inspection_record import LOCATIONS, STATES, normalize_inspection_record
from theme_manager import apply_font_scale, apply_theme
from ui_components import SkyButton


def open_inspection_dialog(panel):
    root = panel.winfo_toplevel()
    window = tk.Toplevel(panel)
    window.title("승강기 현장 관찰 기록")
    window.geometry("900x710")
    window.minsize(720, 530)
    window.transient(root)
    window._ui_theme = getattr(root, "_ui_theme", "light")
    window._language = getattr(root, "_language", "ko")
    record = normalize_inspection_record(panel.inspection_record)

    tk.Label(window, text="현장 관찰 기록", font=("맑은 고딕", 15, "bold"), anchor="w").pack(
        fill="x", padx=18, pady=(14, 4))
    tk.Label(
        window,
        text="NCS 엘리베이터 점검의 위치별 학습 흐름 참고. 현장 확인·증빙 기록이며 KC 적합 판정이 아닙니다.",
        anchor="w", wraplength=820, justify="left",
    ).pack(fill="x", padx=18, pady=(0, 10))

    head = tk.Frame(window)
    head.pack(fill="x", padx=18)
    date_var = tk.StringVar(value=record["inspected_at"])
    inspector_var = tk.StringVar(value=record["inspector"])
    for label, variable, width in (("확인 일시", date_var, 22), ("확인자", inspector_var, 23)):
        tk.Label(head, text=label).pack(side="left", padx=(0, 5))
        tk.Entry(head, textvariable=variable, width=width).pack(side="left", padx=(0, 22))

    body = tk.Frame(window)
    body.pack(fill="both", expand=True, padx=18, pady=10)
    canvas = tk.Canvas(body, highlightthickness=0)
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    content = tk.Frame(canvas)
    content_id = canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(content_id, width=e.width))

    fields = {}
    for key, title, hint in LOCATIONS:
        item = record["locations"][key]
        group = tk.LabelFrame(content, text=f" {title} ", padx=10, pady=7)
        group.pack(fill="x", pady=(0, 8))
        status = tk.StringVar(value=item["status"])
        tk.Label(group, text=hint, anchor="w").pack(fill="x")
        ttk.Combobox(group, textvariable=status, values=STATES, state="readonly", width=18).pack(
            anchor="w", pady=3)
        tk.Label(group, text="관찰·측정 내용 (최대 1,500자)", anchor="w").pack(fill="x")
        observation = tk.Text(group, height=3, wrap="word")
        observation.insert("1.0", item["observation"])
        observation.pack(fill="x", pady=(2, 5))
        tk.Label(group, text="근거 자료 (파일명·측정 기록·제조사 문서 등, 최대 500자)", anchor="w").pack(fill="x")
        evidence = tk.Entry(group)
        evidence.insert(0, item["evidence"])
        evidence.pack(fill="x", pady=(2, 0))
        fields[key] = (status, observation, evidence)

    footer = tk.Frame(window)
    footer.pack(fill="x", padx=18, pady=(0, 12))

    def save():
        proposed = {
            "inspected_at": date_var.get(), "inspector": inspector_var.get(),
            "locations": {
                key: {"status": status.get(), "observation": observation.get("1.0", "end-1c"),
                      "evidence": evidence.get()}
                for key, (status, observation, evidence) in fields.items()
            },
        }
        panel.services.push_undo_state(panel)
        panel.inspection_record = normalize_inspection_record(proposed)
        window.destroy()

    SkyButton(footer, text="기록 적용", command=save, width=13).pack(side="right")
    SkyButton(footer, text="취소", command=window.destroy, width=10).pack(side="right", padx=8)
    apply_theme(window, window._ui_theme)
    apply_font_scale(window, getattr(root, "_font_size", 10))
    window.focus_set()
    return window
