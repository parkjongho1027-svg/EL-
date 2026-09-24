"""UI 테마의 색상 팔레트. Tk를 가져오지 않는다."""
from .constants import BUTTON_BG, BUTTON_ACTIVE_BG

THEMES = {
    "light": {
        "background": "#ffffff",
        "surface": "#ffffff",
        "result": "#f7faff",
        "text": "#1f1f1f",
        "muted": "#555555",
        "entry": "#ffffff",
        "disabled_entry": "#eeeeee",
        "button": BUTTON_BG,
        "button_active": BUTTON_ACTIVE_BG,
        "canvas": "#f2f4f7",
        "subtle": "#eaf3fb",
        "tab": "#e9ecef",
        "tab_selected": "#ffffff",
        "selection_bg": "#075c9c",
        "selection_fg": "#ffffff",
        "accent": "#2677a8",
        "border": "#aebdca",
        "header_1": "#dcecf8",
        "header_1_text": "#174d73",
        "header_2": "#e9ecef",
        "header_2_text": "#3f464d",
    },
    "dark": {
        # 참고 이미지처럼 바탕과 박스 안쪽은 검정으로 두고 파란색은
        # 테두리·제목·선택된 탭에만 사용합니다. 검정과 파랑의 대비가
        # 살아나므로 박스를 파란색으로 전부 채웠을 때보다 구분이 쉽습니다.
        "background": "#000000",
        "surface": "#03080d",
        "result": "#02070c",
        "text": "#ffffff",
        # 안내문·보조문구까지 회색으로 흐리지 않고 순백색으로 표시합니다.
        "muted": "#ffffff",
        "entry": "#06111b",
        "disabled_entry": "#101820",
        # 탭 선택 영역처럼 검정 바탕·흰 글씨·파란 외곽선을 사용합니다.
        "button": "#000000",
        "button_active": "#062f4f",
        "canvas": "#000000",
        "subtle": "#02070c",
        "tab": "#02070c",
        "tab_selected": "#075c9c",
        "selection_bg": "#075c9c",
        "selection_fg": "#ffffff",
        "accent": "#35adff",
        "border": "#167fca",
        "header_1": "#06233a",
        "header_1_text": "#ffffff",
        "header_2": "#03080d",
        "header_2_text": "#ffffff",
    },
}
