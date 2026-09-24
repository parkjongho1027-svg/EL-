"""Tk/ttk 테마와 글꼴 크기 관리."""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from app_config import BUTTON_BG, BUTTON_ACTIVE_BG, BUTTON_TEXT


def _is_sky_button(widget):
    # 호출 시점에만 가져와 공통 위젯과 테마의 순환 import를 피한다.
    from ui_components import SkyButton
    return isinstance(widget, SkyButton)

THEMES = {
    "light": {
        "background": "#ffffff",
        "surface": "#ffffff",
        "result": "#f7faff",
        "text": "#1f1f1f",
        "muted": "#555555",
        "entry": "#ffffff",
        "disabled_entry": "#eeeeee",
        "button": BUTTON_BG,
        "button_active": BUTTON_ACTIVE_BG,
        "canvas": "#f2f4f7",
        "subtle": "#eaf3fb",
        "tab": "#e9ecef",
        "tab_selected": "#ffffff",
        "selection_bg": "#075c9c",
        "selection_fg": "#ffffff",
        "accent": "#2677a8",
        "border": "#aebdca",
        "header_1": "#dcecf8",
        "header_1_text": "#174d73",
        "header_2": "#e9ecef",
        "header_2_text": "#3f464d",
    },
    "dark": {
        # 참고 이미지처럼 바탕과 박스 안쪽은 검정으로 두고 파란색은
        # 테두리·제목·선택된 탭에만 사용합니다. 검정과 파랑의 대비가
        # 살아나므로 박스를 파란색으로 전부 채웠을 때보다 구분이 쉽습니다.
        "background": "#000000",
        "surface": "#03080d",
        "result": "#02070c",
        "text": "#ffffff",
        # 안내문·보조문구까지 회색으로 흐리지 않고 순백색으로 표시합니다.
        "muted": "#ffffff",
        "entry": "#06111b",
        "disabled_entry": "#101820",
        # 탭 선택 영역처럼 검정 바탕·흰 글씨·파란 외곽선을 사용합니다.
        "button": "#000000",
        "button_active": "#062f4f",
        "canvas": "#000000",
        "subtle": "#02070c",
        "tab": "#02070c",
        "tab_selected": "#075c9c",
        "selection_bg": "#075c9c",
        "selection_fg": "#ffffff",
        "accent": "#35adff",
        "border": "#167fca",
        "header_1": "#06233a",
        "header_1_text": "#ffffff",
        "header_2": "#03080d",
        "header_2_text": "#ffffff",
    },
}

def get_theme(widget):
    """위젯이 속한 창의 현재 테마 이름과 색상표를 반환합니다."""
    window = widget.winfo_toplevel()
    mode = getattr(window, "_ui_theme", "light")
    return mode, THEMES[mode]

