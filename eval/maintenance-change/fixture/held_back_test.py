import labels


def test_requirement_changes_display_only():
    assert labels.STABLE_KEY == "account_status"
    assert labels.display_label() == "Account status"
