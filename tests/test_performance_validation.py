import pytest

from cadi_saml import AABB, ShapeCache, SpatialIndex


def test_performance_components_validate_and_update():
    with pytest.raises(ValueError, match="minimum bounds"):
        AABB(2, 0, 0, 1, 1, 1)
    with pytest.raises(ValueError, match="non-empty"):
        ShapeCache.put("", object())

    spatial = SpatialIndex()
    spatial.boxes.append(AABB(0, 0, 0, 1, 1, 1, tag="part"))
    spatial.boxes.append(AABB(0, 0, 0, 1, 1, 1, tag="part"))
    assert spatial.remove("part") == 2
    with pytest.raises(ValueError, match="non-negative"):
        spatial.find_potential_clashes(-0.1)
