"""Pre-installation design document references, separate from KC calculations."""

import tkinter as tk
from tkinter import ttk

from src.core.design_documents import DOCUMENT_AREAS, STATES, normalize_design_documents
from theme_manager import apply_font_scale, apply_theme
from ui_components import SkyButton


def open_design_documents_dialog(panel):
    root = panel.winfo_toplevel()
    window = tk.Toplevel(panel)
    window.title("설치 전 설계자료 확인")
    window.geometry("900x710")
    window.minsize(720, 530)
    window.transient(root)
    window._ui_theme = getattr(root, "_ui_theme", "light")
    window._language = getattr(root, "_language", "ko")
    record = normalize_design_documents(panel.design_documents)

    tk.Label(window, text="설치 전 설계자료 확인", font=("맑은 고딕", 15, "bold"), anchor="w").pack(
        fill="x", padx=18, pady=(14, 4))
    tk.Label(
        window,
        text="설계도면·제조사 사양서·건물 계획자료 등 계산에 사용한 문서의 출처를 기록합니다. "
             "자료 유무는 계산값의 정확성이나 KC 적합성을 자동 판정하지 않습니다.",
        anchor="w", wraplength=820, justify="left",
    ).pack(fill="x", padx=18, pady=(0, 10))

    head = tk.Frame(window)
    head.pack(fill="x", padx=18)
    date_var = tk.StringVar(value=record["reviewed_at"])
    reviewer_var = tk.StringVar(value=record["reviewer"])
    for label, variable, width in (("자료 확인일", date_var, 22), ("확인자", reviewer_var, 23)):
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
    for key, title, hint in DOCUMENT_AREAS:
        item = record["areas"][key]
        group = tk.LabelFrame(content, text=f" {title} ", padx=10, pady=7)
        group.pack(fill="x", pady=(0, 8))
        status = tk.StringVar(value=item["status"])
        tk.Label(group, text=hint, anchor="w").pack(fill="x")
        ttk.Combobox(group, textvariable=status, values=STATES, state="readonly", width=18).pack(
            anchor="w", pady=3)
        tk.Label(group, text="설계 입력값·가정 메모 (최대 1,500자)", anchor="w").pack(fill="x")
        note = tk.Text(group, height=3, wrap="word")
        note.insert("1.0", item["note"])
        note.pack(fill="x", pady=(2, 5))
        tk.Label(group, text="자료 출처 (문서명·도면번호·버전·페이지 등, 최대 500자)", anchor="w").pack(fill="x")
        source = tk.Entry(group)
        source.insert(0, item["source"])
        source.pack(fill="x", pady=(2, 0))
        fields[key] = (status, note, source)

    footer = tk.Frame(window)
    footer.pack(fill="x", padx=18, pady=(0, 12))

    def save():
        proposed = {
            "reviewed_at": date_var.get(), "reviewer": reviewer_var.get(),
            "areas": {
                key: {"status": status.get(), "note": note.get("1.0", "end-1c"),
                      "source": source.get()}
                for key, (status, note, source) in fields.items()
            },
        }
        panel.services.push_undo_state(panel)
        panel.design_documents = normalize_design_documents(proposed)
        window.destroy()

    SkyButton(footer, text="자료 기록 적용", command=save, width=15).pack(side="right")
    SkyButton(footer, text="취소", command=window.destroy, width=10).pack(side="right", padx=8)
    apply_theme(window, window._ui_theme)
    apply_font_scale(window, getattr(root, "_font_size", 10))
    window.focus_set()
    return window
