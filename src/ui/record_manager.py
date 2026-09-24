"""Project-manager-style history table with checkboxes and batch actions."""

import tkinter as tk
from tkinter import ttk
from theme_manager import apply_theme, apply_font_scale
from ui_components import SkyButton, WindowManager, app_ask_string, messagebox


def open_record_manager(
    parent,
    title,
    headers,
    records,
    load,
    delete,
    rename=None,
    change_owner=None,
    multi_load=True,
    save_current=None,
):
    window = tk.Toplevel(parent)
    window.title(title)
    window.minsize(740, 480)
    window.transient(parent.winfo_toplevel())
    window._ui_theme = getattr(parent.winfo_toplevel(), "_ui_theme", "light")
    window._language = getattr(parent.winfo_toplevel(), "_language", "ko")
    WindowManager.center(window, parent, 960, 580)
    toolbar = tk.Frame(window)
    toolbar.pack(fill="x", padx=16, pady=(14, 8))
    if save_current is not None:

        def save_and_refresh():
            save_current()
            refresh()

        SkyButton(
            toolbar,
            text="현재 입력 새로 저장",
            command=save_and_refresh,
            font=("맑은 고딕", 10, "bold"),
            width=16,
        ).pack(side="right", padx=(10, 0))
    heading = tk.Frame(toolbar)
    heading.pack(side="left", fill="x", expand=True)
    tk.Label(heading, text=title, font=("맑은 고딕", 15, "bold"), anchor="w").pack(
        fill="x"
    )
    hint = tk.Label(
        heading,
        text="행을 클릭하거나 드래그해 선택하세요. 선택한 기록은 한 번에 삭제할 수 있습니다.",
        font=("맑은 고딕", 10),
        anchor="w",
    )
    hint._theme_role = "muted"
    hint.pack(fill="x", pady=(3, 0))
    border = tk.Frame(window)
    border._theme_role = "history_card_border"
    border.pack(fill="both", expand=True, padx=16, pady=(0, 10))
    card = tk.Frame(border)
    card._theme_role = "surface"
    card.pack(fill="both", expand=True, padx=2, pady=2)
    label = tk.Label(
        card,
        text="저장된 기록",
        font=("맑은 고딕", 11, "bold"),
        anchor="w",
        padx=12,
        pady=8,
    )
    label._theme_role = "header_1"
    label.pack(fill="x")
    table = tk.Frame(card)
    table.pack(fill="both", expand=True, padx=8, pady=8)
    columns = ("checked", *[key for key, _title, _width in headers])
    tree = ttk.Treeview(
        table,
        columns=columns,
        show="headings",
        style="Project.Treeview",
        selectmode="extended",
    )
    tree.heading("checked", text="체크")
    tree.column("checked", width=62, stretch=False, anchor="center")
    for key, text, width in headers:
        tree.heading(key, text=text)
        tree.column(key, width=width, minwidth=80, anchor="w")
    scroll = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    checked = set()
    drag = {"active": False, "target": True, "visited": set()}
    rows = {}

    def refresh():
        rows.clear()
        tree.delete(*tree.get_children())
        for position, (index, values) in enumerate(records()):
            rows[str(index)] = index
            tree.insert(
                "",
                "end",
                iid=str(index),
                values=("☑" if index in checked else "□", *values),
                tags=("even" if position % 2 == 0 else "odd",),
            )
        checked.intersection_update(rows.values())

    def paint(row):
        values = list(tree.item(row, "values"))
        if values:
            values[0] = "☑" if rows[row] in checked else "□"
            tree.item(row, values=values)

    def press(event):
        row = tree.identify_row(event.y)
        if not row:
            return "break"
        drag.update(active=True, target=rows[row] not in checked, visited={row})
        toggle(row, drag["target"])
        return "break"

    def toggle(row, target):
        if target:
            checked.add(rows[row])
        else:
            checked.discard(rows[row])
        tree.focus(row)
        paint(row)

    def motion(event):
        if drag["active"]:
            row = tree.identify_row(event.y)
            if row in rows and row not in drag["visited"]:
                drag["visited"].add(row)
                toggle(row, drag["target"])
        return "break"

    def selected():
        result = tuple(index for index in rows.values() if index in checked)
        if not result:
            messagebox.showinfo(title, "기록을 선택하세요.", parent=window)
        return result

    def load_selected():
        chosen = selected()
        if not chosen:
            return
        if not multi_load and len(chosen) != 1:
            messagebox.showinfo(title, "불러올 기록 하나만 선택하세요.", parent=window)
            return
        load(chosen)

    def delete_selected():
        chosen = selected()
        if chosen and messagebox.askyesno(
            title, f"선택한 기록 {len(chosen)}개를 삭제할까요?", parent=window
        ):
            delete(chosen)
            checked.clear()
            refresh()

    def rename_selected():
        chosen = selected()
        if len(chosen) != 1:
            if chosen:
                messagebox.showinfo(
                    title, "이름을 변경할 기록 하나만 선택하세요.", parent=window
                )
            return
        name = app_ask_string(title, "새 이름을 입력하세요.", parent=window)
        if name is not None and name.strip():
            rename(chosen[0], name.strip())
            refresh()

    def owner_selected():
        chosen = selected()
        if not chosen:
            return
        owner = app_ask_string(
            title,
            f"선택한 {len(chosen)}개 그래프의 담당자를 입력하세요.",
            parent=window,
        )
        if owner is not None and owner.strip():
            change_owner(chosen, owner.strip())
            refresh()

    actions = tk.Frame(window)
    actions.pack(fill="x", padx=16, pady=(0, 14))
    SkyButton(actions, text="선택 기록 불러오기", command=load_selected, width=18).pack(
        side="left"
    )
    SkyButton(actions, text="삭제", command=delete_selected, width=8).pack(side="right")
    if change_owner:
        SkyButton(actions, text="담당자 변경", command=owner_selected, width=13).pack(
            side="right", padx=5
        )
    if rename:
        SkyButton(actions, text="이름 변경", command=rename_selected, width=12).pack(
            side="right", padx=5
        )
    tree.bind("<ButtonPress-1>", press)
    tree.bind("<B1-Motion>", motion)
    tree.bind("<ButtonRelease-1>", lambda _event: drag.update(active=False))
    theme = window._ui_theme
    for row, bg in (
        ("even", "#ffffff" if theme == "light" else "#07131d"),
        ("odd", "#eef5fa" if theme == "light" else "#0b2233"),
    ):
        tree.tag_configure(row, background=bg)
    refresh()
    apply_theme(window, theme)
    apply_font_scale(window, getattr(parent.winfo_toplevel(), "_font_size", 10))
    return window
