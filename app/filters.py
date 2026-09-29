from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlaceFilters:
    outdoor_seating: bool = False
    wifi: bool = False

    @property
    def active(self) -> bool:
        return self.outdoor_seating or self.wifi
