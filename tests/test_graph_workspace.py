"""Saved graphs must be reproducible and PNG files must work without Pillow."""

import pytest
from types import SimpleNamespace

from src.persistence import storage
from src.ui.chart_png import export_chart_png
from src.ui.graph_workspace import GraphWindow, graph_data


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
