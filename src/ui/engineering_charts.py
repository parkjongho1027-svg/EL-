"""Compatibility entry points for the shared chart workspace."""

from tkinter import messagebox

from src.ui.graph_workspace import open_graph


def show_tension(panel):
    return open_graph(panel, "traction")


def show_capacity(panel):
    if not getattr(panel, "last_capacity_inputs", None):
        messagebox.showinfo("교통량 분석", "교통량을 먼저 계산하세요.", parent=panel)
        return None
    return open_graph(panel, "traffic")
