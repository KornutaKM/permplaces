from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class District:
    key: str
    name: str
    relation_id: int


# OpenStreetMap administrative boundary relation for Perm Urban Okrug.
PERM_RELATION_ID = 1_084_793

# Current OSM administrative boundary relations for the seven city districts of Perm.
PERM_DISTRICTS: tuple[District, ...] = (
    District("dzerzhinsky", "Дзержинский", 1_268_696),
    District("industrialny", "Индустриальный", 1_268_694),
    District("kirovsky", "Кировский", 1_268_698),
    District("leninsky", "Ленинский", 1_268_697),
    District("motovilikhinsky", "Мотовилихинский", 1_268_693),
    District("ordzhonikidzevsky", "Орджоникидзевский", 1_268_692),
    District("sverdlovsky", "Свердловский", 1_268_699),
)

DISTRICT_BY_KEY = {district.key: district for district in PERM_DISTRICTS}
