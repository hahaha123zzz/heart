import pytest

from integrations.deeptutor.product_surface import validate_options


def test_product_surface_allows_chat_capabilities():
    assert validate_options({"capability": "chat"})["capability"] == "chat"
    assert validate_options({"capability": "immersive_reading"})["capability"] == "immersive_reading"


def test_product_surface_hides_unrelated_capabilities():
    with pytest.raises(ValueError, match="capability_not_enabled"):
        validate_options({"capability": "partner_authoring"})
