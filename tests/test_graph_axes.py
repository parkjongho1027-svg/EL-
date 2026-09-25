"""Selected charts must retain one numeric scale across windows and PNG export."""

import struct
import zlib

import pytest

from src.ui.native_plot import render_png
from src.ui.chart_png import export_chart_png
from src.ui.graph_axes import axes_for_graphs, nice_step
from src.ui.graph_workspace import graph_data


def test_traction_cohort_uses_one_round_axis_for_different_distances():
    case = {
        "values": {
            "Wc": "1500",
            "Q": "1000",
            "OB": "50",
            "H": "30",
            "wr": "0.8",
            "n": "6",
        }
    }
    first = graph_data("traction", case)
    second = graph_data("traction", {**case, "values": {**case["values"], "H": "45"}})
    axes = axes_for_graphs("traction", [first, second])
    assert axes["x_max"] >= 45
    assert axes["x_max"] / axes["x_step"] == round(axes["x_max"] / axes["x_step"])
    assert axes["y_max"] >= max(max(sample[1:]) for sample in second)
    assert export_chart_png("traction", first, axes=axes).startswith(b"\x89PNG")
    assert export_chart_png("traction", second, axes=axes).startswith(b"\x89PNG")


def test_capacity_cohort_has_integer_count_ticks_and_same_floor_axis():
    settings = dict(
        cars=2, seats=15, board_rate=0.8, travel_s=40, door_s=4, passenger_s=2
    )
    first = graph_data("traffic", dict(settings, floors=12))
    second = graph_data("traffic", dict(settings, floors=20))
    axes = axes_for_graphs("traffic", [first, second])
    assert axes["x_max"] >= 19
    assert isinstance(axes["x_step"], int)
    assert isinstance(axes["y_step"], int)
    assert axes["y_step"] >= 1
    assert export_chart_png("traffic", first["per_floor"], axes=axes).startswith(
        b"\x89PNG"
    )


def test_traffic_png_keeps_comparison_y_scale():
    axes = dict(x_max=10, x_step=2, y_min=0, y_max=10, y_step=2)
    png = export_chart_png("traffic", [1, 2], width=500, height=300, axes=axes)
    position, compressed = 8, bytearray()
    while position < len(png):
        size = struct.unpack_from("!I", png, position)[0]
        tag = png[position + 4 : position + 8]
        if tag == b"IDAT":
            compressed.extend(png[position + 8 : position + 8 + size])
        position += 12 + size
    raw = zlib.decompress(compressed)
    # At the 2-passenger grid line, outside the bars, the PNG must use 10 as
    # its Y maximum rather than reverting to the highest value in this record.
    y = round(235 - (235 - 70) * 2 / 10)
    offset = y * (1 + 500 * 3) + 1 + 300 * 3
    assert raw[offset : offset + 3] == bytes((226, 232, 237))


def test_simulation_png_uses_shared_time_and_power_limits():
    def run(distance):
        return graph_data(
            "mechanical",
            {
                "distance": str(distance),
                "vmax": "2",
                "amax": "1",
                "jerk": "0.8",
                "mass": "1500",
                "force": "100",
            },
        )

    short, long = run(30), run(60)
    axes = axes_for_graphs("mechanical", [short, long])
    assert axes["x_max"] >= long["duration_s"]
    palette = {"surface": "#ffffff", "text": "#222222", "accent": "#2879cc"}
    for profile in (short, long):
        png = render_png(profile, palette, size=(600, 350), axes=axes)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert nice_step(23) in (5, 10)
    with pytest.raises(ValueError):
        nice_step(0)
