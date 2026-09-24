"""교재 참고표의 행 선택과 용도별 입력 항목 회귀 검사 (원문 검증은 별도)."""
import pytest

from src.core.calculators import traffic_pdf_reference, traffic_visible_input_fields


@pytest.mark.parametrize('use,floors,expected', [
    ('오피스-전용사옥', 10, '60~90'),
    ('오피스-전용사옥', 11, '90~150'),
    ('오피스-전용사옥', 50, '360~540'),
    ('오피스-전용사옥', 51, '480 이상'),
    ('호텔-비즈니스', 15, '90~120'),
    ('호텔-비즈니스', 16, '105~150'),
    ('공동주택', 15, '60 이하'),
    ('공동주택', 16, '60~105'),
    ('병원', 20, None),
])
def test_speed_reference_selects_at_floor_boundaries(use, floors, expected):
    assert traffic_pdf_reference(use, floors)['speed_range_m_min'] == expected


@pytest.mark.parametrize('use,kwargs,count,basis', [
    ('오피스-전용사옥', {'total_area': 2401, 'population': 151}, 3, '면적'),
    ('공동주택', {'households': 141}, 3, '가구'),
    ('호텔-고급', {'rooms': 201}, 3, '실'),
])
def test_reference_rough_counts_round_up(use, kwargs, count, basis):
    result = traffic_pdf_reference(use, 20, **kwargs)
    assert result['rough_count'] == count
    assert basis in result['rough_basis']


@pytest.mark.parametrize('use,specific,unrelated', [
    ('오피스-복합사옥', 'A', 'rooms'),
    ('공동주택', 'households', 'beds'),
    ('호텔-중급', 'rooms', 'households'),
    ('병원', 'beds', 'rooms'),
    ('기타', 'direct_population', 'A'),
])
def test_building_type_shows_only_relevant_population_fields(use, specific, unrelated):
    visible = traffic_visible_input_fields(use)
    assert specific in visible
    assert unrelated not in visible
    assert {'F', 'phi', 'C'} <= visible
