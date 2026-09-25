"""공통 버튼과 앱 전용 다국어 다이얼로그."""

import tkinter as tk
import re
from src.config.constants import BUTTON_BG, BUTTON_ACTIVE_BG, BUTTON_TEXT
from src.ui.theme_manager import THEMES, apply_theme, apply_font_scale

_dialog_root = None


def set_dialog_root(root):
    global _dialog_root
    _dialog_root = root


def resolve_dialog_parent(parent=None):
    if parent is not None:
        return parent
    if _dialog_root is None:
        raise RuntimeError("대화창의 부모 창이 지정되지 않았습니다.")
    try:
        focused = _dialog_root.focus_get()
        return focused.winfo_toplevel() if focused is not None else _dialog_root
    except tk.TclError:
        return _dialog_root


def numeric_input_allowed(proposed, *, list_mode=False):
    """타이핑 중인 미완성 수식은 허용하고, 수식에 쓰지 않는 문자는 막는다."""
    alphabet = r"[0-9eE+\-*/^()., ×÷;]*" if list_mode else r"[0-9eE+\-*/^()., ×÷]*"
    return len(proposed) <= 200 and re.fullmatch(alphabet, proposed) is not None


def attach_numeric_validation(entry, *, list_mode=False):
    command = entry.register(
        lambda proposed: numeric_input_allowed(proposed, list_mode=list_mode)
    )
    entry.configure(validate="key", validatecommand=(command, "%P"))
    return entry


class SkyButton(tk.Frame):
    """파란 외곽선 안에 실제 Tk 버튼을 넣은 접근성 대응 공통 버튼입니다."""

    def __init__(self, master=None, **kwargs):
        text = kwargs.pop("text", "")
        self._command = kwargs.pop("command", None)
        self._state = kwargs.pop("state", "normal")
        font = kwargs.pop("font", ("맑은 고딕", 10))
        width = kwargs.pop("width", 0)
        inner_padx = kwargs.pop("padx", 7)
        inner_pady = kwargs.pop("pady", 4)
        cursor = kwargs.pop("cursor", "hand2")

        # 이전 tk/ttk 버튼에서 사용하던 색상 옵션은 공통 테마가 결정합니다.
        for option in (
            "bg",
            "background",
            "fg",
            "foreground",
            "activebackground",
            "activeforeground",
            "disabledforeground",
            "relief",
            "bd",
            "borderwidth",
            "highlightthickness",
            "highlightbackground",
            "highlightcolor",
            "style",
        ):
            kwargs.pop(option, None)

        super().__init__(master, bd=0, highlightthickness=0, takefocus=False, **kwargs)
        self._cursor = cursor
        self._theme_mode = "light"
        self._button = tk.Button(
            self,
            text=text,
            font=font,
            width=width,
            padx=inner_padx,
            pady=inner_pady,
            bd=0,
            relief="flat",
            command=self._invoke_command,
            takefocus=True,
        )
        self._button.pack(fill="both", expand=True, padx=2, pady=2)

        try:
            mode = getattr(master.winfo_toplevel(), "_ui_theme", "light")
        except (AttributeError, tk.TclError):
            mode = "light"
        self.apply_palette(mode)

    def _render(self):
        """현재 모드·사용 가능 상태·마우스 위치에 맞춰 버튼을 다시 그립니다."""
        if self._theme_mode == "dark":
            border = "#168bd2"
            normal_bg = "#000000"
            active_bg = "#062f4f"
            foreground = "#ffffff"
            disabled_fg = "#ffffff"
        else:
            border = "#9a9a9a"
            normal_bg = BUTTON_BG
            active_bg = BUTTON_ACTIVE_BG
            foreground = BUTTON_TEXT
            disabled_fg = "#666666"

        super().configure(
            bg=border, cursor=self._cursor if self._state != "disabled" else "arrow"
        )
        self._button.configure(
            bg=normal_bg,
            activebackground=active_bg,
            fg=foreground if self._state != "disabled" else disabled_fg,
            activeforeground=foreground,
            disabledforeground=disabled_fg,
            cursor=self._cursor if self._state != "disabled" else "arrow",
            state=self._state,
            highlightthickness=1 if self._button.focus_get() is self._button else 0,
            highlightbackground=border,
            highlightcolor=border,
        )

    def apply_palette(self, mode):
        self._theme_mode = mode if mode in THEMES else "light"
        self._render()

    def _invoke_command(self):
        if self._state != "disabled" and callable(self._command):
            return self._command()
        return None

    def configure(self, cnf=None, **kwargs):
        """기존 Button처럼 text·command·state를 실행 중에도 바꿀 수 있습니다."""
        if cnf:
            kwargs.update(cnf)
        if not hasattr(self, "_button"):
            return super().configure(**kwargs)
        if "text" in kwargs:
            self._button.configure(text=kwargs.pop("text"))
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            self._state = str(kwargs.pop("state"))
        if "width" in kwargs:
            self._button.configure(width=kwargs.pop("width"))
        if "font" in kwargs:
            self._button.configure(font=kwargs.pop("font"))
        if "cursor" in kwargs:
            self._cursor = kwargs.pop("cursor")
        if kwargs:
            super().configure(**kwargs)
        self._render()

    config = configure

    def cget(self, key):
        if key == "text":
            return self._button.cget("text")
        if key == "command":
            return self._command
        if key == "state":
            return self._state
        return super().cget(key)

    def invoke(self):
        return self._button.invoke()

    def focus_set(self):
        self._button.focus_set()


