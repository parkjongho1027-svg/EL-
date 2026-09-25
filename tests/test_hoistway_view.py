"""Floor spacing, car floor alignment, and destination controls."""

from types import SimpleNamespace

import pytest

from src.core.hoistway import HoistwayTrip
from src.core.trajectory import scurve_profile
from src.ui.hoistway_geometry import HoistwayGeometry
from src.ui.hoistway_view import HoistwayView


@pytest.mark.parametrize("floors", [2, 10, 80, 100])
def test_floor_spacing_stays_readable_and_car_bottom_meets_selected_floor(floors):
    geometry = HoistwayGeometry(floors)
    trip = HoistwayTrip(floors, 1, floors, (floors - 1) * 3)
    assert all(geometry.floor_y(floor) - geometry.floor_y(floor + 1) == 68
               for floor in range(1, floors))
    assert geometry.height_px > (floors - 1) * 68
    assert geometry.car_bottom_y(trip, 0) == pytest.approx(geometry.floor_y(1))
    assert geometry.car_bottom_y(trip, trip.distance_m) == pytest.approx(geometry.floor_y(floors))
    assert geometry.counterweight_bottom_y(trip, 0) == pytest.approx(geometry.floor_y(floors))


class FloorValue:
    def __init__(self, value):
        self.value = str(value)

    def get(self):
        return self.value

    def set(self, value):
        self.value = str(value)


def test_clicking_a_floor_after_arrival_starts_from_arrived_floor():
    history = []
    view = SimpleNamespace(start_floor=FloorValue(10), end_floor=FloorValue(10),
                           profile=None, calculate=lambda: history.append("calculate") or True,
                           play=lambda: history.append("play"))
    view.destination_selected = lambda: HoistwayView.destination_selected(view)
    HoistwayView.select_floor(view, 3)
    assert view.start_floor.get() == "10"
    assert view.end_floor.get() == "3"
    assert history == ["calculate", "play"]


def test_changing_destination_during_motion_snaps_to_nearest_floor():
    trip = HoistwayTrip(10, 1, 10, 27)
    profile = scurve_profile(trip.distance_m, 2, 1, .8, 1500)
    midway = min(profile["samples"], key=lambda row: abs(row[1] - 12))
    history = []
    view = SimpleNamespace(
        start_floor=FloorValue(1), end_floor=FloorValue(2),
        profile={**profile, "trip": trip},
        slider=SimpleNamespace(get=lambda: midway[0]),
        stop=lambda: history.append("stopped"),
        calculate=lambda: history.append("recalculated") or True,
        play=lambda: history.append("played"),
    )
    HoistwayView.destination_selected(view)
    assert view.start_floor.get() == "5"
    assert history == ["stopped", "recalculated", "played"]


def test_reaching_last_sample_updates_departure_and_draws_car_floor(monkeypatch):
    trip = HoistwayTrip(10, 1, 10, 27)
    profile = {**scurve_profile(trip.distance_m, 2, 1, .8, 1500), "trip": trip}
    palette = {"text": "#111111", "muted": "#555555", "surface": "#ffffff",
               "accent": "#2677a8", "background": "#ffffff"}
    monkeypatch.setattr("src.ui.hoistway_view.get_theme", lambda _canvas: ("light", palette))
    car_rectangles, scroll = [], []

    class Chart:
        def winfo_width(self):
            return 600

        def winfo_height(self):
            return 500

        def delete(self, *_args):
            pass

        def create_line(self, *_args, **_kwargs):
            pass

        def create_oval(self, *_args, **_kwargs):
            pass

        def create_text(self, *_args, **_kwargs):
            pass

        def create_rectangle(self, *points, **options):
            if options.get("fill") == "#2879cc":
                car_rectangles.append(points)

        def yview_moveto(self, position):
            scroll.append(position)

    label = SimpleNamespace(configure=lambda **_options: None)
    view = SimpleNamespace(
        profile=profile, slider=SimpleNamespace(get=lambda: profile["duration_s"]),
        canvas=Chart(), structure_key=None,
        draw_structure=lambda *_args: None,
        phase_label=label,
        phase_labels={phase: label for phase in ("출발", "가속", "주행", "감속", "도착")},
        status_label=label, start_floor=FloorValue(1), arrived=False,
    )
    HoistwayView.redraw(view)
    assert view.start_floor.get() == "10"
    assert view.arrived
    assert car_rectangles[-1][3] == pytest.approx(HoistwayGeometry(10).floor_y(10))
    assert scroll and 0 <= scroll[-1] <= 1
