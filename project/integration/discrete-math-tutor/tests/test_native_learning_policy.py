from integrations.deeptutor.native_bridge import native_learning_policy


def test_native_bridge_can_read_authorized_course_materials():
    policy = native_learning_policy()
    assert policy["allowed_capabilities"] == ["chat", "immersive_reading"]
    assert policy["allowed_surfaces"] == ["chat", "reading"]
    assert policy["reading"]["material_ids"] == ["*"]
    assert policy["reading"]["allow_upload"] is False


def test_native_bridge_policy_preserves_age_band():
    policy = native_learning_policy(
        {"age_band": "13-15", "reading": {"material_ids": ["stale"]}}
    )
    assert policy["age_band"] == "13-15"
    assert policy["reading"]["material_ids"] == ["*"]