def apply_theme(widget, mode):
    """현재 창과 그 안의 모든 Tk 위젯에 선택한 테마를 적용합니다."""
    colors = THEMES[mode]

    # Windows에 설치된 Tk 버전에 따라 일부 색상 옵션을 지원하지 않을 수 있습니다.
    # 특정 위젯 하나의 옵션 오류가 프로그램 전체 종료로 이어지지 않게 건너뜁니다.
    try:
        if _is_sky_button(widget):
            # 전용 버튼은 내부 글자판까지 직접 칠하므로 자식 위젯 재귀를 중단합니다.
            widget.apply_palette(mode)
            return
        elif isinstance(widget, (tk.Tk, tk.Toplevel)):
            widget.configure(bg=colors["background"])
        elif isinstance(widget, tk.LabelFrame):
            # 다크 모드에서는 검정 박스 둘레와 제목만 파랗게 밝혀
            # 참고 이미지의 백라이트 테두리와 비슷한 인상을 만듭니다.
            widget.configure(
                bg=colors["surface"],
                fg=colors["text"],
                highlightbackground=colors["border"],
                highlightcolor=colors["accent"],
                highlightthickness=1,
                bd=1,
                relief="solid"
            )
        elif isinstance(widget, tk.Frame):
            role = getattr(widget, "_theme_role", "")
            if role == "history_card_border":
                # '입력 기록 1', '입력 기록 2' 카드마다 따로 만든 외부 프레임입니다.
                # 안쪽 카드와의 2픽셀 간격에 이 배경색이 그대로 노출되어
                # Windows 테마와 관계없이 카드 전체를 감싸는 선이 보입니다.
                widget.configure(
                    bg="#168bd2" if mode == "dark" else colors["border"],
                    bd=0,
                    relief="flat",
                    highlightthickness=0,
                )
            elif role == "subtle":
                widget.configure(bg=colors["subtle"])
            elif role == "canvas":
                widget.configure(bg=colors["canvas"])
            elif role == "surface":
                widget.configure(bg=colors["surface"])
            else:
                parent_bg = colors["background"]
                try:
                    parent_bg = widget.master.cget("bg")
                except (tk.TclError, AttributeError):
                    pass
                widget.configure(bg=parent_bg)
        elif isinstance(widget, tk.Canvas):
            widget.configure(bg=colors["canvas"])
        elif isinstance(widget, tk.Text):
            error_color = "#ff6b6b" if mode == "dark" else "red"
            widget.configure(bg=colors["result"],
                             fg=error_color if getattr(widget, "_result_error", False)
                                else colors["text"],
                             insertbackground=colors["text"],
                             selectbackground=colors["selection_bg"],
                             selectforeground=colors["selection_fg"],
                             highlightbackground=colors["border"],
                             highlightcolor=colors["accent"],
                             highlightthickness=1)
        elif isinstance(widget, tk.Entry):
            widget.configure(bg=colors["entry"], fg=colors["text"],
                             insertbackground=colors["text"],
                             selectbackground=colors["selection_bg"],
                             selectforeground=colors["selection_fg"],
                             disabledbackground=colors["disabled_entry"],
                             disabledforeground=colors["text"],
                             highlightbackground=colors["border"],
                             highlightcolor=colors["accent"],
                             highlightthickness=1,
                             relief="flat")
        elif isinstance(widget, tk.Listbox):
            widget.configure(bg=colors["entry"], fg=colors["text"],
                             selectbackground=colors["selection_bg"],
                             selectforeground=colors["selection_fg"],
                             highlightbackground=colors["border"],
                             highlightcolor=colors["accent"], highlightthickness=1)
        elif isinstance(widget, tk.Checkbutton):
            parent_bg = colors["surface"]
            try:
                parent_bg = widget.master.cget("bg")
            except (tk.TclError, AttributeError):
                pass
            widget.configure(
                bg=parent_bg, fg=colors["text"], activebackground=parent_bg,
                activeforeground=colors["text"], selectcolor=colors["entry"],
                highlightthickness=0
            )
        elif isinstance(widget, tk.Button):
            # 버튼 색상은 용도와 관계없이 한 가지 디자인으로 통일합니다.
            # 다크 모드: 검정 바탕 + 흰 글씨 + 항상 보이는 파란 외곽선
            # 라이트 모드: 회색 바탕 + 검정 글씨
            if mode == "dark":
                widget.configure(
                    bg="#000000",
                    fg="#ffffff",
                    activebackground=colors["button_active"],
                    activeforeground="#ffffff",
                    disabledforeground="#ffffff"
                )
                try:
                    # highlightbackground가 포커스가 없을 때도 파란 선을 그립니다.
                    # highlightcolor는 키보드 포커스를 받았을 때 같은 계열의
                    # 밝은 파랑으로 표시하여 테두리가 회색으로 바뀌지 않게 합니다.
                    widget.configure(
                        relief="flat", bd=0,
                        highlightthickness=2,
                        highlightbackground=colors["border"],
                        highlightcolor=colors["accent"],
                        takefocus=True
                    )
                except tk.TclError:
                    pass
            else:
                widget.configure(
                    bg=BUTTON_BG,
                    fg=BUTTON_TEXT,
                    activebackground=BUTTON_ACTIVE_BG,
                    activeforeground=BUTTON_TEXT,
                    disabledforeground="#607078"
                )
                try:
                    widget.configure(relief="flat", bd=0, highlightthickness=0)
                except tk.TclError:
                    pass
        elif isinstance(widget, tk.Label):
            role = getattr(widget, "_theme_role", "")
            parent_bg = colors["background"]
            try:
                parent_bg = widget.master.cget("bg")
            except (tk.TclError, AttributeError):
                pass
            if role == "header_1":
                widget.configure(bg=colors["header_1"], fg=colors["header_1_text"])
            elif role == "header_2":
                widget.configure(bg=colors["header_2"], fg=colors["header_2_text"])
            elif role == "subtle":
                widget.configure(bg=colors["subtle"], fg=colors["text"])
            elif role == "formula":
                widget.configure(
                    bg=colors["surface"], fg=colors["text"],
                    highlightbackground=colors["border"],
                    highlightcolor=colors["accent"],
                )
            else:
                widget.configure(bg=parent_bg,
                                 fg=colors["muted"] if role == "muted" else colors["text"])
    except tk.TclError:
        pass

    if isinstance(widget, (tk.Text, tk.Entry)):
        # 일부 Tk 버전에서는 창이 포커스를 잃었을 때 별도의 선택 배경색을 쓴다.
        try:
            widget.configure(inactiveselectbackground=colors["selection_bg"])
        except tk.TclError:
            pass

    for child in widget.winfo_children():
        apply_theme(child, mode)

