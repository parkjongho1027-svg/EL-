"""Physical stage boundaries come from the trajectory, not sampled acceleration."""

import pytest

from src.core.trajectory import scurve_profile
from src.ui.native_plot import render_png
from src.ui.phase_annotations import phase_segments


@pytest.mark.parametrize("distance,expected_numbers", [
    (40, (1, 2, 3, 4, 5, 6, 7)),
    (0.4, (1, 3, 5, 7)),
])
def test_plot_stages_match_computed_profile(distance, expected_numbers):
    profile = scurve_profile(distance, 2, 1, 0.8, 1500)
    stages = phase_segments(profile)
    assert tuple(stage[0] for stage in stages) == expected_numbers
    assert stages[0][2] == 0
    assert stages[-1][3] == pytest.approx(profile["duration_s"])
    assert all(stage[3] > stage[2] for stage in stages)


def test_old_or_invalid_phase_metadata_is_not_drawn():
    profile = scurve_profile(40, 2, 1, 0.8, 1500)
    assert phase_segments({k: v for k, v in profile.items()
                           if k != "phase_durations_s"}) == ()
    assert phase_segments({**profile, "phase_durations_s": (1,) * 7}) == ()


def test_mechanical_png_has_stage_annotations_but_electrical_png_does_not():
    profile = scurve_profile(40, 2, 1, 0.8, 1500)
    palette = {"surface": "#ffffff", "text": "#222222", "accent": "#2879cc"}
    annotated = render_png(profile, palette, size=(900, 400))
    unannotated = render_png({k: v for k, v in profile.items()
                              if k != "phase_durations_s"}, palette,
                             size=(900, 400))
    assert annotated.startswith(b"\x89PNG\r\n\x1a\n")
    assert annotated != unannotated
    electrical = {**profile, "grid_kw_samples": profile["signed_mechanical_kw_samples"]}
    assert render_png(electrical, palette, size=(900, 400)) == render_png(
        {k: v for k, v in electrical.items() if k != "phase_durations_s"},
        palette, size=(900, 400))
