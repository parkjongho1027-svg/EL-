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


@dataclass(frozen=True)
class HoistwayOverviewGeometry:
    """Map the entire shaft to the visible height of the fixed overview."""

    floors: int
    height_px: int
    top_px: int = 90
    bottom_margin_px: int = 35

    @property
    def bottom_px(self):
        return max(self.top_px + 60, self.height_px - self.bottom_margin_px)

    def floor_y(self, floor):
        fraction = (floor - 1) / (self.floors - 1)
        return self.bottom_px - fraction * (self.bottom_px - self.top_px)

    def car_bottom_y(self, trip: HoistwayTrip, traveled_m: float):
        car_height_m, _ = trip.position(traveled_m)
        return self.bottom_px - car_height_m / trip.height_m * (self.bottom_px - self.top_px)

    def counterweight_bottom_y(self, trip: HoistwayTrip, traveled_m: float):
        _, weight_height_m = trip.position(traveled_m)
        return self.bottom_px - weight_height_m / trip.height_m * (self.bottom_px - self.top_px)
