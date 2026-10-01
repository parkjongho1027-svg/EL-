"""승강로 계산값을 화면의 픽셀 좌표로 바꾸는 모듈."""

from dataclasses import dataclass

from src.core.hoistway import HoistwayTrip


@dataclass(frozen=True)
class HoistwayGeometry:
    """층 높이와 여백을 이용해 승강로 화면 좌표를 계산한다."""
    floors: int
    pitch_px: int = 68
    top_px: int = 122
    bottom_px: int = 90

    @property
    def height_px(self):
        """모든 층과 위·아래 여백을 포함한 전체 화면 높이를 구한다."""
        return self.top_px + (self.floors - 1) * self.pitch_px + self.bottom_px

    def floor_y(self, floor):
        """지정한 층의 바닥선을 화면 Y좌표로 바꾼다."""
        return self.top_px + (self.floors - floor) * self.pitch_px

    def car_bottom_y(self, trip: HoistwayTrip, traveled_m: float):
        """카의 실제 높이를 화면에서 카 바닥이 놓일 Y좌표로 바꾼다."""
        car_height_m, _ = trip.position(traveled_m)
        return self.floor_y(1) - car_height_m / trip.floor_height_m * self.pitch_px

    def counterweight_bottom_y(self, trip: HoistwayTrip, traveled_m: float):
        """균형추의 실제 높이를 화면에서 균형추 바닥이 놓일 Y좌표로 바꾼다."""
        _, counterweight_height_m = trip.position(traveled_m)
        return self.floor_y(1) - counterweight_height_m / trip.floor_height_m * self.pitch_px
