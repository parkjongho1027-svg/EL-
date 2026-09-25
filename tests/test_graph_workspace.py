"""Saved graphs must be reproducible and PNG files must work without Pillow."""

import pytest
from types import SimpleNamespace

from src.persistence import storage
from src.core.energy_model import compare_trips
from src.ui.chart_png import export_chart_png
from src.ui.graph_workspace import GraphWindow, graph_data, manage_graphs, ComparisonWindow
from src.ui.native_plot import render_png, stack_pngs
from src.ui.graph_axes import axes_for_graphs
import struct


def test_saved_graphs_roundtrip_and_multiple_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "get_data_file_path", lambda: tmp_path / "user_data.json"
    )
    store = storage.PersistentStore()
    inputs = {
        "values": {
            "Wc": "1500",
            "Q": "1000",
            "OB": "50",
            "H": "30",
            "wr": "0.8",
            "n": "6",
        }
    }
    store.add_graph("traction", "장력 사례 1", "담당자 A", inputs)
    store.add_graph("traction", "장력 사례 2", "담당자 B", inputs)
    store.add_graph(
        "traffic",
        "수송 사례",
        "담당자 A",
        dict(
            floors=12,
            cars=2,
            seats=15,
            board_rate=0.8,
            travel_s=40,
            door_s=4,
            passenger_s=2,
        ),
    )
    reloaded = storage.PersistentStore()
    assert [record["name"] for _, record in reloaded.graph_history()] == [
        "장력 사례 1",
        "장력 사례 2",
        "수송 사례",
    ]
    assert len(reloaded.graph_history("traction")) == 2
    assert len(reloaded.graph_history("traffic")) == 1
    reloaded.update_graph(1, name="장력 비교", owner="새 담당자")
    assert reloaded.graph_history("traction")[-1][1]["owner"] == "새 담당자"
    for _, record in reloaded.graph_history():
        assert graph_data(record["kind"], record["state"])
    reloaded.delete_graphs([0, 2])
    assert [
        record["name"] for _, record in storage.PersistentStore().graph_history()
    ] == ["장력 비교"]
    with pytest.raises(ValueError):
        reloaded.add_graph("traction", "", "담당자", inputs)


def test_tension_and_capacity_png_signatures():
    tension = graph_data(
        "traction",
        {
            "values": {
                "Wc": "1500",
                "Q": "1000",
                "OB": "50",
                "H": "30",
                "wr": "0.8",
                "n": "6",
            }
        },
    )
    capacity = graph_data(
        "traffic",
        dict(
            floors=12,
            cars=2,
            seats=15,
            board_rate=0.8,
            travel_s=40,
            door_s=4,
            passenger_s=2,
        ),
    )
    assert export_chart_png("traction", tension).startswith(b"\x89PNG\r\n\x1a\n")
    assert export_chart_png("traffic", capacity["per_floor"]).startswith(
        b"\x89PNG\r\n\x1a\n"
    )
    with pytest.raises(ValueError):
        export_chart_png("unknown", tension)


def test_live_simulation_window_reuses_completed_profile():
    state = {"distance": "30"}
    profile = {"samples": [(0, 0, 0, 0, 0)]}
    messages = []
    display = SimpleNamespace(delete=lambda *_: messages.append("cleared"))
    label = SimpleNamespace(
        configure=lambda **options: messages.append(options["text"])
    )
    chart = SimpleNamespace(
        source=lambda: state.copy(),
        state=None,
        kind="mechanical",
        panel=SimpleNamespace(_graph_state_mechanical=state.copy(), _profile=profile),
        canvas=display,
        status=label,
        redraw=lambda: messages.append("drawn"),
        _pending=5,
    )
    GraphWindow.refresh(chart)
    assert chart.data is profile and messages[-1] == "drawn"
    chart.panel._graph_state_mechanical = {"distance": "40"}
    GraphWindow.refresh(chart)
    assert chart.data is None and messages[-2] == "cleared"


@pytest.mark.parametrize("kind", ["mechanical", "electrical"])
def test_saved_simulation_group_opens_one_comparison_window(kind, monkeypatch):
    state = {"distance": "30", "vmax": "2", "amax": "1", "jerk": "0.8", "mass": "1500", "force": "100"}
    profile = graph_data("mechanical", state)
    data = profile if kind == "mechanical" else compare_trips(
        dict(distance=30, car_mass=1000, load_mass=500, counterweight_mass=1500,
             equivalent_extra_mass=0, resistance=100, direction="상승",
             drive_efficiency=.85, regen_efficiency=.5, auxiliary_kw=.1),
        dict(vmax=2, amax=1, jerk=.8), dict(vmax=2, amax=1, jerk=.8),
    )
    records = [(0, {"kind": kind, "state": state, "name": "A"}),
               (1, {"kind": kind, "state": state, "name": "B"})]
    panel = SimpleNamespace(store=SimpleNamespace(graph_history=lambda selected=None: records))
    created = []
    monkeypatch.setattr("src.ui.graph_workspace.open_record_manager",
                        lambda _panel, _title, _fields, _records, load, *_args, **_kwargs: load([0, 1]))
    monkeypatch.setattr("src.ui.graph_workspace.graph_data", lambda _kind, _state: data)
    monkeypatch.setattr("src.ui.graph_workspace.ComparisonWindow",
                        lambda _panel, _kind, prepared, axes: created.append((prepared, axes)))
    monkeypatch.setattr("src.ui.graph_workspace.open_graph",
                        lambda *_args, **_kwargs: pytest.fail("Should not open separate chart windows"))
    manage_graphs(panel, kind)
    assert len(created) == 1 and len(created[0][0]) == 2
    assert created[0][1]["x_max"] >= profile["duration_s"]


def test_comparison_png_contains_colored_profiles_and_stacked_energy():
    short = graph_data("mechanical", dict(distance="20", vmax="2", amax="1", jerk=".8", mass="1500", force="100"))
    long = graph_data("mechanical", dict(distance="40", vmax="2", amax="1", jerk=".8", mass="1500", force="100"))
    palette = {"surface": "#ffffff", "text": "#222222", "accent": "#2879cc"}
    axes = axes_for_graphs("mechanical", [short, long])
    png = render_png(short, palette, size=(640, 350), axes=axes,
                     comparisons=[(short, "#2475d0"), (long, "#e36b28")])
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    stacked = stack_pngs([png, png])
    assert struct.unpack_from("!2I", stacked, 16) == (640, 700)
