"""Screen coordinates for a scrollable, equal-floor-height hoistway diagram."""

from dataclasses import dataclass

from src.core.hoistway import HoistwayTrip


@dataclass(frozen=True)
class HoistwayGeometry:
    floors: int
    pitch_px: int = 68
    top_px: int = 122
    bottom_px: int = 90

    @property
    def height_px(self):
        return self.top_px + (self.floors - 1) * self.pitch_px + self.bottom_px

    def floor_y(self, floor):
        return self.top_px + (self.floors - floor) * self.pitch_px

    def car_bottom_y(self, trip: HoistwayTrip, traveled_m: float):
        car_height_m, _ = trip.position(traveled_m)
        return self.floor_y(1) - car_height_m / trip.floor_height_m * self.pitch_px

    def counterweight_bottom_y(self, trip: HoistwayTrip, traveled_m: float):
        _, counterweight_height_m = trip.position(traveled_m)
        return self.floor_y(1) - counterweight_height_m / trip.floor_height_m * self.pitch_px
