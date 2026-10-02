"""Floor spacing, car floor alignment, and destination controls."""

from types import SimpleNamespace

import pytest

from src.core.hoistway import HoistwayTrip, PHASE_NAMES
from src.core.trajectory import scurve_profile
from src.ui.hoistway_geometry import HoistwayGeometry, HoistwayOverviewGeometry
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


@pytest.mark.parametrize("floors,start,end", [(2, 1, 2), (10, 1, 10), (100, 89, 90), (100, 100, 1)])
def test_overview_fits_both_bodies_and_floor_markers_without_scrolling(floors, start, end):
    trip = HoistwayTrip(floors, start, end, (floors - 1) * 3)
    geom = HoistwayOverviewGeometry(floors, 500)
    for traveled in (0, trip.distance_m / 2, trip.distance_m):
        car = geom.car_bottom_y(trip, traveled)
        counterweight = geom.counterweight_bottom_y(trip, traveled)
        assert geom.top_px <= car <= geom.bottom_px
        assert geom.top_px <= counterweight <= geom.bottom_px
        assert car + counterweight == pytest.approx(geom.top_px + geom.bottom_px)
    assert geom.car_bottom_y(trip, 0) == pytest.approx(geom.floor_y(start))
    assert geom.car_bottom_y(trip, trip.distance_m) == pytest.approx(geom.floor_y(end))


def test_overview_shows_only_departure_and_destination_labels():
    trip = HoistwayTrip(100, 89, 90, 297)
    texts, rectangles = [], []

    class Chart:
        def delete(self, *_args):
            pass

        def winfo_height(self):
            return 500

        def create_text(self, _x, _y, **options):
            texts.append(options["text"])

        def create_rectangle(self, *points, **options):
            rectangles.append((points, options["fill"]))

        def create_line(self, *_args, **_kwargs):
            pass

        def create_oval(self, *_args, **_kwargs):
            pass

    view = SimpleNamespace(overview_canvas=Chart())
    palette = {"text": "#111111", "border": "#aaaaaa", "surface": "#ffffff"}
    HoistwayView.draw_overview(view, trip, trip.distance_m, palette)
    assert [label for label in texts if "층" in label] == ["출발 89층", "도착 90층"]
    assert "권상기" in texts
    bodies = [points for points, color in rectangles if color in ("#2879cc", "#d46a17")]
    assert len(bodies) == 2
    assert bodies[0][3] == pytest.approx(HoistwayOverviewGeometry(100, 500).floor_y(90))


def test_overview_remains_visible_for_short_and_tall_shafts():
    view = SimpleNamespace(overview_visible=False)
    HoistwayView.sync_overview_visibility(view, HoistwayGeometry(2), 500)
    assert view.overview_visible
    HoistwayView.sync_overview_visibility(view, HoistwayGeometry(10), 500)
    assert view.overview_visible
    HoistwayView.sync_overview_visibility(view, HoistwayGeometry(100), 1000)
    assert view.overview_visible


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


@pytest.mark.parametrize("shown_time_offset,forced", [(0, False), (0.04, True)])
def test_reaching_last_sample_updates_departure_and_draws_car_floor(monkeypatch, shown_time_offset, forced):
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

    phases = []
    label = SimpleNamespace(configure=lambda **options: phases.append(options.get("text")))
    view = SimpleNamespace(
        profile=profile, slider=SimpleNamespace(get=lambda: profile["duration_s"] - shown_time_offset),
        canvas=Chart(), structure_key=None,
        draw_structure=lambda *_args: None,
        draw_overview=lambda *_args: None,
        sync_overview_visibility=lambda *_args: None,
        overview_visible=False,
        phase_label=label,
        phase_labels={phase: label for phase in (*PHASE_NAMES, "도착")},
        status_label=label, start_floor=FloorValue(1), arrived=False,
    )
    HoistwayView.redraw(view, force_finish=forced)
    assert view.start_floor.get() == "10"
    assert view.arrived
    assert "도착" in phases
    assert car_rectangles[-1][3] == pytest.approx(HoistwayGeometry(10).floor_y(10))
    assert scroll and 0 <= scroll[-1] <= 1


def test_tick_forces_arrival_despite_scale_rounding():
    duration = 13.024
    values = {"time": 12.95, "forced": None, "stopped": False}

    def set_slider(value):
        values["time"] = round(value / 0.05) * 0.05

    view = SimpleNamespace(
        after_id=None, playing=True, window=SimpleNamespace(winfo_exists=lambda: True),
        profile={"duration_s": duration},
        slider=SimpleNamespace(get=lambda: values["time"], set=set_slider),
        redraw=lambda **options: values.update(forced=options.get("force_finish")),
        stop=lambda: values.update(stopped=True),
    )
    HoistwayView.tick(view)
    assert values["time"] < duration
    assert values["forced"] is True
    assert values["stopped"] is True