def style_combobox_popdown(combobox):
    """펼쳐진 콤보박스 목록에 현재 화면 모드의 색상을 직접 적용합니다.

    ttk 콤보박스의 목록은 버튼을 누를 때 별도 창으로 만들어집니다. 그래서
    프로그램 시작 때 지정한 색만으로는 일부 Windows 환경에서 흰 목록이
    남습니다. 목록이 만들어진 뒤 이 함수를 다시 실행해 색상을 확정합니다.
    """
    mode, colors = get_theme(combobox)
    popup_bg = "#000000" if mode == "dark" else "#ffffff"
    popup_fg = "#ffffff" if mode == "dark" else "#1f1f1f"
    popup_select_bg = colors["selection_bg"]
    popup_select_fg = colors["selection_fg"]
    try:
        popdown = combobox.tk.call("ttk::combobox::PopdownWindow", combobox._w)
        listbox = f"{popdown}.f.l"
        combobox.tk.call(
            listbox, "configure",
            "-background", popup_bg,
            "-foreground", popup_fg,
            "-selectbackground", popup_select_bg,
            "-selectforeground", popup_select_fg,
            "-highlightbackground", colors["accent"],
            "-highlightcolor", colors["accent"],
            "-highlightthickness", 1,
        )
    except tk.TclError:
        # Tk 버전에 따라 내부 목록 경로가 다르면 옵션 데이터베이스 설정을 사용합니다.
        pass

def bind_combobox_popdown_theme(combobox):
    """목록을 열 때마다 현재 테마를 적용하도록 한 번만 연결합니다."""
    if getattr(combobox, "_popdown_theme_bound", False):
        return

    def restyle_after_open(_event):
        # 기본 클릭 동작이 목록을 만든 다음 실행되도록 아주 짧게 예약합니다.
        combobox.after(20, lambda: style_combobox_popdown(combobox))

    combobox.bind("<Button-1>", restyle_after_open, add="+")
    combobox.bind("<Alt-Down>", restyle_after_open, add="+")
    combobox._popdown_theme_bound = True

