from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlaceFilters:
    outdoor_seating: bool = False
    wifi: bool = False
    open_now: bool = False

    @property
    def active(self) -> bool:
        return self.outdoor_seating or self.wifi or self.open_now