class WindowManager:
    """모든 보조창의 생성 위치와 화면 경계 처리를 한 곳에서 관리합니다."""

    SCREEN_MARGIN_X = 24
    SCREEN_MARGIN_Y = 72

    @classmethod
    def center(cls, window, parent=None, width=None, height=None):
        window.update_idletasks()
        screen_w = max(1, window.winfo_screenwidth())
        screen_h = max(1, window.winfo_screenheight())
        req_w = int(width or window.winfo_reqwidth())
        req_h = int(height or window.winfo_reqheight())
        # 큰 창도 화면 아래/옆으로 잘리지 않도록 실제 화면 안으로 제한합니다.
        width = min(req_w, max(320, screen_w - cls.SCREEN_MARGIN_X))
        height = min(req_h, max(220, screen_h - cls.SCREEN_MARGIN_Y))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")
        return width, height


def center_child_window(window, parent=None, width=None, height=None):
    """호환용 래퍼. 모든 창 배치는 WindowManager가 실제로 처리합니다."""
    return WindowManager.center(window, parent, width, height)


def _dialog_language(parent):
    if parent is None:
        parent = resolve_dialog_parent(parent)
    return getattr(parent, "_language", "ko")


def app_show_message(title, message, parent=None, kind="info", **_kwargs):
    """OS 언어와 무관하게 확인 버튼까지 앱 언어로 표시하는 안내창입니다."""
    parent = resolve_dialog_parent(parent)
    language = _dialog_language(parent)
    window = tk.Toplevel(parent)
    window.title(title)
    window.resizable(False, False)
    window.transient(parent)
    window._language = language
    window._ui_theme = getattr(parent, "_ui_theme", "light")
    symbols = {"info": "i", "warning": "!", "error": "×"}
    body = tk.Frame(window)
    body.pack(fill="both", expand=True, padx=22, pady=(22, 12))
    icon = tk.Label(
        body, text=symbols.get(kind, "i"), width=2, font=("맑은 고딕", 16, "bold")
    )
    icon._theme_role = "header_1" if kind != "error" else "header_2"
    icon.pack(side="left", anchor="n", padx=(0, 14))
    tk.Label(
        body,
        text=str(message),
        justify="left",
        anchor="w",
        wraplength=410,
        font=("맑은 고딕", 10),
    ).pack(side="left", fill="both", expand=True)
    button = SkyButton(
        window,
        text="OK" if language == "en" else "확인",
        command=window.destroy,
        width=10,
    )
    button.pack(pady=(0, 16))
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    apply_theme(window, window._ui_theme)
    apply_font_scale(window, getattr(parent, "_font_size", 10))
    center_child_window(window, parent, 500, max(190, window.winfo_reqheight()))
    window.grab_set()
    button.focus_set()
    window.wait_window()
    return "ok"


