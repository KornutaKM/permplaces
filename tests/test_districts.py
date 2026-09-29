from app.districts import DISTRICT_BY_KEY, PERM_DISTRICTS, PERM_RELATION_ID


def test_perm_has_seven_unique_osm_district_boundaries() -> None:
    assert PERM_RELATION_ID == 1_084_793
    assert len(PERM_DISTRICTS) == 7
    assert len({district.key for district in PERM_DISTRICTS}) == 7
    assert len({district.relation_id for district in PERM_DISTRICTS}) == 7


def test_verified_relation_ids() -> None:
    assert DISTRICT_BY_KEY["dzerzhinsky"].relation_id == 1_268_696
    assert DISTRICT_BY_KEY["industrialny"].relation_id == 1_268_694
    assert DISTRICT_BY_KEY["kirovsky"].relation_id == 1_268_698
    assert DISTRICT_BY_KEY["leninsky"].relation_id == 1_268_697
    assert DISTRICT_BY_KEY["motovilikhinsky"].relation_id == 1_268_693
    assert DISTRICT_BY_KEY["ordzhonikidzevsky"].relation_id == 1_268_692
    assert DISTRICT_BY_KEY["sverdlovsky"].relation_id == 1_268_699