def configure_ttk_theme(root, mode):
    """Notebook 탭·콤보박스·스크롤바처럼 ttk가 그리는 위젯의 색을 바꿉니다."""
    colors = THEMES[mode]
    style = ttk.Style(root)
    try:
        # Combobox의 화살표를 눌렀을 때 열리는 목록은 본체와 별개의
        # Listbox이므로 옵션 데이터베이스에도 색을 따로 지정해야 합니다.
        popup_bg = "#000000" if mode == "dark" else "#ffffff"
        popup_fg = "#ffffff" if mode == "dark" else "#1f1f1f"
        popup_select_bg = colors["selection_bg"]
        popup_select_fg = colors["selection_fg"]
        root.option_add("*TCombobox*Listbox.background", popup_bg)
        root.option_add("*TCombobox*Listbox.foreground", popup_fg)
        root.option_add("*TCombobox*Listbox.selectBackground", popup_select_bg)
        root.option_add("*TCombobox*Listbox.selectForeground", popup_select_fg)
        root.option_add("*TCombobox*Listbox.highlightBackground", colors["accent"])
        root.option_add("*TCombobox*Listbox.highlightColor", colors["accent"])

        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(
            "TNotebook", background=colors["background"], borderwidth=1,
            bordercolor=colors["border"], lightcolor=colors["border"],
            darkcolor=colors["border"]
        )
        style.configure(
            "TNotebook.Tab", font=("맑은 고딕", 11),
            background=colors["tab"], foreground=colors["text"], padding=(10, 5),
            bordercolor=colors["border"], lightcolor=colors["border"],
            darkcolor=colors["border"]
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", colors["tab_selected"]), ("active", colors["tab_selected"])],
            foreground=[("selected", colors["text"]), ("active", colors["text"])]
        )
        style.configure(
            "TCombobox", fieldbackground=colors["entry"], background=colors["button"],
            foreground=colors["text"], arrowcolor=colors["accent"],
            bordercolor=colors["border"], lightcolor=colors["border"],
            darkcolor=colors["border"]
        )
        style.map(
            "TCombobox", fieldbackground=[("readonly", colors["entry"])],
            foreground=[("readonly", colors["text"])],
            selectbackground=[("readonly", colors["selection_bg"])],
            selectforeground=[("readonly", colors["selection_fg"])]
        )
        style.configure("Horizontal.TScrollbar", background=colors["button"],
                        troughcolor=colors["canvas"], arrowcolor=colors["text"])
        style.configure("Vertical.TScrollbar", background=colors["button"],
                        troughcolor=colors["canvas"], arrowcolor=colors["text"])
        style.configure(
            "Project.Treeview", font=("맑은 고딕", 10), rowheight=28,
            background=colors["entry"], fieldbackground=colors["entry"],
            foreground=colors["text"], bordercolor=colors["border"],
            borderwidth=1, relief="solid"
        )
        style.map(
            "Project.Treeview",
            background=[("selected", colors["selection_bg"])],
            foreground=[("selected", colors["selection_fg"])]
        )
        style.configure(
            "Project.Treeview.Heading", font=("맑은 고딕", 9, "bold"),
            background=colors["header_1"], foreground=colors["header_1_text"],
            bordercolor=colors["border"], padding=(8, 7), relief="flat"
        )
        style.map(
            "Project.Treeview.Heading",
            background=[("active", colors["tab_selected"])],
            foreground=[("active", colors["text"])],
        )

        # 이미 한 번 열렸던 목록은 옵션 데이터베이스만 바꿔서는 즉시
        # 갱신되지 않을 수 있어 현재 존재하는 목록에도 직접 적용합니다.
        def update_existing_popdowns(widget):
            if isinstance(widget, ttk.Combobox):
                bind_combobox_popdown_theme(widget)
                style_combobox_popdown(widget)
            for child in widget.winfo_children():
                update_existing_popdowns(child)

        update_existing_popdowns(root)
    except tk.TclError:
        # 지원하지 않는 ttk 색상 옵션이 있어도 기본 스타일로 계속 실행합니다.
        pass

def apply_font_scale(widget, selected_size):
    """명시된 글꼴의 굵기·비율을 보존하면서 기준 크기(10)를 조절합니다."""
    target_delta = int(selected_size) - 10
    try:
        target = widget._button if _is_sky_button(widget) else widget
        if "font" in target.keys():
            if not hasattr(target, "_base_font_actual"):
                target._base_font_actual = tkfont.Font(font=target.cget("font")).actual()
            base = target._base_font_actual
            size = max(7, abs(int(base.get("size", 10))) + target_delta)
            target.configure(font=(base.get("family", "맑은 고딕"), size,
                                   base.get("weight", "normal")))
    except (tk.TclError, ValueError, TypeError):
        pass
    if not _is_sky_button(widget):
        for child in widget.winfo_children():
            apply_font_scale(child, selected_size)