def app_ask_yes_no(title, message, parent=None, **_kwargs):
    """예/아니오까지 선택 언어로 고정되는 앱 전용 확인창입니다."""
    parent = resolve_dialog_parent(parent)
    language = _dialog_language(parent)
    answer = {"value": False}
    window = tk.Toplevel(parent)
    window.title(title)
    window.resizable(False, False)
    window.transient(parent)
    window._language = language
    window._ui_theme = getattr(parent, "_ui_theme", "light")
    tk.Label(
        window,
        text=str(message),
        justify="left",
        anchor="w",
        wraplength=430,
        font=("맑은 고딕", 10, "bold"),
    ).pack(fill="both", expand=True, padx=24, pady=(26, 16))
    buttons = tk.Frame(window)
    buttons.pack(pady=(0, 20))

    def finish(value):
        answer["value"] = value
        window.destroy()

    yes_button = SkyButton(
        buttons,
        text="Yes" if language == "en" else "예",
        command=lambda: finish(True),
        width=10,
    )
    yes_button.pack(side="left", padx=6)
    SkyButton(
        buttons,
        text="No" if language == "en" else "아니오",
        command=lambda: finish(False),
        width=10,
    ).pack(side="left", padx=6)
    window.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    window.bind("<Return>", lambda _event: finish(True))
    window.bind("<Escape>", lambda _event: finish(False))
    apply_theme(window, window._ui_theme)
    apply_font_scale(window, getattr(parent, "_font_size", 10))
    center_child_window(window, parent, 500, max(205, window.winfo_reqheight()))
    window.grab_set()
    yes_button.focus_set()
    window.wait_window()
    return answer["value"]


def app_ask_string(title, prompt, parent=None, initialvalue=""):
    """OK/Cancel과 제목까지 앱 언어로 표시하는 한 줄 입력창입니다."""
    parent = resolve_dialog_parent(parent)
    language = _dialog_language(parent)
    result = {"value": None}
    window = tk.Toplevel(parent)
    window.title(title)
    window.resizable(False, False)
    window.transient(parent)
    window._language = language
    window._ui_theme = getattr(parent, "_ui_theme", "light")
    tk.Label(
        window, text=prompt, justify="left", anchor="w", font=("맑은 고딕", 10)
    ).pack(fill="x", padx=22, pady=(22, 8))
    entry = tk.Entry(window, font=("맑은 고딕", 11))
    entry.pack(fill="x", padx=22, pady=(0, 16))
    entry.insert(0, initialvalue or "")
    entry.select_range(0, tk.END)
    buttons = tk.Frame(window)
    buttons.pack(pady=(0, 18))

    def finish(save):
        result["value"] = entry.get() if save else None
        window.destroy()

    SkyButton(
        buttons,
        text="OK" if language == "en" else "확인",
        command=lambda: finish(True),
        width=10,
    ).pack(side="left", padx=6)
    SkyButton(
        buttons,
        text="Cancel" if language == "en" else "취소",
        command=lambda: finish(False),
        width=10,
    ).pack(side="left", padx=6)
    window.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    window.bind("<Return>", lambda _event: finish(True))
    window.bind("<Escape>", lambda _event: finish(False))
    apply_theme(window, window._ui_theme)
    apply_font_scale(window, getattr(parent, "_font_size", 10))
    center_child_window(window, parent, 480, 205)
    window.grab_set()
    entry.focus_set()
    window.wait_window()
    return result["value"]


