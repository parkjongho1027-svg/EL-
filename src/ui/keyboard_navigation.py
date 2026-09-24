"""탭·Enter·Shift+Tab 입력 이동을 담당하는 Tk UI 믹스인."""
import tkinter as tk
from tkinter import ttk


def focus_input_for_replacement(entry):
    """Tab으로 이동한 숫자칸의 기존 값을 바로 덮어쓸 수 있게 선택한다."""
    entry.focus_set()
    entry.selection_range(0, tk.END)
    entry.icursor(tk.END)


class KeyboardNavigationMixin:
    def _shortcut_calculate(self, _event=None):
        self.active_panel().calculate()
        return "break"

    def _shortcut_clear(self, _event=None):
        panel = self.active_panel()
        clear_command = getattr(panel, "clear", None) or getattr(panel, "reset", None)
        if clear_command:
            clear_command()
        return "break"

    def _shortcut_undo(self, _event=None):
        self.active_panel().undo_last()
        return "break"

    def _shortcut_history(self, _event=None):
        self.active_panel().show_history()
        return "break"

    def _shortcut_projects(self, _event=None):
        self.open_project_manager()
        return "break"

    def _shortcut_integrated(self, _event=None):
        self.calculate_all()
        return "break"

    def _shortcut_next_tab(self, event=None):
        """Space 또는 Ctrl+Right로 네 계산 탭을 순서대로 순환합니다."""
        focus = self.root.focus_get()
        if focus is not None and focus.winfo_toplevel() is not self.root:
            return None
        if event is not None and event.keysym == "space":
            # 문자 입력칸과 버튼에서 필요한 공백/클릭 동작은 가로채지 않습니다.
            if isinstance(focus, (tk.Text, ttk.Combobox, tk.Button)):
                return None
            if isinstance(focus, tk.Entry):
                # 교통량의 메모 입력칸은 실제 문장에 공백이 필요합니다.
                if (focus is self.traffic_panel.entries.get("criterion_source") or
                        focus in self.scurve_panel.measurement_paths.values()):
                    return None
        return self._move_to_next_tab()

    def _mark_calculated_input(self,panel,entry):
        """Enter 계산 직후 Tab은 입력칸 하나가 아니라 다음 계산 창으로 이동한다."""
        self._tab_after_enter=(panel,entry)

    def _clear_calculated_on_edit(self,event):
        if event.keysym not in ('Return','Tab','ISO_Left_Tab','Shift_L','Shift_R',
                                'Control_L','Control_R','Alt_L','Alt_R'):
            self._tab_after_enter=None

    def _move_to_next_tab(self,direction=1):
        self._tab_after_enter=None
        try:
            current=self.notebook.index(self.notebook.select())
            next_index=(current+direction)%self.notebook.index('end')
            self.notebook.select(next_index)
            panels=self.panels+[self.criteria_panel,self.scurve_panel]
            self.root.after_idle(lambda i=next_index,back=direction<0:
                                 self._focus_first_input(panels[i],last=back))
        except (tk.TclError,IndexError):
            return None
        return 'break'

    def _visible_inputs(self, panel):
        """현재 보이는 입력칸만 순서대로 돌려준다."""
        if panel is getattr(self, 'scurve_panel', None) and panel.mode_tabs.index(panel.mode_tabs.select()) == 1:
            candidates = [*panel.energy_entries.values(), *panel.measurement_paths.values()]
        else:
            candidates = list(getattr(panel, "entries", {}).values())
            if panel is self.criteria_panel:
                candidates += list(panel.traction_entries.values())
        entries = []
        for entry in candidates:
            try:
                if str(entry.cget("state")) != "disabled" and entry.winfo_viewable():
                    entries.append(entry)
            except (tk.TclError, AttributeError):
                continue
        return entries

    def _focus_first_input(self, panel, last=False):
        """탭 이동 직후 첫 번째(역방향은 마지막) 입력값을 전체 선택한다."""
        entries = self._visible_inputs(panel)
        if entries:
            focus_input_for_replacement(entries[-1 if last else 0])

    def _focus_adjacent_input(self, panel, current, direction=1):
        if self._tab_after_enter == (panel,current) and direction>0:
            return self._move_to_next_tab()
        self._tab_after_enter=None
        entries = self._visible_inputs(panel)
        if not entries:
            return "break"
        try:
            index = entries.index(current)
        except ValueError:
            index = -1 if direction > 0 else 0
        target_index = index + direction
        if 0 <= target_index < len(entries):
            target = entries[target_index]
            focus_input_for_replacement(target)
        else:
            if panel is getattr(self, 'scurve_panel', None):
                subtab = panel.mode_tabs.index(panel.mode_tabs.select())
                if direction > 0 and subtab == 0:
                    panel.mode_tabs.select(1)
                    self.root.after_idle(lambda:self._focus_first_input(panel))
                    return "break"
                if direction < 0 and subtab == 1:
                    panel.mode_tabs.select(0)
                    self.root.after_idle(lambda:self._focus_first_input(panel,last=True))
                    return "break"
            # 마지막 입력칸에서 Tab을 누르면 다음 계산창으로 넘어가고 첫 입력칸에 즉시 포커스합니다.
            return self._move_to_next_tab(direction)
        return "break"