def app_ask_project_info(parent=None, initial_manager=""):
    """프로젝트 저장 시 프로젝트명과 담당자를 한 창에서 입력받습니다."""
    parent = resolve_dialog_parent(parent)
    language = _dialog_language(parent)
    result = {"value": None}
    window = tk.Toplevel(parent)
    window.title(
        "Save Elevator Project" if language == "en" else "승강기 프로젝트 저장"
    )
    window.resizable(False, False)
    window.transient(parent)
    window._language = language
    window._ui_theme = getattr(parent, "_ui_theme", "light")

    form = tk.Frame(window)
    form.pack(fill="both", expand=True, padx=24, pady=(22, 12))

    tk.Label(
        form,
        text="Project name" if language == "en" else "프로젝트명",
        anchor="w",
        font=("맑은 고딕", 10, "bold"),
    ).grid(row=0, column=0, sticky="w", pady=(0, 6))
    name_entry = tk.Entry(form, font=("맑은 고딕", 11), width=38)
    name_entry.grid(row=1, column=0, sticky="ew", pady=(0, 16))

    tk.Label(
        form,
        text="Manager" if language == "en" else "담당자",
        anchor="w",
        font=("맑은 고딕", 10, "bold"),
    ).grid(row=2, column=0, sticky="w", pady=(0, 6))
    manager_entry = tk.Entry(form, font=("맑은 고딕", 11), width=38)
    manager_entry.grid(row=3, column=0, sticky="ew")
    manager_entry.insert(0, initial_manager or "")
    form.columnconfigure(0, weight=1)

    buttons = tk.Frame(window)
    buttons.pack(pady=(4, 20))

    def finish(save):
        if not save:
            result["value"] = None
            window.destroy()
            return
        name = name_entry.get().strip()
        manager = manager_entry.get().strip()
        if not name:
            messagebox.showwarning(
                "Project Name" if language == "en" else "프로젝트명",
                "Enter a project name."
                if language == "en"
                else "프로젝트명을 입력해주세요.",
                parent=window,
            )
            name_entry.focus_set()
            return
        if not manager:
            messagebox.showwarning(
                "Project Manager" if language == "en" else "프로젝트 담당자",
                "Enter a manager name."
                if language == "en"
                else "담당자 이름을 입력해주세요.",
                parent=window,
            )
            manager_entry.focus_set()
            return
        result["value"] = (name, manager)
        window.destroy()

    SkyButton(
        buttons,
        text="Save" if language == "en" else "저장",
        command=lambda: finish(True),
        width=10,
    ).pack(side="left", padx=6)
    SkyButton(
        buttons,
        text="Cancel" if language == "en" else "취소",
        command=lambda: finish(False),
        width=10,
    ).pack(side="left", padx=6)
    window.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    window.bind("<Escape>", lambda _event: finish(False))
    name_entry.bind("<Return>", lambda _event: manager_entry.focus_set())
    manager_entry.bind("<Return>", lambda _event: finish(True))
    apply_theme(window, window._ui_theme)
    apply_font_scale(window, getattr(parent, "_font_size", 10))
    center_child_window(window, parent, 500, 285)
    window.grab_set()
    name_entry.focus_set()
    window.wait_window()
    return result["value"]


class AppMessageBox:
    showinfo = staticmethod(
        lambda title, message, **kwargs: app_show_message(
            title, message, kind="info", **kwargs
        )
    )
    showwarning = staticmethod(
        lambda title, message, **kwargs: app_show_message(
            title, message, kind="warning", **kwargs
        )
    )
    showerror = staticmethod(
        lambda title, message, **kwargs: app_show_message(
            title, message, kind="error", **kwargs
        )
    )
    askyesno = staticmethod(app_ask_yes_no)


messagebox = AppMessageBox()
